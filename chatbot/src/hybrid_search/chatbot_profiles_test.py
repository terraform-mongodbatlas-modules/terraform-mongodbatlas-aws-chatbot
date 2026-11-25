from __future__ import annotations

import pytest
from pymongo.errors import OperationFailure

from hybrid_search.chatbot_profiles import (
    PROFILES_COLLECTION,
    ChatbotProfile,
    DemoQuery,
    StartupStatus,
    load_registry,
    load_startup_status,
    record_startup_status,
    upsert_profile,
)


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    async def to_list(self, length: object) -> list[dict]:
        return self._docs


class _FakeCollection:
    name = PROFILES_COLLECTION

    def __init__(self, docs: list[dict] | None = None) -> None:
        self._docs = docs or []
        self.updates: list[dict] = []

    def find(self, filter: dict) -> _FakeCursor:
        assert filter == {}
        return _FakeCursor(self._docs)

    async def update_one(self, filter: dict, update: dict, upsert: bool = False) -> None:
        self.updates.append({"filter": filter, "update": update, "upsert": upsert})

    async def find_one(self, filter: dict) -> dict | None:
        return next((doc for doc in self._docs if doc.get("_id") == filter.get("_id")), None)


def _doc(name: str = "healthcare", **overrides: object) -> dict:
    base: dict[str, object] = {"_id": name, "display_name": "Healthcare"}
    base.update(overrides)
    return base


async def test_load_registry_parses_queries_and_the_prompt():
    doc = _doc(
        queries=[{"label": "Marge", "message": "What is due?"}],
        system_prompt="Answer as the member assistant.",
    )

    registry = await load_registry(_FakeCollection([doc]))

    assert registry["healthcare"] == ChatbotProfile(
        display_name="Healthcare",
        queries=[DemoQuery(label="Marge", message="What is due?")],
        system_prompt="Answer as the member assistant.",
    )


async def test_load_registry_defaults_to_no_queries_and_no_prompt():
    registry = await load_registry(_FakeCollection([_doc()]))

    assert registry["healthcare"].queries == []
    assert registry["healthcare"].system_prompt is None


async def test_load_registry_treats_null_queries_as_empty():
    registry = await load_registry(_FakeCollection([_doc(queries=None)]))

    assert registry["healthcare"].queries == []


async def test_load_registry_ignores_unknown_fields():
    registry = await load_registry(_FakeCollection([_doc(unexpected="not a profile field")]))

    assert registry["healthcare"].display_name == "Healthcare"


@pytest.mark.parametrize(
    "doc",
    [
        {"display_name": "No id"},
        {"_id": 7, "display_name": "Not a string"},
        _doc(display_name=None),
        _doc(display_name=""),
    ],
)
async def test_load_registry_skips_a_document_without_a_usable_name_or_label(doc: dict):
    assert await load_registry(_FakeCollection([doc])) == {}


@pytest.mark.parametrize(
    ("insert_fields", "expected_update"),
    [
        (
            {"display_name": "chunks"},
            {
                "$set": {"system_prompt": "Answer briefly."},
                "$setOnInsert": {"display_name": "chunks"},
            },
        ),
        (
            None,
            {"$set": {"system_prompt": "Answer briefly."}},
        ),
    ],
)
async def test_upsert_profile_keys_the_document_by_collection_name(
    insert_fields: dict | None,
    expected_update: dict,
):
    collection = _FakeCollection()

    await upsert_profile(
        collection,
        name="healthcare",
        set_fields={"system_prompt": "Answer briefly."},
        insert_fields=insert_fields,
    )

    assert collection.updates == [
        {"filter": {"_id": "healthcare"}, "update": expected_update, "upsert": True}
    ]


async def test_record_startup_status_sets_the_subdocument_without_upsert():
    collection = _FakeCollection([_doc()])
    status = StartupStatus(outcome="failed", phase="indexes", error="model is not enabled")

    await record_startup_status(collection, name="healthcare", status=status)

    assert collection.updates == [
        {
            "filter": {"_id": "healthcare"},
            "update": {"$set": {"startup": status.model_dump()}},
            "upsert": False,
        }
    ]


async def test_load_startup_status_reads_the_subdocument():
    stored = StartupStatus(outcome="ok", phase="ingest")
    collection = _FakeCollection([_doc(startup=stored.model_dump())])

    loaded = await load_startup_status(collection, name="healthcare")

    assert loaded is not None
    assert (loaded.outcome, loaded.phase, loaded.error) == ("ok", "ingest", None)


@pytest.mark.parametrize(
    "doc",
    [
        _doc(),
        _doc(startup=None),
        _doc(startup={"outcome": "nope"}),
        _doc(startup="not a document"),
    ],
)
async def test_load_startup_status_returns_none_for_missing_or_invalid_values(doc: dict):
    assert await load_startup_status(_FakeCollection([doc]), name="healthcare") is None


async def test_load_startup_status_returns_none_on_a_mongo_error():
    class _Broken:
        async def find_one(self, filter: dict) -> dict:
            raise OperationFailure("not authorized", 13)

    assert await load_startup_status(_Broken(), name="healthcare") is None
