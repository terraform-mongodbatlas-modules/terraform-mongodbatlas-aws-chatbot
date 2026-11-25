from __future__ import annotations

from pathlib import Path

import pytest
import typer
from pydantic import SecretStr

import hybrid_search.cli.cmd_register as cmd_module
from hybrid_search.cli.cmd_register import cmd_register
from hybrid_search.cli.register_logic import RegisterResult
from hybrid_search.settings import HybridSearchSettings


def _settings() -> HybridSearchSettings:
    return HybridSearchSettings(mongodb_uri=SecretStr("mongodb://localhost"))


def _capture(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(cmd_module, "get_settings", _settings)
    monkeypatch.setattr(cmd_module, "apply_log_level", lambda _level: None)
    monkeypatch.setattr(
        cmd_module,
        "register",
        lambda input: calls.append(input) or RegisterResult(),
    )
    return calls


def test_cmd_register_passes_every_option(monkeypatch):
    calls = _capture(monkeypatch)

    cmd_register(
        collection="healthcare",
        display_name="Healthcare",
        description="Clinical notes",
        icon="/public/health.svg",
        demo_queries=Path("/queries.yaml"),
        system_prompt=Path("/prompt.txt"),
        dirs=[Path("/docs")],
        force=True,
    )

    input = calls[0]
    assert input.collection == "healthcare"
    assert input.display_name == "Healthcare"
    assert input.description == "Clinical notes"
    assert input.icon == "/public/health.svg"
    assert input.demo_queries_path == Path("/queries.yaml")
    assert input.system_prompt_path == Path("/prompt.txt")
    assert input.dirs == [Path("/docs")]
    assert input.force is True


def test_cmd_register_exits_nonzero(monkeypatch):
    monkeypatch.setattr(cmd_module, "get_settings", _settings)
    monkeypatch.setattr(cmd_module, "apply_log_level", lambda _level: None)
    monkeypatch.setattr(cmd_module, "register", lambda _input: RegisterResult(exit_code=1))

    with pytest.raises(typer.Exit) as excinfo:
        cmd_register(
            collection="healthcare",
            display_name="Healthcare",
            description=None,
            icon=None,
            demo_queries=None,
            system_prompt=None,
            dirs=[],
            force=False,
        )

    assert excinfo.value.exit_code == 1
