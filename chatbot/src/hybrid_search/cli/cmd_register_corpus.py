from __future__ import annotations

from pathlib import Path

import typer

from hybrid_search.cli.corpus_manifest import CorpusManifestError, load_manifest
from hybrid_search.cli.register_logic import RegisterInput, register
from hybrid_search.settings import apply_log_level, get_settings


def cmd_register_corpus(
    corpus: Path = typer.Option(
        ...,
        "--corpus",
        help="Directory holding a corpus.yaml manifest.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-ingest even when the content hash is unchanged.",
    ),
):
    settings = get_settings()
    apply_log_level(settings.log_level)
    try:
        manifest = load_manifest(corpus)
    except CorpusManifestError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    result = register(
        RegisterInput(
            settings=settings,
            collection=manifest.collection,
            display_name=manifest.display_name,
            description=manifest.description,
            icon=manifest.icon,
            demo_queries_path=manifest.queries,
            system_prompt_path=manifest.system_prompt,
            dirs=manifest.docs or [],
            force=force,
        )
    )
    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)
