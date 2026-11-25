"""The background startup task honors the same switches as the CLI paths."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

import hybrid_search.startup as startup_module
from hybrid_search.chatbot_profiles import DemoQuery
from hybrid_search.settings import DEFAULT_RAG_SYSTEM_PROMPT, HybridSearchSettings


class _FakeClient:
    def __init__(self) -> None:
        self.closed = False

    def __getitem__(self, key: str) -> _FakeClient:
        # mongo.py subscripts client[db][collection]; the patched helpers ignore
        # the collection, so returning self is enough.
        return self

    def close(self) -> None:
        self.closed = True


def _settings(**overrides: object) -> HybridSearchSettings:
    base: dict[str, object] = {"mongodb_uri": SecretStr("mongodb://localhost")}
    base.update(overrides)
    return HybridSearchSettings(**base)


def _patch_startup(monkeypatch, client: _FakeClient) -> tuple[dict[str, int], list[dict]]:
    calls = {"indexes": 0, "ingest": 0}
    upserts: list[dict] = []

    async def fake_connect(settings, **kwargs):
        return client

    async def fake_indexes(collection, settings):
        calls["indexes"] += 1
        return []

    async def fake_ingest(*args, **kwargs):
        calls["ingest"] += 1

    async def fake_upsert(registry, *, name: str, set_fields, insert_fields=None):
        upserts.append({"name": name, "set_fields": set_fields, "insert_fields": insert_fields})

    monkeypatch.setattr(startup_module, "connect_with_retry", fake_connect)
    monkeypatch.setattr(startup_module, "create_and_wait_chunks_indexes", fake_indexes)
    monkeypatch.setattr(startup_module, "ingest_dirs", fake_ingest)
    monkeypatch.setattr(startup_module, "load_demo_queries", _bundled_queries)
    monkeypatch.setattr(startup_module.chatbot_profiles, "upsert_profile", fake_upsert)
    return calls, upserts


def _bundled_queries(path: object) -> list[DemoQuery]:
    return [DemoQuery(label="A", message="What is A?")]


@pytest.mark.asyncio
async def test_startup_task_creates_and_ingests_by_default(monkeypatch):
    client = _FakeClient()
    calls, _upserts = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings())

    assert calls == {"indexes": 1, "ingest": 1}
    assert client.closed is True


@pytest.mark.asyncio
async def test_startup_task_skips_ingest_when_flag_set(monkeypatch):
    client = _FakeClient()
    calls, _upserts = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings(skip_ingest=True))

    assert calls == {"indexes": 1, "ingest": 0}


@pytest.mark.asyncio
async def test_startup_task_skips_index_creation_when_flag_set(monkeypatch):
    client = _FakeClient()
    calls, _upserts = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings(skip_index_creation=True))

    assert calls == {"indexes": 0, "ingest": 1}


@pytest.mark.asyncio
async def test_startup_upserts_the_config_even_when_skipping_work(monkeypatch):
    client = _FakeClient()
    calls, upserts = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings(skip_index_creation=True, skip_ingest=True))

    assert calls == {"indexes": 0, "ingest": 0}
    assert len(upserts) == 1


@pytest.mark.asyncio
async def test_startup_config_carries_the_prompt_and_bundled_queries(monkeypatch):
    client = _FakeClient()
    _calls, upserts = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings(rag_system_prompt="Answer briefly."))

    assert upserts == [
        {
            "name": "chunks",
            "set_fields": {
                "system_prompt": "Answer briefly.",
                "queries": [{"label": "A", "message": "What is A?"}],
            },
            "insert_fields": {"display_name": "chunks"},
        }
    ]


@pytest.mark.asyncio
async def test_startup_config_still_writes_the_prompt_without_the_demo_file(monkeypatch):
    client = _FakeClient()
    _calls, upserts = _patch_startup(monkeypatch, client)

    def missing(path: object) -> list[DemoQuery]:
        raise FileNotFoundError(path)

    monkeypatch.setattr(startup_module, "load_demo_queries", missing)

    await startup_module.run_startup_task(_settings())

    assert upserts[0]["set_fields"] == {"system_prompt": DEFAULT_RAG_SYSTEM_PROMPT}
    assert "queries" not in upserts[0]["set_fields"]
