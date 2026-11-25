"""Load a corpus directory's ``corpus.yaml`` manifest.

A corpus directory describes itself: ``collection`` and ``display_name`` are
required, and the optional ``description``, ``icon``, ``queries``,
``system_prompt``, and ``docs`` mirror what ``hybrid-search register`` accepts.
The path fields default to ``queries.yaml``, ``system_prompt.txt``, and
``docs/`` beside the manifest when those exist, so the common case names only
the collection and its label.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

MANIFEST_NAME = "corpus.yaml"
DEFAULT_QUERIES = "queries.yaml"
DEFAULT_SYSTEM_PROMPT = "system_prompt.txt"
DEFAULT_DOCS = "docs"


class CorpusManifestError(ValueError):
    pass


class CorpusManifest(BaseModel):
    collection: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str | None = None
    icon: str | None = None
    queries: Path | None = None
    system_prompt: Path | None = None
    docs: list[Path] | None = None


def load_manifest(corpus_dir: Path) -> CorpusManifest:
    manifest_path = corpus_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        msg = f"corpus manifest not found: {manifest_path}"
        raise CorpusManifestError(msg)
    try:
        data = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError as exc:
        msg = f"invalid YAML in {manifest_path}: {exc}"
        raise CorpusManifestError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{manifest_path} must hold a mapping of manifest fields"
        raise CorpusManifestError(msg)
    try:
        manifest = CorpusManifest.model_validate(data)
    except ValidationError as exc:
        msg = f"invalid corpus manifest {manifest_path}: {exc}"
        raise CorpusManifestError(msg) from exc
    return manifest.model_copy(
        update={
            "queries": _optional_file(corpus_dir, manifest.queries, DEFAULT_QUERIES),
            "system_prompt": _optional_file(
                corpus_dir, manifest.system_prompt, DEFAULT_SYSTEM_PROMPT
            ),
            "docs": _docs(corpus_dir, manifest.docs),
        }
    )


def _optional_file(base: Path, path: Path | None, default_name: str) -> Path | None:
    """Resolve ``path``, or the convention file when the field is omitted."""
    if path is not None:
        return _absolute(base, path)
    # Resolve the convention path directly: it already carries ``base``, so
    # passing it back through ``_absolute`` would join ``base`` twice when the
    # caller gave a relative corpus directory.
    convention = base / default_name
    return convention.resolve() if convention.is_file() else None


def _docs(base: Path, docs: list[Path] | None) -> list[Path]:
    if docs is not None:
        return [_absolute(base, path) for path in docs]
    convention = base / DEFAULT_DOCS
    return [convention.resolve()] if convention.is_dir() else []


def _absolute(base: Path, path: Path) -> Path:
    return path if path.is_absolute() else (base / path).resolve()
