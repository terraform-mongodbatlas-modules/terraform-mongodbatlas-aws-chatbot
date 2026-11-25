from __future__ import annotations

from pathlib import Path

import typer

from hybrid_search.cli.register_logic import RegisterInput, register
from hybrid_search.settings import apply_log_level, get_settings


def cmd_register(
    collection: str = typer.Option(
        ...,
        "--collection",
        help="Chunks collection to register as a chat profile.",
    ),
    display_name: str = typer.Option(
        ...,
        "--display-name",
        help="Label shown in the chat profile dropdown.",
    ),
    description: str | None = typer.Option(
        None,
        "--description",
        help="Tooltip text for the profile.",
    ),
    icon: str | None = typer.Option(
        None,
        "--icon",
        help="Image URL the app serves, for example /public/logo_light.svg.",
    ),
    demo_queries: Path | None = typer.Option(
        None,
        "--demo-queries",
        help="YAML file of starter questions, as a list or under `queries:`.",
    ),
    system_prompt: Path | None = typer.Option(
        None,
        "--system-prompt",
        help="Text file holding the RAG system prompt.",
    ),
    dirs: list[Path] = typer.Option(
        [],
        "--dir",
        help="Directory to ingest into the collection; repeat for more.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-ingest even when the content hash is unchanged.",
    ),
):
    settings = get_settings()
    apply_log_level(settings.log_level)
    result = register(
        RegisterInput(
            settings=settings,
            collection=collection,
            display_name=display_name,
            description=description,
            icon=icon,
            demo_queries_path=demo_queries,
            system_prompt_path=system_prompt,
            dirs=dirs,
            force=force,
        )
    )
    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)
