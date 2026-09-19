"""Top-level command-line interface."""

from pathlib import Path
from typing import Annotated

import typer

from education_roi import __version__
from education_roi.config.paths import ProjectPaths

app = typer.Typer(
    name="edu-roi",
    help="Reproducible education and career pathway analysis.",
    no_args_is_help=True,
)
data_app = typer.Typer(help="Discover, update, and validate source datasets.")
app.add_typer(data_app, name="data")


def version_callback(value: bool) -> None:
    """Print the installed version and exit."""
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Education Path ROI command line."""


@app.command()
def paths(
    root: Annotated[
        Path | None,
        typer.Option(help="Project root. Defaults to EDU_ROI_ROOT or the current directory."),
    ] = None,
) -> None:
    """Display resolved project data and result paths."""
    resolved = ProjectPaths.from_environment(root)
    typer.echo(f"root={resolved.root}")
    typer.echo(f"data={resolved.data}")
    typer.echo(f"results={resolved.results}")


@data_app.command("check")
def data_check() -> None:
    """Check configured authoritative sources for releases."""
    typer.echo("No source adapters are configured yet.")


@data_app.command("update")
def data_update(dataset: Annotated[str, typer.Argument(help="Stable dataset identifier.")]) -> None:
    """Download and register a dataset release through its source adapter."""
    typer.echo(f"No source adapter is configured for {dataset}.")
    raise typer.Exit(code=2)


@data_app.command("validate")
def data_validate() -> None:
    """Validate registered artifact integrity and metadata."""
    typer.echo("No registered artifacts were found.")


if __name__ == "__main__":  # pragma: no cover
    app()
