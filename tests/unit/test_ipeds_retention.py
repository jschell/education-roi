"""The final revised EF2023D observation retains source population and lineage."""

import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds import (
    IPEDSComponent,
    IPEDSRelease,
    IPEDSReleaseCatalog,
    IPEDSRetentionError,
    register_retention_release,
    resolve_retention,
    select_release,
)
from education_roi.ipeds.retention import (
    LABELS,
    RETENTION_DATA,
    RETENTION_DICTIONARY,
    read_retention_rows,
    verify_retention_dictionary,
)
from education_roi.ipeds.retention_evidence import (
    IPEDSRetentionTableError,
    resolve_retention_evidence,
)
from education_roi.ipeds.retention_pipeline import transform_retention_archive
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.provenance.store import ArtifactStore, Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,RRFTCTA,XRRFTCTA,RET_NMF,XRET_NMF,RET_PCF,XRET_PCF\n"


def fixture(
    tmp_path: Path, rows: str
) -> tuple[Path, Path, IPEDSRelease, ArtifactManifest, ArtifactManifest]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG),
        IPEDSComponent.FALL_RETENTION,
        release_id="2023-24-final",
    )
    archive = tmp_path / "EF2023D.zip"
    dictionary = tmp_path / "EF2023D_Dict.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("ef2023d.csv", HEADER + "236948,1,R,1,R,100,R\n")
        output.writestr("ef2023d_rv.csv", HEADER + rows)
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("ef2023d.xlsx", b"fixture")
    registry = Registry(tmp_path / "data/manifests/registry.sqlite")
    store = ArtifactStore(tmp_path / "data/raw", registry)
    manifests = []
    for path, definition, url in (
        (archive, RETENTION_DATA, str(release.data_url)),
        (dictionary, RETENTION_DICTIONARY, str(release.dictionary_url)),
    ):
        registry.add_dataset(definition)
        item = store.register(
            path,
            definition,
            release=release.release_id,
            source_url=url,
            final_url=url,
            publication_status="final",
            schema_version="ipeds-ef2023d-v1",
        )
        manifests.append(registry.transition(item.artifact_id, ApprovalState.VALIDATED))
    return archive, dictionary, release, manifests[0], manifests[1]


def test_revised_cohort_observation_does_not_equate_retention_and_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.retention.verify_retention_dictionary", lambda path: None
    )
    args = fixture(tmp_path, "236948,7311,R,6938,R,95,R\n236949,-1,N,,N,,N\n")
    result = resolve_retention(*args, 236948)
    assert result.status == "OBSERVED"
    assert (result.entry_cohort_year, result.observation_year) == (2022, 2023)
    assert (result.adjusted_cohort, result.enrolled_next_fall) == (7311, 6938)
    assert result.reported_retention_percent == 95
    assert result.data_artifact_id == args[3].artifact_id
    assert "not a bachelor's completion probability" in result.interpretation
    missing = resolve_retention(*args, 236949)
    assert missing.status == "INSUFFICIENT_DATA"
    assert missing.raw_cells["RRFTCTA"] == "-1"
    assert resolve_retention(*args, 999999).status == "INSUFFICIENT_DATA"
    args[0].write_bytes(b"tampered")
    with pytest.raises(IPEDSRetentionError, match="bytes do not match"):
        resolve_retention(*args, 236948)


def test_dictionary_rejects_swapped_definitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fixture(tmp_path, "236948,1,R,1,R,100,R\n")[1]
    rows = [["1", key, "N", "6", "Cont", "X" + key, label] for key, label in LABELS.items()]

    def fake_rows(data: bytes, *, sheet_names: frozenset[str]) -> list[list[str]]:
        return [["(Final/revised release)"]] if sheet_names == frozenset({"Introduction"}) else rows

    monkeypatch.setattr("education_roi.ipeds.retention._xlsx_rows", fake_rows)
    verify_retention_dictionary(path)
    rows[0][6], rows[1][6] = rows[1][6], rows[0][6]
    with pytest.raises(IPEDSRetentionError, match="cohort definitions"):
        verify_retention_dictionary(path)
    rows[0][6], rows[1][6] = rows[1][6], rows[0][6]
    rows[1] = rows[0].copy()
    with pytest.raises(IPEDSRetentionError, match="cohort definitions"):
        verify_retention_dictionary(path)


@pytest.mark.parametrize("row", ["236948,10,R,8,R,80,R,extra", "236948,10,R,8,R,80"])
def test_retention_rejects_malformed_csv_row(tmp_path: Path, row: str) -> None:
    archive = tmp_path / "malformed.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("ef2023d_rv.csv", HEADER + row + "\n")
    with pytest.raises(IPEDSRetentionError, match="malformed retention row 2"):
        read_retention_rows(archive, "ef2023d_rv.csv")


def test_zero_cohort_and_impossible_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.retention.verify_retention_dictionary", lambda path: None
    )
    args = fixture(tmp_path, "236948,0,R,0,R,0,R\n236949,10,R,11,R,100,R\n")
    assert resolve_retention(*args, 236948).status == "INSUFFICIENT_DATA"
    with pytest.raises(IPEDSRetentionError, match="exceeds adjusted cohort"):
        resolve_retention(*args, 236949)


def test_registration_and_cli_pin_final_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.retention.verify_retention_dictionary", lambda path: None
    )
    args = fixture(tmp_path / "sources", "236948,100,R,90,R,90,R\n")
    release = args[2]
    sources = (args[0], args[1])

    class FakeDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile(sources[self.index - 1], target)
            return DownloadResult(target, url, url, target.stat().st_size)

    root = tmp_path / "project"
    registered = register_retention_release(
        release,
        ProjectPaths(root),
        downloader=FakeDownloader(),  # type: ignore[arg-type]
    )
    assert registered.data.state is ApprovalState.VALIDATED
    assert registered.dictionary.state is ApprovalState.VALIDATED
    cli = CliRunner().invoke(
        app,
        ["ipeds", "resolve-retention", "236948", "--catalog", str(CATALOG), "--root", str(root)],
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["reported_retention_percent"] == 90
    with pytest.raises(IPEDSRetentionError, match="missing"):
        read_retention_rows(args[0], "nonexistent.csv")


def test_immutable_retention_table_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.retention_pipeline.verify_retention_dictionary", lambda path: None
    )
    args = fixture(tmp_path, "236948,7311,R,6938,R,95,R\n236949,-1,N,,N,,N\n")
    output = tmp_path / "data/processed"
    first = transform_retention_archive(args[0], args[1], output, *args[3:], args[2])
    second = transform_retention_archive(args[0], args[1], output, *args[3:], args[2])
    assert first.manifest_path == second.manifest_path
    assert first.manifest == second.manifest
    records = pl.read_parquet(first.parquet_path).sort("unitid").to_dicts()
    assert len(records) == 2
    assert (records[0]["adjusted_cohort"], records[0]["enrolled_next_fall"]) == (7311, 6938)
    assert records[0]["reported_retention_percent"] == 95
    assert records[0]["unavailable_reason"] is None
    assert records[1]["raw_adjusted_cohort"] == "-1"
    assert records[1]["unavailable_reason"] == "missing or negative source cell"
    assert first.manifest.transformation.input_artifact_ids == (
        args[3].artifact_id,
        args[4].artifact_id,
    )
    cli = CliRunner().invoke(
        app, ["ipeds", "build-retention", "--catalog", str(CATALOG), "--root", str(tmp_path)]
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["manifest"]["row_count"] == 2
    first.parquet_path.write_bytes(b"tampered")
    with pytest.raises(Exception, match="different bytes"):
        transform_retention_archive(args[0], args[1], output, *args[3:], args[2])


def test_verified_retention_evidence_and_tamper_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.retention_pipeline.verify_retention_dictionary", lambda path: None
    )
    args = fixture(tmp_path, "236948,7311,R,6938,R,95,R\n236949,-1,N,,N,,N\n")
    processed = transform_retention_archive(
        args[0], args[1], tmp_path / "data/processed", *args[3:], args[2]
    )
    table = processed.parquet_path
    observed = resolve_retention_evidence(table, 236948)
    assert observed.status == "OBSERVED"
    assert observed.reported_retention_percent == 95
    assert observed.enrolled_next_fall == 6938
    assert observed.data_artifact_id == args[3].artifact_id
    assert observed.table_sha256 == processed.manifest.transformation.output_sha256
    assert resolve_retention_evidence(table, 236949).status == "INSUFFICIENT_DATA"
    missing = resolve_retention_evidence(table, 999999)
    assert missing.status == "INSUFFICIENT_DATA"
    assert missing.unavailable_reason == "institution absent from exact retention table"
    cli = CliRunner().invoke(app, ["ipeds", "resolve-retention-table", str(table), "236948"])
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["population"] == observed.population
    with pytest.raises(ValueError, match="positive"):
        resolve_retention_evidence(table, 0)
    table.write_bytes(b"tampered")
    with pytest.raises(IPEDSRetentionTableError, match="hash differs"):
        resolve_retention_evidence(table, 236948)
    cli = CliRunner().invoke(app, ["ipeds", "resolve-retention-table", str(table), "236948"])
    assert cli.exit_code == 2


def test_retention_evidence_rejects_manifest_population_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.retention_pipeline.verify_retention_dictionary", lambda path: None
    )
    args = fixture(tmp_path, "236948,10,R,8,R,80,R\n")
    processed = transform_retention_archive(
        args[0], args[1], tmp_path / "data/processed", *args[3:], args[2]
    )
    manifest = json.loads(processed.manifest_path.read_text())
    manifest["population"] = "different_population"
    processed.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(IPEDSRetentionTableError, match="unsupported retention release"):
        resolve_retention_evidence(processed.parquet_path, 236948)
