from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import SecretStr
from pymongo.errors import OperationFailure

from hybrid_search.health import IndexState
from hybrid_search.indexes import (
    autoembed_index_definition,
    create_and_wait_chunks_indexes,
    create_chunks_indexes_if_missing,
    ensure_indexes_ready,
    format_index_ready_line,
    index_states,
    wait_chunks_indexes_ready,
)
from hybrid_search.settings import HybridSearchSettings

_Page = list[dict[str, Any]] | Exception


class _FakeCursor:
    """Replays the next page from the owning collection; the last page repeats."""

    def __init__(self, collection: _FakeCollection) -> None:
        self._collection = collection

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        collection = self._collection
        page = collection.pages[min(collection.page_index, len(collection.pages) - 1)]
        collection.page_index += 1
        if isinstance(page, Exception):
            raise page
        return page


class _FakeCollection:
    def __init__(
        self,
        pages: list[_Page],
        *,
        name: str = "chunks",
        database_name: str = "hybrid_search",
        create_failures: int = 0,
        create_errors: list[Exception] | None = None,
    ) -> None:
        self.name = name
        self.database = type("DB", (), {"name": database_name})()
        self.pages = pages
        self.page_index = 0
        self.create_failures = create_failures
        self.create_errors = list(create_errors or [])
        self.inserted = 0
        self.created: list[str] = []
        self.dropped: list[str] = []

    def list_search_indexes(self) -> _FakeCursor:
        return _FakeCursor(self)

    async def insert_one(self, _doc: dict[str, Any]) -> None:
        self.inserted += 1

    async def delete_one(self, _doc: dict[str, Any]) -> None:
        pass

    async def create_search_index(self, model: Any) -> None:
        if self.create_errors:
            raise self.create_errors.pop(0)
        if self.create_failures > 0:
            self.create_failures -= 1
            raise OperationFailure("database hybrid_search not found", 26)
        self.created.append(model.document["name"])

    async def drop_search_index(self, name: str) -> None:
        self.dropped.append(name)


@pytest.fixture
def settings() -> HybridSearchSettings:
    return HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
    )


def _index(name: str, status: str) -> dict[str, str]:
    return {"name": name, "status": status}


@pytest.mark.asyncio
async def test_create_indexes_when_missing(settings):
    collection = _FakeCollection([[]])

    await create_chunks_indexes_if_missing(collection, settings)

    assert collection.created == ["autoembed_idx", "text_idx"]


@pytest.mark.asyncio
async def test_create_indexes_skips_existing(settings):
    collection = _FakeCollection([[_index("autoembed_idx", "READY"), _index("text_idx", "READY")]])

    await create_chunks_indexes_if_missing(collection, settings)

    assert collection.created == []


@pytest.mark.asyncio
async def test_create_materializes_namespace_then_retries(settings, caplog):
    collection = _FakeCollection([[]], create_failures=1)
    caplog.set_level(logging.INFO)

    await create_chunks_indexes_if_missing(collection, settings)

    assert collection.inserted == 1
    assert collection.created == ["autoembed_idx", "text_idx"]
    assert "namespace missing" in caplog.text.lower()


@pytest.mark.asyncio
async def test_create_reraises_other_operation_failure(settings):
    collection = _FakeCollection([OperationFailure("unauthorized", 13)])

    with pytest.raises(OperationFailure, match="unauthorized"):
        await create_chunks_indexes_if_missing(collection, settings)
    assert collection.inserted == 0


@pytest.mark.asyncio
async def test_wait_until_ready(settings):
    collection = _FakeCollection(
        [
            [_index("autoembed_idx", "BUILDING"), _index("text_idx", "READY")],
            [_index("autoembed_idx", "READY"), _index("text_idx", "READY")],
        ]
    )

    ready = await wait_chunks_indexes_ready(collection, settings, timeout_s=5, interval_s=0)

    assert ("chunks", "text_idx", "READY") in ready
    assert ("chunks", "autoembed_idx", "READY") in ready


@pytest.mark.asyncio
async def test_wait_raises_when_index_failed(settings):
    collection = _FakeCollection([[_index("autoembed_idx", "FAILED")]])

    with pytest.raises(RuntimeError, match="autoembed_idx failed"):
        await wait_chunks_indexes_ready(collection, settings, timeout_s=5, interval_s=0)


@pytest.mark.asyncio
async def test_wait_times_out(settings):
    collection = _FakeCollection([[_index("autoembed_idx", "BUILDING")]])

    with pytest.raises(TimeoutError):
        await wait_chunks_indexes_ready(collection, settings, timeout_s=0.01, interval_s=0)


@pytest.mark.asyncio
async def test_wait_materializes_namespace_when_list_missing(settings, caplog):
    collection = _FakeCollection(
        [
            OperationFailure("database hybrid_search not found", 26),
            [_index("autoembed_idx", "READY"), _index("text_idx", "READY")],
        ]
    )
    caplog.set_level(logging.INFO)

    ready = await wait_chunks_indexes_ready(collection, settings, timeout_s=5, interval_s=0)

    assert collection.inserted == 1
    assert ("chunks", "autoembed_idx", "READY") in ready
    assert "hybrid_search.chunks" in caplog.text


@pytest.mark.asyncio
async def test_wait_logs_status_transitions(settings, caplog):
    collection = _FakeCollection(
        [
            [_index("autoembed_idx", "BUILDING"), _index("text_idx", "BUILDING")],
            [_index("autoembed_idx", "READY"), _index("text_idx", "READY")],
        ]
    )
    caplog.set_level(logging.INFO)

    await wait_chunks_indexes_ready(collection, settings, timeout_s=5, interval_s=0)

    assert "chunks.autoembed_idx BUILDING" in caplog.text
    assert "chunks.autoembed_idx READY" in caplog.text
    assert "chunks.text_idx BUILDING" in caplog.text
    assert "chunks.text_idx READY" in caplog.text


@pytest.mark.asyncio
async def test_wait_logs_status_every_poll_not_just_transitions(settings, caplog):
    collection = _FakeCollection(
        [
            [_index("autoembed_idx", "BUILDING")],
            [_index("autoembed_idx", "BUILDING")],
            [_index("autoembed_idx", "READY"), _index("text_idx", "READY")],
        ]
    )
    caplog.set_level(logging.INFO)

    await wait_chunks_indexes_ready(collection, settings, timeout_s=5, interval_s=0)

    # The second BUILDING poll repeats the previous status and must still be logged.
    assert caplog.text.count("chunks.autoembed_idx BUILDING") == 2


@pytest.mark.asyncio
async def test_wait_logs_missing_index_as_pending_every_poll(settings, caplog):
    collection = _FakeCollection(
        [
            [_index("autoembed_idx", "BUILDING")],
            [_index("autoembed_idx", "BUILDING")],
            [_index("autoembed_idx", "READY"), _index("text_idx", "READY")],
        ]
    )
    caplog.set_level(logging.INFO)

    await wait_chunks_indexes_ready(collection, settings, timeout_s=5, interval_s=0)

    assert caplog.text.count("chunks.text_idx PENDING") == 2


@pytest.mark.asyncio
async def test_ensure_indexes_ready_passes_when_both_ready(settings):
    collection = _FakeCollection([[_index("autoembed_idx", "READY"), _index("text_idx", "READY")]])
    await ensure_indexes_ready(collection, settings)


@pytest.mark.asyncio
async def test_ensure_indexes_ready_raises_with_status_for_pending(settings):
    collection = _FakeCollection(
        [[_index("autoembed_idx", "BUILDING"), _index("text_idx", "READY")]]
    )
    with pytest.raises(RuntimeError, match=r"autoembed_idx \(BUILDING\)"):
        await ensure_indexes_ready(collection, settings)


@pytest.mark.asyncio
async def test_ensure_indexes_ready_reports_missing_index(settings):
    collection = _FakeCollection([[_index("text_idx", "READY")]])
    with pytest.raises(RuntimeError, match=r"autoembed_idx \(MISSING\)"):
        await ensure_indexes_ready(collection, settings)


def test_autoembed_index_definition():
    definition = autoembed_index_definition(model="voyage-4-lite")
    assert definition["fields"][0] == {
        "type": "autoEmbed",
        "modality": "text",
        "path": "content",
        "model": "voyage-4-lite",
    }
    assert definition["fields"][1] == {"type": "filter", "path": "file_path"}


def test_autoembed_index_definition_has_no_dimensions():
    definition = autoembed_index_definition(model="voyage-4-lite")
    assert "numDimensions" not in str(definition)
    assert all(field.get("type") != "vector" for field in definition["fields"])


def test_format_index_ready_line():
    line = format_index_ready_line("chunks", "autoembed_idx")
    assert line.endswith(" chunks.autoembed_idx READY")


@pytest.mark.asyncio
async def test_create_and_wait_chunks_indexes_returns_and_logs_the_ready_lines(settings, caplog):
    collection = _FakeCollection([[_index("autoembed_idx", "READY"), _index("text_idx", "READY")]])
    caplog.set_level(logging.INFO)

    lines = await create_and_wait_chunks_indexes(collection, settings)

    assert collection.created == []
    assert all(line.endswith(" READY") for line in lines)
    assert {line.split()[1] for line in lines} == {"chunks.autoembed_idx", "chunks.text_idx"}
    assert "chunks.text_idx READY" in caplog.text


@pytest.mark.asyncio
async def test_index_states_report_missing_instead_of_pending(settings):
    collection = _FakeCollection([[_index("text_idx", "READY")]])

    states = await index_states(collection, settings)

    assert states == [
        IndexState(name="autoembed_idx", status="MISSING"),
        IndexState(name="text_idx", status="READY"),
    ]


@pytest.mark.parametrize(
    ("status_detail", "expected"),
    [
        ("autoEmbed model is not enabled", "autoEmbed model is not enabled"),
        (
            [{"message": "model is not enabled"}, {"message": "retry later"}],
            "model is not enabled; retry later",
        ),
        (["first", "second"], "first; second"),
        (None, None),
    ],
)
@pytest.mark.asyncio
async def test_index_states_carry_the_atlas_status_detail(settings, status_detail, expected):
    index = {"name": "autoembed_idx", "status": "FAILED"}
    if status_detail is not None:
        index["statusDetail"] = status_detail
    collection = _FakeCollection([[index, _index("text_idx", "READY")]])

    states = await index_states(collection, settings)

    assert states[0].detail == expected


@pytest.mark.asyncio
async def test_wait_failed_error_includes_the_atlas_detail(settings):
    collection = _FakeCollection(
        [
            [
                {
                    "name": "autoembed_idx",
                    "status": "FAILED",
                    "statusDetail": "autoEmbed model is not enabled",
                }
            ]
        ]
    )

    with pytest.raises(RuntimeError, match="autoEmbed model is not enabled"):
        await wait_chunks_indexes_ready(collection, settings, timeout_s=5, interval_s=0)


@pytest.mark.asyncio
async def test_create_recreates_a_failed_index_when_requested(settings):
    collection = _FakeCollection([[_index("autoembed_idx", "FAILED"), _index("text_idx", "READY")]])

    await create_chunks_indexes_if_missing(collection, settings, recreate_failed=True)

    assert collection.dropped == ["autoembed_idx"]
    assert collection.created == ["autoembed_idx"]


@pytest.mark.asyncio
async def test_create_leaves_a_failed_index_by_default(settings):
    collection = _FakeCollection([[_index("autoembed_idx", "FAILED"), _index("text_idx", "READY")]])

    await create_chunks_indexes_if_missing(collection, settings)

    assert collection.dropped == []
    assert collection.created == []


@pytest.mark.asyncio
async def test_create_and_wait_retries_a_transient_failure(settings):
    collection = _FakeCollection(
        [[], [], [_index("autoembed_idx", "READY"), _index("text_idx", "READY")]],
        create_errors=[OperationFailure("transient", 8000)],
    )
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    lines = await create_and_wait_chunks_indexes(
        collection, settings, create_attempts=2, sleep=fake_sleep
    )

    assert collection.created == ["autoembed_idx", "text_idx"]
    assert delays == [2.0]
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_create_and_wait_raises_after_the_last_attempt(settings):
    collection = _FakeCollection(
        [[]],
        create_errors=[OperationFailure("first", 8000), OperationFailure("second", 8000)],
    )
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    with pytest.raises(OperationFailure, match="second"):
        await create_and_wait_chunks_indexes(
            collection, settings, create_attempts=2, sleep=fake_sleep
        )

    assert delays == [2.0]
    # One list per attempt, and no wait ran after the last failure.
    assert collection.page_index == 2
