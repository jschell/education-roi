"""Top-level command-line interface."""

import json
from pathlib import Path
from typing import Annotated

import typer

from education_roi import __version__
from education_roi.cashflow import ReturnPerspective
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds import (
    IPEDSArchiveError,
    IPEDSCatalogError,
    IPEDSReleaseCatalog,
    IPEDSValueProvider,
    compare_release_catalogs,
)
from education_roi.provenance.adapters import SourceConfiguration
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.store import ArtifactStore, Registry
from education_roi.reproduction.bundle import BundleIntegrityError, verify_reproduction_bundle
from education_roi.reproduction.runner import run_provisional_reproduction
from education_roi.reproduction.synthetic import (
    SYNTHETIC_FIXTURE_VERSION,
    synthetic_provisional_request,
)
from education_roi.scenarios import (
    ComparisonBundleError,
    EarningsFixture,
    FixtureValueProvider,
    ScenarioAnalysisError,
    ScenarioComparisonError,
    ScenarioDocument,
    ScenarioGraphError,
    ScenarioResolutionError,
    ScenarioValidationError,
    analyze_scenario,
    compare_scenarios,
    load_scenario_file,
    resolve_configuration_graph,
    resolve_scenario_graph,
    verify_comparison_bundle,
    write_comparison_bundle,
)

app = typer.Typer(
    name="edu-roi",
    help="Reproducible education and career pathway analysis.",
    no_args_is_help=True,
)
data_app = typer.Typer(help="Discover, update, and validate source datasets.")
reproduce_app = typer.Typer(help="Write and verify Zhang reproduction artifacts.")
scenario_app = typer.Typer(help="Validate scenario definitions and reference graphs.")
ipeds_app = typer.Typer(help="Inspect and register authoritative IPEDS releases.")
app.add_typer(data_app, name="data")
app.add_typer(reproduce_app, name="reproduce")
app.add_typer(scenario_app, name="scenario")
app.add_typer(ipeds_app, name="ipeds")


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


@ipeds_app.command("compare-inventory")
def ipeds_compare_inventory(
    reviewed: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    observed: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Observed catalog JSON."),
    ],
    fail_on_change: Annotated[
        bool,
        typer.Option(help="Exit 1 when differences require review."),
    ] = False,
) -> None:
    """Compare complete IPEDS inventory snapshots without promoting changes."""
    try:
        comparison = compare_release_catalogs(
            IPEDSReleaseCatalog.from_file(reviewed),
            IPEDSReleaseCatalog.from_file(observed),
        )
    except IPEDSCatalogError as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    payload = comparison.model_dump(mode="json")
    payload["status"] = "REVIEW_REQUIRED" if comparison.review_required else "UNCHANGED"
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if comparison.review_required and fail_on_change:
        raise typer.Exit(code=1)


@reproduce_app.command("verify-bundle")
def reproduce_verify_bundle(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
) -> None:
    """Verify a deterministic reproduction bundle and every recorded digest."""
    try:
        verified = verify_reproduction_bundle(bundle)
    except BundleIntegrityError as error:
        typer.echo(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        raise typer.Exit(code=1) from None
    typer.echo(
        json.dumps(
            {
                "status": "VALID",
                "run_id": verified.run_id,
                "certification_status": verified.certification_status,
                "files_checked": len(verified.artifacts),
            },
            sort_keys=True,
        )
    )


@reproduce_app.command("synthetic-run")
def reproduce_synthetic_run(
    results_root: Annotated[Path, typer.Option(help="Directory that will contain the run.")],
    run_id: Annotated[str, typer.Option(help="New immutable run identifier.")] = "synthetic-run",
) -> None:
    """Run the explicitly synthetic clean-environment reproduction fixture."""
    result = run_provisional_reproduction(
        synthetic_provisional_request(), results_root=results_root, run_id=run_id
    )
    typer.echo(
        json.dumps(
            {
                "status": "WRITTEN",
                "certification_status": result.report.certification_status.value,
                "fixture_version": SYNTHETIC_FIXTURE_VERSION,
                "run_id": result.bundle.run_id,
                "bundle_path": str(result.bundle.path),
                "warning": "SYNTHETIC FIXTURE; NOT A PAPER REPRODUCTION",
            },
            sort_keys=True,
        )
    )


@scenario_app.command("schema")
def scenario_schema() -> None:
    """Print the canonical JSON Schema for scenario document version 1.0."""
    typer.echo(
        json.dumps(
            ScenarioDocument.model_json_schema(),
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@scenario_app.command("validate")
def scenario_validate(
    files: Annotated[
        list[Path],
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Scenario YAML files."),
    ],
) -> None:
    """Validate scenario files, resolve references, and emit stable identities."""
    try:
        documents = tuple(load_scenario_file(path) for path in files)
        graph = resolve_scenario_graph(documents)
    except (ScenarioValidationError, ScenarioGraphError) as error:
        typer.echo(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps({"status": "VALID", **graph.as_dict()}, sort_keys=True))


@scenario_app.command("resolve")
def scenario_resolve(
    files: Annotated[
        list[Path],
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Scenario YAML files."),
    ],
    fixture_values: Annotated[
        Path,
        typer.Option(
            exists=True, dir_okay=False, readable=True, help="Synthetic/test fixture values."
        ),
    ],
) -> None:
    """Resolve scenario values from an explicit fixture provider."""
    try:
        documents = tuple(load_scenario_file(path) for path in files)
        graph = resolve_scenario_graph(documents)
        provider = FixtureValueProvider.from_file(fixture_values)
        resolved = resolve_configuration_graph(graph, provider)
    except (ScenarioValidationError, ScenarioGraphError, ScenarioResolutionError) as error:
        typer.echo(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(resolved.as_dict(), sort_keys=True))


@scenario_app.command("resolve-ipeds")
def scenario_resolve_ipeds(
    files: Annotated[
        list[Path],
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Scenario YAML files."),
    ],
    root: Annotated[
        Path | None,
        typer.Option(help="Project root containing the validated artifact registry."),
    ] = None,
) -> None:
    """Resolve IPEDS values from validated immutable registry artifacts."""
    paths = ProjectPaths.from_environment(root)
    registry_path = paths.data / "manifests" / "registry.sqlite"
    if not registry_path.is_file():
        typer.echo(
            json.dumps(
                {"error": f"artifact registry not found: {registry_path}", "status": "INVALID"},
                sort_keys=True,
            )
        )
        raise typer.Exit(code=1)
    try:
        documents = tuple(load_scenario_file(path) for path in files)
        graph = resolve_scenario_graph(documents)
        scenarios = {scenario.id: scenario for scenario in graph.scenarios}
        provider = IPEDSValueProvider(Registry(registry_path), paths.data / "raw", scenarios)
        resolved = resolve_configuration_graph(graph, provider)
    except (
        IPEDSArchiveError,
        ScenarioValidationError,
        ScenarioGraphError,
        ScenarioResolutionError,
    ) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(resolved.as_dict(), sort_keys=True))


@scenario_app.command("analyze")
def scenario_analyze(
    scenario_id: Annotated[str, typer.Option(help="Scenario ID to analyze.")],
    files: Annotated[
        list[Path],
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Scenario YAML files."),
    ],
    fixture_values: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Resolved-value fixture."),
    ],
    earnings_fixture: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Age-earnings fixture."),
    ],
    perspective: Annotated[
        ReturnPerspective, typer.Option(help="Return perspective.")
    ] = ReturnPerspective.CONDITIONAL_GRADUATE,
) -> None:
    """Analyze a scenario against its counterfactual using explicit fixtures."""
    try:
        documents = tuple(load_scenario_file(path) for path in files)
        source_graph = resolve_scenario_graph(documents)
        provider = FixtureValueProvider.from_file(fixture_values)
        resolved_graph = resolve_configuration_graph(source_graph, provider)
        earnings = EarningsFixture.from_file(earnings_fixture)
        analysis = analyze_scenario(
            source_graph, resolved_graph, earnings, scenario_id, perspective
        )
    except (
        ScenarioValidationError,
        ScenarioGraphError,
        ScenarioResolutionError,
        ScenarioAnalysisError,
    ) as error:
        typer.echo(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(analysis.as_dict(), sort_keys=True))


@app.command("compare")
def scenario_compare(
    scenario_ids: Annotated[
        list[str], typer.Option("--scenario-id", help="Scenario ID; repeat at least twice.")
    ],
    files: Annotated[
        list[Path],
        typer.Argument(
            exists=True, dir_okay=False, readable=True, help="Connected scenario YAML files."
        ),
    ],
    fixture_values: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Resolved-value fixture."),
    ],
    earnings_fixture: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True, help="Age-earnings fixture.")
    ],
    results_root: Annotated[Path, typer.Option(help="Parent directory for immutable runs.")],
    run_id: Annotated[str, typer.Option(help="New immutable run identifier.")],
    perspective: Annotated[
        ReturnPerspective, typer.Option(help="Return perspective.")
    ] = ReturnPerspective.CONDITIONAL_GRADUATE,
) -> None:
    """Compare scenarios and write a reproducible, integrity-protected run bundle."""
    try:
        documents = tuple(load_scenario_file(path) for path in files)
        source_graph = resolve_scenario_graph(documents)
        resolved = resolve_configuration_graph(
            source_graph, FixtureValueProvider.from_file(fixture_values)
        )
        earnings = EarningsFixture.from_file(earnings_fixture)
        report = compare_scenarios(
            source_graph, resolved, earnings, tuple(scenario_ids), perspective
        )
        bundle = write_comparison_bundle(
            results_root / run_id,
            scenario_files=tuple(files),
            source_graph=source_graph,
            resolved_graph=resolved,
            earnings_fixture=earnings,
            report=report,
        )
    except (
        ScenarioValidationError,
        ScenarioGraphError,
        ScenarioResolutionError,
        ScenarioAnalysisError,
        ScenarioComparisonError,
        ComparisonBundleError,
    ) as error:
        typer.echo(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        raise typer.Exit(code=1) from None
    typer.echo(
        json.dumps(
            {
                "status": report.status.value,
                "provisional": report.provisional,
                "run_id": run_id,
                "bundle_path": str(bundle),
                "report_hash": report.report_hash,
            },
            sort_keys=True,
        )
    )


@scenario_app.command("verify-bundle")
def scenario_verify_bundle(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
) -> None:
    """Verify every recorded comparison-bundle byte and digest."""
    try:
        manifest = verify_comparison_bundle(bundle)
    except ComparisonBundleError as error:
        typer.echo(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        raise typer.Exit(code=1) from None
    files = manifest.get("files")
    if not isinstance(files, list):  # pragma: no cover - verifier enforces this
        raise typer.Exit(code=1)
    typer.echo(
        json.dumps(
            {
                "status": "VALID",
                "report_hash": manifest["report_hash"],
                "files_checked": len(files),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    app()
