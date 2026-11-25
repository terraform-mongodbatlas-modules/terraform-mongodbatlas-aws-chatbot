from __future__ import annotations

import typer

from hybrid_search.cli.index_create_logic import IndexCreateInput, index_create
from hybrid_search.settings import apply_log_level, get_settings


def cmd_index_create(
    recreate: bool = typer.Option(
        False,
        "--recreate",
        help="Drop and recreate indexes that are FAILED",
    ),
):
    settings = get_settings().model_copy(update={"skip_index_creation": False})
    apply_log_level(settings.log_level)
    result = index_create(IndexCreateInput(settings=settings, recreate=recreate))
    if result.exit_code != 0:
        if result.error:
            typer.echo(result.error, err=True)
        raise typer.Exit(result.exit_code)
