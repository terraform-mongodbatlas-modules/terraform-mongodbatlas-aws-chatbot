from __future__ import annotations

from pathlib import Path

import pytest
import typer
from pydantic import SecretStr

import hybrid_search.cli.cmd_register_corpus as cmd_module
from hybrid_search.cli.cmd_register_corpus import cmd_register_corpus
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


def _corpus(tmp_path: Path) -> Path:
    (tmp_path / "corpus.yaml").write_text(
        "collection: healthcare\n"
        "display_name: Springfield Health\n"
        "description: Member services\n"
        "icon: /public/logo_light.svg\n"
    )
    (tmp_path / "queries.yaml").write_text("- label: Marge\n  message: What is due?\n")
    (tmp_path / "system_prompt.txt").write_text("Answer as Springfield Health.")
    (tmp_path / "docs").mkdir()
    return tmp_path


def test_cmd_register_corpus_passes_the_manifest(monkeypatch, tmp_path):
    calls = _capture(monkeypatch)
    corpus = _corpus(tmp_path)

    cmd_register_corpus(corpus=corpus, force=True)

    input = calls[0]
    assert input.collection == "healthcare"
    assert input.display_name == "Springfield Health"
    assert input.description == "Member services"
    assert input.icon == "/public/logo_light.svg"
    assert input.demo_queries_path == (corpus / "queries.yaml").resolve()
    assert input.system_prompt_path == (corpus / "system_prompt.txt").resolve()
    assert input.dirs == [(corpus / "docs").resolve()]
    assert input.force is True


def test_cmd_register_corpus_exits_on_manifest_error(monkeypatch, tmp_path):
    _capture(monkeypatch)

    with pytest.raises(typer.Exit) as excinfo:
        cmd_register_corpus(corpus=tmp_path, force=False)

    assert excinfo.value.exit_code == 1


def test_cmd_register_corpus_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr(cmd_module, "get_settings", _settings)
    monkeypatch.setattr(cmd_module, "apply_log_level", lambda _level: None)
    monkeypatch.setattr(cmd_module, "register", lambda _input: RegisterResult(exit_code=1))
    corpus = _corpus(tmp_path)

    with pytest.raises(typer.Exit) as excinfo:
        cmd_register_corpus(corpus=corpus, force=False)

    assert excinfo.value.exit_code == 1
