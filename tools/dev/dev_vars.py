"""Generate dev.tfvars for the chatbot workspace tests."""

from pathlib import Path

import typer

app = typer.Typer()

WORKSPACE_DIR = Path(__file__).parent.parent.parent / "tests" / "workspace_chatbot_examples"
DEV_TFVARS = WORKSPACE_DIR / "dev.tfvars"


@app.command()
def chatbot(env: str, owner: str) -> None:
    """Write extra_tags to dev.tfvars so CI tags the resources it creates."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    DEV_TFVARS.write_text(
        f'extra_tags = {{\n  "mongodb-env"   = "{env}"\n  "mongodb-owner" = "{owner}"\n}}\n'
    )
    typer.echo(f"Generated {DEV_TFVARS}")


@app.command()
def org(org_id: str) -> None:
    """Generate org_id-only dev.tfvars, used by the synced dev-vars-org recipe."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    DEV_TFVARS.write_text(f'org_id = "{org_id}"\n')
    typer.echo(f"Generated {DEV_TFVARS}")


if __name__ == "__main__":
    app()
