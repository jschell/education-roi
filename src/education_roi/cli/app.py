"""Top-level command-line interface."""

import json
from pathlib import Path
from typing import Annotated

import typer

from education_roi import __version__
from education_roi.config.paths import ProjectPaths
from education_roi.provenance.adapters import SourceConfiguration
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.store import ArtifactStore, Registry

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
def data_check(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Check configured authoritative sources for releases."""
    configured = SourceConfiguration.load(config)
    releases = [
        release.__dict__ for dataset in configured.datasets for release in dataset.discover()
    ]
    typer.echo(json.dumps(releases, indent=2))


@data_app.command("update")
def data_update(
    dataset: Annotated[str, typer.Argument(help="Stable dataset identifier.")],
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    release: Annotated[
        str | None, typer.Option(help="Release to download; defaults to last.")
    ] = None,
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Download and register a dataset release through its source adapter."""
    paths = ProjectPaths.from_environment(root)
    sources = SourceConfiguration.load(config)
    try:
        selected_dataset = sources.dataset(dataset)
    except KeyError:
        typer.echo(f"Unknown dataset: {dataset}", err=True)
        raise typer.Exit(code=2) from None
    matches = [
        item for item in selected_dataset.releases if release is None or item.release == release
    ]
    if not matches:
        typer.echo(f"Unknown release for {dataset}: {release}", err=True)
        raise typer.Exit(code=2)
    selected = matches[-1]
    registry = Registry(paths.data / "manifests" / "registry.sqlite")
    registry.add_dataset(selected_dataset.definition)
    download = HttpDownloader().download(
        selected.source_url,
        paths.data / ".downloads",
        selected_dataset.definition.allowed_domains,
    )
    try:
        manifest = ArtifactStore(paths.data / "raw", registry).register(
            download.path,
            selected_dataset.definition,
            release=selected.release,
            source_url=download.source_url,
            final_url=download.final_url,
            publication_status=selected.publication_status,
            schema_version=selected.schema_version,
            vintage=selected.vintage,
            expected_sha256=selected.expected_sha256,
        )
    finally:
        download.path.unlink(missing_ok=True)
    typer.echo(manifest.model_dump_json(indent=2))


@data_app.command("validate")
def data_validate(
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Validate registered artifact integrity and metadata."""
    paths = ProjectPaths.from_environment(root)
    registry_path = paths.data / "manifests" / "registry.sqlite"
    if not registry_path.exists():
        typer.echo("No registered artifacts were found.")
        return
    registry = Registry(registry_path)
    failures: list[dict[str, str]] = []
    artifacts = registry.list_artifacts()
    for artifact in artifacts:
        artifact_path = paths.data / "raw" / artifact.storage_path
        if not artifact_path.exists():
            failures.append({"artifact_id": artifact.artifact_id, "error": "missing bytes"})
            continue
        digest, size = sha256_file(artifact_path)
        if digest != artifact.sha256 or size != artifact.file_size:
            failures.append({"artifact_id": artifact.artifact_id, "error": "integrity mismatch"})
    typer.echo(json.dumps({"checked": len(artifacts), "failures": failures}, indent=2))
    if failures:
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
