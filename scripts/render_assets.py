#!/usr/bin/env python3
"""Render the assets tree that ships as the CodeBuild secondary source.

Stdlib only: Terraform runs this from a `local-exec` on a machine that has only
Python and the AWS CLI. The tree mirrors the vendored `chatbot/assets/` paths and
is always complete, so the buildspec can copy it over the app root wholesale and
every file the Dockerfile `COPY`s exists.

Order: copy the vendored defaults, render `demo_queries.yaml` from `queries`,
replace `document_dirs/` when the caller supplies folders, then overlay
`assets_dir` last so a caller's files win. Files are copied byte for byte, so a
PDF passes through with no conversion.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-dir", required=True)
    parser.add_argument("--staging-dir", required=True)
    parser.add_argument("--queries-b64", default="")
    parser.add_argument("--document-dirs-b64", default="")
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


def replace_document_dirs(staging: Path, entries: list[str]) -> None:
    target = staging / "document_dirs"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for entry in entries:
        source = Path(entry)
        if source.is_dir():
            shutil.copytree(source, target / source.name)
        else:
            shutil.copy2(source, target / source.name)


def main() -> None:
    args = parse_args()
    module_dir = Path(args.module_dir).resolve()
    staging = Path(args.staging_dir)
    vendored = module_dir / "chatbot" / "assets"

    if not vendored.is_dir():
        raise SystemExit(f"vendored assets not found at {vendored}")

    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(vendored, staging)

    queries = decode_json(args.queries_b64)
    if queries:
        render_queries(staging, queries)

    document_dirs = decode_json(args.document_dirs_b64)
    if document_dirs:
        replace_document_dirs(staging, document_dirs)

    if args.assets_dir:
        overlay = Path(args.assets_dir)
        if not overlay.is_dir():
            raise SystemExit(f"--assets-dir {args.assets_dir} is not a directory")
        shutil.copytree(overlay, staging, dirs_exist_ok=True)

    print(f"Rendered assets tree at {staging}")


if __name__ == "__main__":
    main()
