"""Top-level command-line interface."""

import json
from pathlib import Path
from typing import Annotated

import typer

from education_roi import __version__
from education_roi.cashflow import ReturnPerspective
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds import (
    GR2023_DATASET_ID,
    GR2023_DICTIONARY_DATASET_ID,
    IPEDS_CHARGES_DATASET,
    IPEDS_DICTIONARY_DATASET,
    RETENTION_DATA,
    RETENTION_DICTIONARY,
    InstitutionHistory,
    InstitutionHistoryError,
    IPEDSArchiveError,
    IPEDSCatalogError,
    IPEDSComponent,
    IPEDSExpenseError,
    IPEDSGraduationComparisonError,
    IPEDSGraduationError,
    IPEDSProcessedArtifactConflict,
    IPEDSReleaseCatalog,
    IPEDSReleaseComparisonError,
    IPEDSRetentionError,
    IPEDSValueProvider,
    compare_charge_tables,
    compare_graduation_tables,
    compare_release_catalogs,
    register_gr2022_release,
    register_gr2023_release,
    register_retention_release,
    resolve_gr2023_bachelors,
    resolve_graduation_evidence,
    resolve_ic2023_expenses,
    resolve_retention,
    select_release,
    transform_charges_archive,
    transform_gr2022_archive,
    transform_gr2023_archive,
    transform_ic2023_expenses,
)
from education_roi.ipeds.retention_pipeline import transform_retention_archive
from education_roi.provenance.adapters import SourceConfiguration
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.provenance.store import ArtifactStore, ProvenanceError, Registry
from education_roi.reproduction.bootstrap import bootstrap_zhang_sources, resolve_vintages
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


@ipeds_app.command("register-gr2023")
def ipeds_register_gr2023(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Register the paired final GR2023 data archive and dictionary."""
    _register_gr_release(catalog, root, "2023-24-final")


@ipeds_app.command("register-gr2022")
def ipeds_register_gr2022(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Register the paired final GR2022 data archive and legacy dictionary."""
    _register_gr_release(catalog, root, "2022-23-final")


def _register_gr_release(catalog: Path, root: Path | None, release_id: str) -> None:
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.GRADUATION_RATES,
            release_id=release_id,
        )
        register = (
            register_gr2022_release if release_id == "2022-23-final" else register_gr2023_release
        )
        registered = register(release, ProjectPaths.from_environment(root))
    except (IPEDSCatalogError, ProvenanceError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps(
            {
                "data": registered.data.model_dump(mode="json"),
                "dictionary": registered.dictionary.model_dump(mode="json"),
                "status": "VALIDATED",
            },
            sort_keys=True,
        )
    )


@ipeds_app.command("register-retention")
def ipeds_register_retention(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Validate and register the paired final revised EF2023D source."""
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.FALL_RETENTION,
            release_id="2023-24-final",
        )
        registered = register_retention_release(release, ProjectPaths.from_environment(root))
    except (IPEDSCatalogError, IPEDSRetentionError, ProvenanceError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps(
            {
                "status": "VALIDATED",
                "data": registered.data.model_dump(mode="json"),
                "dictionary": registered.dictionary.model_dump(mode="json"),
            },
            sort_keys=True,
        )
    )


@ipeds_app.command("resolve-retention")
def ipeds_resolve_retention(
    unitid: Annotated[int, typer.Argument(help="Exact institution UNITID.")],
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Report one observed full-time first-year retention cohort, not completion risk."""
    paths = ProjectPaths.from_environment(root)
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.FALL_RETENTION,
            release_id="2023-24-final",
        )
        registry_path = paths.data / "manifests" / "registry.sqlite"
        if not registry_path.is_file():
            raise ValueError(f"artifact registry not found: {registry_path}")
        registry = Registry(registry_path)
        manifests = []
        for dataset_id in (RETENTION_DATA.dataset_id, RETENTION_DICTIONARY.dataset_id):
            matching = tuple(
                item
                for item in registry.list_artifacts(dataset_id, release.release_id)
                if item.state in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
            )
            if len(matching) != 1:
                raise ValueError(
                    f"expected one validated {dataset_id} artifact; found {len(matching)}"
                )
            manifests.append(matching[0])
        result = resolve_retention(
            paths.data / "raw" / manifests[0].storage_path,
            paths.data / "raw" / manifests[1].storage_path,
            release,
            manifests[0],
            manifests[1],
            unitid,
        )
    except (IPEDSCatalogError, IPEDSRetentionError, ProvenanceError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@ipeds_app.command("build-retention")
def ipeds_build_retention(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Build the immutable final EF2023D institutional retention table."""
    paths = ProjectPaths.from_environment(root)
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.FALL_RETENTION,
            release_id="2023-24-final",
        )
        registry_path = paths.data / "manifests" / "registry.sqlite"
        if not registry_path.is_file():
            raise ValueError(f"artifact registry not found: {registry_path}")
        manifests = []
        registry = Registry(registry_path)
        for dataset_id in (RETENTION_DATA.dataset_id, RETENTION_DICTIONARY.dataset_id):
            matching = tuple(
                item
                for item in registry.list_artifacts(dataset_id, release.release_id)
                if item.state in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
            )
            if len(matching) != 1:
                raise ValueError(
                    f"expected one validated {dataset_id} artifact; found {len(matching)}"
                )
            manifests.append(matching[0])
        result = transform_retention_archive(
            paths.data / "raw" / manifests[0].storage_path,
            paths.data / "raw" / manifests[1].storage_path,
            paths.data / "processed",
            manifests[0],
            manifests[1],
            release,
        )
    except (
        IPEDSCatalogError,
        IPEDSRetentionError,
        IPEDSProcessedArtifactConflict,
        ProvenanceError,
        ValueError,
    ) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps(
            {
                "status": "WRITTEN",
                "parquet_path": str(result.parquet_path),
                "manifest_path": str(result.manifest_path),
                "manifest": result.manifest.model_dump(mode="json"),
            },
            sort_keys=True,
        )
    )


@ipeds_app.command("resolve-expenses")
def ipeds_resolve_expenses(
    unitid: Annotated[int, typer.Argument(help="Exact institution UNITID.")],
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
    allow_nonfinal: Annotated[
        bool, typer.Option(help="Explicitly allow the pinned provisional expense release.")
    ] = False,
) -> None:
    """Show separate IC2023 living estimates; do not resolve incremental living cost."""
    paths = ProjectPaths.from_environment(root)
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.ACADEMIC_YEAR_CHARGES,
            release_id="2023-24-provisional",
            allow_nonfinal=allow_nonfinal,
        )
        registry_path = paths.data / "manifests" / "registry.sqlite"
        if not registry_path.is_file():
            raise ValueError(f"artifact registry not found: {registry_path}")
        manifests = _ic_manifests(Registry(registry_path), release.release_id)
        result = resolve_ic2023_expenses(
            paths.data / "raw" / manifests[0].storage_path,
            paths.data / "raw" / manifests[1].storage_path,
            release,
            manifests[0],
            manifests[1],
            unitid,
        )
    except (
        IPEDSCatalogError,
        IPEDSArchiveError,
        IPEDSExpenseError,
        ProvenanceError,
        ValueError,
    ) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


def _ic_manifests(registry: Registry, release_id: str) -> tuple[ArtifactManifest, ArtifactManifest]:
    manifests = []
    for dataset_id in (IPEDS_CHARGES_DATASET.dataset_id, IPEDS_DICTIONARY_DATASET.dataset_id):
        matching = tuple(
            item
            for item in registry.list_artifacts(dataset_id, release_id)
            if item.state in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
        )
        if len(matching) != 1:
            raise ValueError(f"expected one validated {dataset_id} artifact; found {len(matching)}")
        manifests.append(matching[0])
    return manifests[0], manifests[1]


@ipeds_app.command("build-expenses")
def ipeds_build_expenses(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
    allow_nonfinal: Annotated[
        bool, typer.Option(help="Explicitly allow the pinned provisional expense release.")
    ] = False,
) -> None:
    """Build immutable, source-paired IC2023 expense observations by living basis."""
    paths = ProjectPaths.from_environment(root)
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.ACADEMIC_YEAR_CHARGES,
            release_id="2023-24-provisional",
            allow_nonfinal=allow_nonfinal,
        )
        registry_path = paths.data / "manifests" / "registry.sqlite"
        if not registry_path.is_file():
            raise ValueError(f"artifact registry not found: {registry_path}")
        data, dictionary = _ic_manifests(Registry(registry_path), release.release_id)
        result = transform_ic2023_expenses(
            paths.data / "raw" / data.storage_path,
            paths.data / "raw" / dictionary.storage_path,
            paths.data / "processed",
            data,
            dictionary,
            release,
        )
    except (
        IPEDSCatalogError,
        IPEDSArchiveError,
        IPEDSExpenseError,
        IPEDSProcessedArtifactConflict,
        ProvenanceError,
        ValueError,
    ) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps(
            {
                "status": "WRITTEN",
                "parquet_path": str(result.parquet_path),
                "manifest_path": str(result.manifest_path),
                "manifest": result.manifest.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@ipeds_app.command("resolve-gr2023")
def ipeds_resolve_gr2023(
    unitid: Annotated[int, typer.Argument(help="Exact institution UNITID.")],
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Report one observed institutional bachelor's cohort; no probability inference."""
    paths = ProjectPaths.from_environment(root)
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.GRADUATION_RATES,
            release_id="2023-24-final",
        )
        registry_path = paths.data / "manifests" / "registry.sqlite"
        if not registry_path.is_file():
            raise ValueError(f"artifact registry not found: {registry_path}")
        data_manifest, dictionary_manifest = _gr2023_manifests(
            Registry(registry_path), release.release_id
        )
        result = resolve_gr2023_bachelors(
            paths.data / "raw" / data_manifest.storage_path,
            paths.data / "raw" / dictionary_manifest.storage_path,
            release,
            data_manifest,
            dictionary_manifest,
            unitid,
        )
    except (IPEDSCatalogError, IPEDSGraduationError, ProvenanceError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    payload = result.model_dump(mode="json")
    payload["observed_rate"] = (
        result.observation.observed_rate if result.observation is not None else None
    )
    payload["interpretation"] = (
        "observed institutional cohort, not individual completion probability"
    )
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _gr2023_manifests(
    registry: Registry, release_id: str
) -> tuple[ArtifactManifest, ArtifactManifest]:
    manifests = []
    for dataset_id in (GR2023_DATASET_ID, GR2023_DICTIONARY_DATASET_ID):
        matching = tuple(
            item
            for item in registry.list_artifacts(dataset_id, release_id)
            if item.state in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
        )
        if len(matching) != 1:
            raise ValueError(
                f"expected one validated {dataset_id} artifact for {release_id}; "
                f"found {len(matching)}"
            )
        manifests.append(matching[0])
    return manifests[0], manifests[1]


@ipeds_app.command("build-gr2023")
def ipeds_build_gr2023(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Build an immutable final GR2023 bachelor's cohort table from validated inputs."""
    _build_gr_table(catalog, root, "2023-24-final")


@ipeds_app.command("build-gr2022")
def ipeds_build_gr2022(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
) -> None:
    """Build an immutable final GR2022 bachelor's cohort table from validated inputs."""
    _build_gr_table(catalog, root, "2022-23-final")


def _build_gr_table(catalog: Path, root: Path | None, release_id: str) -> None:
    paths = ProjectPaths.from_environment(root)
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.GRADUATION_RATES,
            release_id=release_id,
        )
        registry_path = paths.data / "manifests" / "registry.sqlite"
        if not registry_path.is_file():
            raise ValueError(f"artifact registry not found: {registry_path}")
        data_manifest, dictionary_manifest = _gr2023_manifests(
            Registry(registry_path), release.release_id
        )
        transform = (
            transform_gr2022_archive if release_id == "2022-23-final" else transform_gr2023_archive
        )
        processed = transform(
            paths.data / "raw" / data_manifest.storage_path,
            paths.data / "raw" / dictionary_manifest.storage_path,
            paths.data / "processed",
            data_manifest,
            dictionary_manifest,
            release,
        )
    except (
        IPEDSCatalogError,
        IPEDSGraduationError,
        IPEDSProcessedArtifactConflict,
        ProvenanceError,
        ValueError,
    ) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps(
            {
                "manifest": processed.manifest.model_dump(mode="json"),
                "manifest_path": str(processed.manifest_path),
                "parquet_path": str(processed.parquet_path),
                "status": "WRITTEN",
            },
            sort_keys=True,
        )
    )


@ipeds_app.command("build-charges")
def ipeds_build_charges(
    catalog: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Reviewed catalog JSON."),
    ],
    release_id: Annotated[str, typer.Option(help="Exact catalog release ID.")],
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
    allow_nonfinal: Annotated[
        bool,
        typer.Option(help="Explicitly allow a preliminary or provisional release."),
    ] = False,
) -> None:
    """Build an immutable normalized charge table from a validated raw artifact."""
    paths = ProjectPaths.from_environment(root)
    registry_path = paths.data / "manifests" / "registry.sqlite"
    try:
        release = select_release(
            IPEDSReleaseCatalog.from_file(catalog),
            IPEDSComponent.ACADEMIC_YEAR_CHARGES,
            release_id=release_id,
            allow_nonfinal=allow_nonfinal,
        )
        if not registry_path.is_file():
            raise ValueError(f"artifact registry not found: {registry_path}")
        registry = Registry(registry_path)
        artifacts = tuple(
            artifact
            for artifact in registry.list_artifacts(
                dataset_id=IPEDS_CHARGES_DATASET.dataset_id, release=release.release_id
            )
            if artifact.state in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
        )
        if len(artifacts) != 1:
            raise ValueError(
                f"expected one validated IPEDS charges artifact for {release.release_id}; "
                f"found {len(artifacts)}"
            )
        artifact = artifacts[0]
        processed = transform_charges_archive(
            paths.data / "raw" / artifact.storage_path,
            paths.data / "processed",
            artifact,
            release,
        )
    except (
        IPEDSArchiveError,
        IPEDSCatalogError,
        IPEDSProcessedArtifactConflict,
        ValueError,
    ) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps(
            {
                "manifest": processed.manifest.model_dump(mode="json"),
                "manifest_path": str(processed.manifest_path),
                "parquet_path": str(processed.parquet_path),
                "status": "WRITTEN",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@ipeds_app.command("resolve-graduation-table")
def ipeds_resolve_graduation_table(
    table: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Processed GR table."),
    ],
    unitid: Annotated[int, typer.Argument(help="Exact institution UNITID.")],
) -> None:
    """Return verified institutional cohort evidence without inferring a scenario probability."""
    try:
        evidence = resolve_graduation_evidence(table, unitid)
    except (IPEDSGraduationComparisonError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    typer.echo(json.dumps(evidence.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@ipeds_app.command("compare-graduation")
def ipeds_compare_graduation(
    previous: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Earlier GR cohort table."),
    ],
    current: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Later GR cohort table."),
    ],
    threshold: Annotated[
        float,
        typer.Option(help="Absolute observed-rate difference requiring review (0 to 1)."),
    ] = 0.10,
    count_threshold: Annotated[
        float,
        typer.Option(help="Relative cohort-count difference requiring review."),
    ] = 0.25,
    history: Annotated[
        Path | None,
        typer.Option("--history", exists=True, dir_okay=False, readable=True),
    ] = None,
    history_source: Annotated[
        Path | None,
        typer.Option("--history-source", exists=True, dir_okay=False, readable=True),
    ] = None,
    fail_on_review: Annotated[bool, typer.Option()] = False,
    allow_unverified_inputs: Annotated[
        bool,
        typer.Option(help="Allow fixtures without manifests; provenance is unverified."),
    ] = False,
) -> None:
    """Compare two distinct final bachelor’s entry cohorts for manual release review."""
    try:
        if history_source is not None and history is None:
            raise ValueError("--history-source requires --history")
        institution_history = InstitutionHistory.from_file(history) if history is not None else None
        if history_source is not None:
            assert institution_history is not None
            if sha256_file(history_source)[0] != institution_history.source_sha256:
                raise ValueError("history source SHA-256 does not match the supplied artifact")
        report = compare_graduation_tables(
            previous,
            current,
            absolute_rate_threshold=threshold,
            relative_count_threshold=count_threshold,
            institution_history=institution_history,
            require_manifests=not allow_unverified_inputs,
        )
    except (IPEDSGraduationComparisonError, InstitutionHistoryError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    payload = report.model_dump(mode="json")
    payload["input_provenance_status"] = (
        "UNVERIFIED" if allow_unverified_inputs else "MANIFEST_VERIFIED"
    )
    payload["history_source_status"] = (
        "HASH_VERIFIED"
        if history_source is not None
        else "UNVERIFIED"
        if history is not None
        else "NOT_APPLICABLE"
    )
    payload["status"] = "REVIEW_REQUIRED" if report.review_required else "ACCEPTABLE"
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if report.review_required and fail_on_review:
        raise typer.Exit(code=1)


@ipeds_app.command("compare-charges")
def ipeds_compare_charges(
    previous: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Previous Parquet table."),
    ],
    current: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Current Parquet table."),
    ],
    threshold: Annotated[
        float,
        typer.Option(help="Absolute fractional change requiring review."),
    ] = 0.25,
    history: Annotated[
        Path | None,
        typer.Option(
            "--history",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Versioned directional UNITID history JSON for these exact releases.",
        ),
    ] = None,
    history_source: Annotated[
        Path | None,
        typer.Option(
            "--history-source",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Local authoritative source artifact to verify against history source_sha256.",
        ),
    ] = None,
    fail_on_review: Annotated[
        bool,
        typer.Option(help="Exit 1 when the report requires manual review."),
    ] = False,
) -> None:
    """Compare normalized charge releases and emit a deterministic review report."""
    try:
        if history_source is not None and history is None:
            raise ValueError("--history-source requires --history")
        institution_history = InstitutionHistory.from_file(history) if history is not None else None
        if history_source is not None:
            assert institution_history is not None
            if sha256_file(history_source)[0] != institution_history.source_sha256:
                raise ValueError("history source SHA-256 does not match the supplied artifact")
        report = compare_charge_tables(
            previous,
            current,
            percent_change_threshold=threshold,
            institution_history=institution_history,
        )
    except (IPEDSReleaseComparisonError, InstitutionHistoryError, ValueError) as error:
        typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
        raise typer.Exit(code=2) from None
    payload = report.model_dump(mode="json")
    payload["history_source_status"] = (
        "HASH_VERIFIED"
        if history_source is not None
        else "UNVERIFIED"
        if history is not None
        else "NOT_APPLICABLE"
    )
    payload["status"] = "REVIEW_REQUIRED" if report.review_required else "ACCEPTABLE"
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if report.review_required and fail_on_review:
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


@data_app.command("bootstrap-zhang")
def data_bootstrap_zhang(
    root: Annotated[Path | None, typer.Option(help="Project root.")] = None,
    vintage: Annotated[
        list[int] | None,
        typer.Option(help="ACS vintage to include; repeat for multiple years."),
    ] = None,
    from_year: Annotated[
        int | None, typer.Option(help="First ACS vintage in an inclusive update range.")
    ] = None,
    to_year: Annotated[
        int | None, typer.Option(help="Last ACS vintage in an inclusive update range.")
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Download, register, and transform instead of dry-run."),
    ] = False,
    minimum_free_gb: Annotated[
        float, typer.Option(help="Required free space before execute mode starts.")
    ] = 70.0,
) -> None:
    """Plan or execute the resumable Zhang source bootstrap."""
    paths = ProjectPaths.from_environment(root)
    try:
        vintages = resolve_vintages(tuple(vintage or ()), from_year, to_year)
        report = bootstrap_zhang_sources(
            paths,
            vintages=vintages,
            execute=execute,
            minimum_free_gb=minimum_free_gb,
        )
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from None
    typer.echo(json.dumps(report.as_dict(), indent=2))


if __name__ == "__main__":  # pragma: no cover
    app()
