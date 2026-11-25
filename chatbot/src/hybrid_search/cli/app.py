import typer

from hybrid_search.cli.cmd_index_create import cmd_index_create
from hybrid_search.cli.cmd_ingest import cmd_ingest
from hybrid_search.cli.cmd_query import cmd_query
from hybrid_search.cli.cmd_register import cmd_register
from hybrid_search.cli.cmd_register_corpus import cmd_register_corpus

app = typer.Typer()
# Flat commands keep the `hybrid-search <command> --option ...` shape; a sub-typer
# would force `hybrid-search <group> <command>` for every entry point.
app.command(name="index-create", help="Atlas search indexes")(cmd_index_create)
app.command(name="ingest", help="Ingest documents into the chunks collection")(cmd_ingest)
app.command(name="query")(cmd_query)
app.command(name="register", help="Register a chunks collection as a chat profile")(cmd_register)
app.command(name="register-corpus", help="Register a corpus directory as a chat profile")(
    cmd_register_corpus
)


def main():
    app()
