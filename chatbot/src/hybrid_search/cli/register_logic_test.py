from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

import hybrid_search.cli.register_logic as register_module
from hybrid_search.cli.ingest_logic import IngestResult
from hybrid_search.cli.register_logic import RegisterInput, register
from hybrid_search.settings import HybridSearchSettings


class _FakeDatabase:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def __getitem__(self, name: str) -> dict:
        self.requested.append(name)
        return {"name": name}


class _FakeClient:
    def __init__(self, database: _FakeDatabase) -> None:
        self.database = database
        self.closed = False

    def __getitem__(self, name: str) -> _FakeDatabase:
        assert name == "hybrid_search"
        return self.database

    def close(self) -> None:
        self.closed = True


def _input(**overrides: object) -> RegisterInput:
    base: dict[str, object] = {
        "settings": HybridSearchSettings(mongodb_uri=SecretStr("mongodb://localhost")),
        "collection": "healthcare",
        "display_name": "Healthcare",
    }
    base.update(overrides)
    return RegisterInput(**base)


def _patch(monkeypatch) -> dict:
    database = _FakeDatabase()
    client = _FakeClient(database)
    calls: dict[str, object] = {
        "client": client,
        "database": database,
        "indexes": 0,
        "upsert": None,
        "ingest": None,
    }

    async def fake_indexes(collection: object, settings: object) -> list:
        calls["indexes"] += 1
        return ["2026-11-25 healthcare.autoembed_idx READY"]

    async def fake_upsert(
        registry: object, *, name: str, set_fields: dict, insert_fields=None
    ) -> None:
        calls["upsert"] = {
            "registry": registry,
            "name": name,
            "set_fields": set_fields,
            "insert_fields": insert_fields,
        }

    async def fake_ingest(
        settings: HybridSearchSettings,
        collection: object,
        state_collection: object,
        dirs: list[Path],
        **kwargs: object,
    ) -> IngestResult:
        calls["ingest"] = {
            "settings": settings,
            "collection": collection,
            "state_collection": state_collection,
            "dirs": dirs,
            "force": kwargs.get("force"),
        }
        return IngestResult(ingested=2, skipped=1)

    monkeypatch.setattr(register_module, "get_client", lambda _settings: client)
    monkeypatch.setattr(register_module, "create_and_wait_chunks_indexes", fake_indexes)
    monkeypatch.setattr(register_module.chatbot_profiles, "upsert_profile", fake_upsert)
    monkeypatch.setattr(register_module, "ingest_dirs", fake_ingest)
    return calls


def test_register_rejects_an_invalid_collection_name(monkeypatch):
    monkeypatch.setattr(register_module, "get_client", lambda _settings: pytest.fail("opened"))

    result = register(_input(collection="bad.name"))

    assert result.exit_code == 1


def test_register_creates_indexes_and_writes_the_document(monkeypatch, tmp_path):
    calls = _patch(monkeypatch)
    queries = tmp_path / "queries.yaml"
    queries.write_text("- label: Marge\n  message: What is due?\n")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Answer as the member assistant.\n")

    result = register(
        _input(
            description="Clinical notes",
            icon="/public/health.svg",
            demo_queries_path=queries,
            system_prompt_path=prompt,
        )
    )

    assert result.exit_code == 0
    assert len(result.ready_lines) == 1
    assert result.ready_lines[0].endswith("healthcare.autoembed_idx READY")
    assert calls["indexes"] == 1
    assert calls["upsert"] == {
        "registry": {"name": "_chatbot_profiles"},
        "name": "healthcare",
        "set_fields": {
            "display_name": "Healthcare",
            "description": "Clinical notes",
            "icon": "/public/health.svg",
            "queries": [{"label": "Marge", "message": "What is due?"}],
            "system_prompt": "Answer as the member assistant.",
        },
        "insert_fields": None,
    }
    assert calls["client"].closed is True


def test_register_leaves_omitted_fields_out(monkeypatch):
    calls = _patch(monkeypatch)

    register(_input())

    assert calls["upsert"]["set_fields"] == {"display_name": "Healthcare"}


def test_register_ingests_directories_into_the_new_collection(monkeypatch, tmp_path):
    calls = _patch(monkeypatch)

    result = register(_input(dirs=[tmp_path], force=True))

    ingest = calls["ingest"]
    assert ingest["settings"].chunks_collection == "healthcare"
    assert ingest["settings"].skip_index_creation is False
    assert ingest["collection"] == {"name": "healthcare"}
    assert ingest["state_collection"] == {"name": "healthcare_ingest_state"}
    assert ingest["dirs"] == [tmp_path]
    assert ingest["force"] is True
    assert (result.ingested, result.skipped) == (2, 1)


def test_register_rejects_an_empty_system_prompt_file(monkeypatch, tmp_path):
    calls = _patch(monkeypatch)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("  \n")

    result = register(_input(system_prompt_path=prompt))

    assert result.exit_code == 1
    assert calls["upsert"] is None


def test_register_exits_nonzero_when_the_indexes_time_out(monkeypatch):
    _patch(monkeypatch)

    async def fake_indexes(collection: object, settings: object) -> list:
        raise TimeoutError("timed out waiting for indexes")

    monkeypatch.setattr(register_module, "create_and_wait_chunks_indexes", fake_indexes)

    result = register(_input())

    assert result.exit_code == 1
