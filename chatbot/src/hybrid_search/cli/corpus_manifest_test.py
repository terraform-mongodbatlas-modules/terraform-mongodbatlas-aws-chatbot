from __future__ import annotations

from pathlib import Path

import pytest

from hybrid_search.cli.corpus_manifest import (
    DEFAULT_DOCS,
    DEFAULT_QUERIES,
    DEFAULT_SYSTEM_PROMPT,
    MANIFEST_NAME,
    CorpusManifestError,
    load_manifest,
)


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_loads_manifest_and_convention_files(tmp_path: Path):
    _write(tmp_path, MANIFEST_NAME, "collection: healthcare\ndisplay_name: Springfield Health\n")
    queries = _write(tmp_path, DEFAULT_QUERIES, "- label: Marge\n  message: What is due?\n")
    prompt = _write(tmp_path, DEFAULT_SYSTEM_PROMPT, "Answer as Springfield Health.")
    docs = tmp_path / DEFAULT_DOCS
    docs.mkdir()

    manifest = load_manifest(tmp_path)

    assert manifest.collection == "healthcare"
    assert manifest.display_name == "Springfield Health"
    assert manifest.queries == queries.resolve()
    assert manifest.system_prompt == prompt.resolve()
    assert manifest.docs == [docs.resolve()]


def test_explicit_paths_win(tmp_path: Path):
    _write(
        tmp_path,
        MANIFEST_NAME,
        "collection: c\n"
        "display_name: C\n"
        "queries: custom/questions.yaml\n"
        "system_prompt: prompts/persona.txt\n"
        "docs: [one, two]\n",
    )

    manifest = load_manifest(tmp_path)

    assert manifest.queries == (tmp_path / "custom/questions.yaml").resolve()
    assert manifest.system_prompt == (tmp_path / "prompts/persona.txt").resolve()
    assert manifest.docs == [(tmp_path / "one").resolve(), (tmp_path / "two").resolve()]


def test_relative_corpus_dir_resolves_convention_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    corpus = tmp_path / "healthcare"
    _write(corpus, MANIFEST_NAME, "collection: c\ndisplay_name: C\n")
    queries = _write(corpus, DEFAULT_QUERIES, "- label: Marge\n  message: What is due?\n")
    prompt = _write(corpus, DEFAULT_SYSTEM_PROMPT, "Answer as C.")
    monkeypatch.chdir(tmp_path)

    manifest = load_manifest(Path("healthcare"))

    assert manifest.queries == queries.resolve()
    assert manifest.system_prompt == prompt.resolve()


def test_missing_convention_files_are_left_out(tmp_path: Path):
    _write(tmp_path, MANIFEST_NAME, "collection: c\ndisplay_name: C\n")

    manifest = load_manifest(tmp_path)

    assert manifest.queries is None
    assert manifest.system_prompt is None
    assert manifest.docs == []


def test_explicit_empty_docs_stays_empty(tmp_path: Path):
    _write(tmp_path, MANIFEST_NAME, "collection: c\ndisplay_name: C\ndocs: []\n")
    (tmp_path / DEFAULT_DOCS).mkdir()

    assert load_manifest(tmp_path).docs == []


def test_missing_manifest_raises(tmp_path: Path):
    with pytest.raises(CorpusManifestError, match="not found"):
        load_manifest(tmp_path)


def test_missing_display_name_raises(tmp_path: Path):
    _write(tmp_path, MANIFEST_NAME, "collection: c\n")

    with pytest.raises(CorpusManifestError, match="display_name"):
        load_manifest(tmp_path)
