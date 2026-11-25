from __future__ import annotations

import pytest
import typer
from pydantic import SecretStr

import hybrid_search.cli.cmd_index_create as cmd_module
import hybrid_search.cli.index_create_logic as logic
from hybrid_search.cli.cmd_index_create import cmd_index_create
from hybrid_search.cli.index_create_logic import IndexCreateInput, IndexCreateResult
from hybrid_search.settings import HybridSearchSettings


def _settings() -> HybridSearchSettings:
    return HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        log_level="DEBUG",
    )


def test_cmd_index_create_applies_settings_log_level(monkeypatch):
    settings = _settings()
    applied: list[str] = []
    monkeypatch.setattr(cmd_module, "get_settings", lambda: settings)
    monkeypatch.setattr(cmd_module, "apply_log_level", applied.append)
    monkeypatch.setattr(cmd_module, "index_create", lambda _input: IndexCreateResult())

    cmd_index_create(recreate=False)

    assert applied == ["DEBUG"]


def test_cmd_index_create_passes_recreate(monkeypatch):
    inputs: list[IndexCreateInput] = []
    monkeypatch.setattr(cmd_module, "get_settings", _settings)
    monkeypatch.setattr(cmd_module, "apply_log_level", lambda _level: None)
    monkeypatch.setattr(
        cmd_module,
        "index_create",
        lambda input: inputs.append(input) or IndexCreateResult(),
    )

    cmd_index_create(recreate=True)

    assert inputs[0].recreate is True


def test_cmd_index_create_prints_the_error(monkeypatch, capsys):
    monkeypatch.setattr(cmd_module, "get_settings", _settings)
    monkeypatch.setattr(cmd_module, "apply_log_level", lambda _level: None)
    monkeypatch.setattr(
        cmd_module,
        "index_create",
        lambda _input: IndexCreateResult(exit_code=1, error="model is not enabled"),
    )

    with pytest.raises(typer.Exit):
        cmd_index_create(recreate=False)

    assert "model is not enabled" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_index_create_passes_recreate_and_reports_the_error(monkeypatch):
    captured: dict[str, object] = {}

    class _Client:
        def close(self) -> None:
            captured["closed"] = True

    async def failing_indexes(collection: object, settings: object, **kwargs: object) -> None:
        captured.update(kwargs)
        raise RuntimeError("index chunks.autoembed_idx failed: model is not enabled")

    monkeypatch.setattr(logic, "get_client", lambda _settings: _Client())
    monkeypatch.setattr(logic, "chunks_collection", lambda _client, _settings: object())
    monkeypatch.setattr(logic, "create_and_wait_chunks_indexes", failing_indexes)

    result = await logic._index_create_async(IndexCreateInput(settings=_settings(), recreate=True))

    assert captured["recreate_failed"] is True
    assert captured["create_attempts"] == 3
    assert captured["closed"] is True
    assert result.exit_code == 1
    assert result.error == "index chunks.autoembed_idx failed: model is not enabled"
