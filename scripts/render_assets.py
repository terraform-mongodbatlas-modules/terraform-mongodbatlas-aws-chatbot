#!/usr/bin/env python3
"""Render the assets tree that ships as the CodeBuild secondary source.

Stdlib only: Terraform runs this from a `local-exec` on a machine that has only
Python and the AWS CLI. The tree mirrors the vendored `chatbot/assets/` paths and
is always complete, so the buildspec can copy it over the app root wholesale and
every file the Dockerfile `COPY`s exists.

Order: copy the vendored defaults, stage the bundled corpus from the repository
docs unless `skip_repo_docs` is set, render `demo_queries.yaml` from `queries`,
replace `document_dirs/` when the caller supplies entries, then overlay
`assets_dir` last so a caller's files win. Files are copied byte for byte, so a
PDF passes through with no conversion.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
from pathlib import Path

# The bundled corpus: the repository docs, flattened to one corpus name each so a
# bare `document_dirs` entry resolves without a path. Keep this in step with
# `local.corpus_sources` in locals.tf.
CORPUS_SOURCES = {
    "README.md": "README.md",
    "architecture.md": "docs/architecture.md",
    "security-and-iam.md": "docs/security-and-iam.md",
    "why-mongodb-for-agents.md": "docs/why-mongodb-for-agents.md",
    "minimal-example.md": "examples/minimal/README.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-dir", required=True)
    parser.add_argument("--staging-dir", required=True)
    parser.add_argument("--queries-b64", default="")
    parser.add_argument("--document-dirs-b64", default="")
    parser.add_argument("--skip-repo-docs", default="false")
    parser.add_argument("--assets-dir", default="")
    return parser.parse_args()


def decode_json(value: str):
    if not value:
        return None
    return json.loads(base64.b64decode(value))


def render_queries(staging: Path, queries: dict[str, str]) -> None:
    lines = ["queries:"]
    for label in sorted(queries):
        lines.append(f"  - label: {json.dumps(label)}")
        lines.append(f"    message: {json.dumps(queries[label])}")
    (staging / "demo_queries.yaml").write_text("\n".join(lines) + "\n")


def stage_corpus(module_dir: Path, staging: Path) -> None:
    """Copy the repository docs into the staging `document_dirs/` under their flat
    corpus names, so a bare `document_dirs` entry resolves."""
    target = staging / "document_dirs"
    target.mkdir(parents=True, exist_ok=True)
    for name, source_rel in CORPUS_SOURCES.items():
        source = module_dir / source_rel
        if not source.is_file():
            raise SystemExit(f"corpus source not found: {source_rel}")
        shutil.copy2(source, target / name)


def resolve_document_entry(entry: str, module_dir: Path, skip_repo_docs: bool) -> tuple[Path, str]:
    """Resolve one `document_dirs` entry to a source path and a destination name.

    A bare name (no path separator) resolves to the bundled corpus source and
    keeps its corpus name, unless `skip_repo_docs` is set, in which case no corpus
    is staged and a bare name cannot resolve. A path with a separator resolves
    relative to the working directory; an absolute path is used as-is.
    """
    if os.path.isabs(entry) or "/" in entry or "\\" in entry:
        source, dest_name = Path(entry), Path(entry).name
    else:
        if skip_repo_docs:
            raise SystemExit(
                f"skip_repo_docs is true, so a bare document_dirs name cannot resolve: {entry}"
            )
        if entry not in CORPUS_SOURCES:
            known = ", ".join(sorted(CORPUS_SOURCES))
            raise SystemExit(
                f"bare document_dirs name is not a bundled corpus document: {entry} "
                f"(known names: {known})"
            )
        source, dest_name = module_dir / CORPUS_SOURCES[entry], entry
    if not source.exists():
        raise SystemExit(f"document_dirs entry not found: {entry} (resolved to {source})")
    return source, dest_name


def replace_document_dirs(
    staging: Path, entries: list[str], module_dir: Path, skip_repo_docs: bool
) -> None:
    target = staging / "document_dirs"
    resolved = [resolve_document_entry(entry, module_dir, skip_repo_docs) for entry in entries]
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for source, dest_name in resolved:
        if source.is_dir():
            shutil.copytree(source, target / source.name)
        else:
            shutil.copy2(source, target / dest_name)


def main() -> None:
    args = parse_args()
    module_dir = Path(args.module_dir).resolve()
    staging = Path(args.staging_dir)
    vendored = module_dir / "chatbot" / "assets"
    skip_repo_docs = args.skip_repo_docs.lower() == "true"

    if not vendored.is_dir():
        raise SystemExit(f"vendored assets not found at {vendored}")

    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(vendored, staging)

    if not skip_repo_docs:
        stage_corpus(module_dir, staging)

    queries = decode_json(args.queries_b64)
    if queries:
        render_queries(staging, queries)

    document_dirs = decode_json(args.document_dirs_b64)
    if document_dirs:
        replace_document_dirs(staging, document_dirs, module_dir, skip_repo_docs)

    if args.assets_dir:
        overlay = Path(args.assets_dir)
        if not overlay.is_dir():
            raise SystemExit(f"--assets-dir {args.assets_dir} is not a directory")
        shutil.copytree(overlay, staging, dirs_exist_ok=True)

    print(f"Rendered assets tree at {staging}")


if __name__ == "__main__":
    main()
