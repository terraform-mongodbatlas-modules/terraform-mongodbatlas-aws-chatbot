"""The background startup task honors the same switches as the CLI paths."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

import hybrid_search.startup as startup_module
from hybrid_search.settings import HybridSearchSettings


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


def _patch_startup(monkeypatch, client: _FakeClient) -> dict[str, int]:
    calls = {"create": 0, "wait": 0, "ingest": 0}

    async def fake_connect(settings, **kwargs):
        return client

    async def fake_create(collection, settings):
        calls["create"] += 1

    async def fake_wait(collection, settings, **kwargs):
        calls["wait"] += 1

    async def fake_ingest(*args, **kwargs):
        calls["ingest"] += 1

    monkeypatch.setattr(startup_module, "connect_with_retry", fake_connect)
    monkeypatch.setattr(startup_module, "create_chunks_indexes_if_missing", fake_create)
    monkeypatch.setattr(startup_module, "wait_chunks_indexes_ready", fake_wait)
    monkeypatch.setattr(startup_module, "ingest_dirs", fake_ingest)
    return calls


@pytest.mark.asyncio
async def test_startup_task_creates_and_ingests_by_default(monkeypatch):
    client = _FakeClient()
    calls = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings())

    assert calls == {"create": 1, "wait": 1, "ingest": 1}
    assert client.closed is True


@pytest.mark.asyncio
async def test_startup_task_skips_ingest_when_flag_set(monkeypatch):
    client = _FakeClient()
    calls = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings(skip_ingest=True))

    assert calls == {"create": 1, "wait": 1, "ingest": 0}


@pytest.mark.asyncio
async def test_startup_task_skips_index_creation_when_flag_set(monkeypatch):
    client = _FakeClient()
    calls = _patch_startup(monkeypatch, client)

    await startup_module.run_startup_task(_settings(skip_index_creation=True))

    assert calls == {"create": 0, "wait": 0, "ingest": 1}
