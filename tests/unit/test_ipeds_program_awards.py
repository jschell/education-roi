"""Exact C2023_A program award evidence remains distinct from graduate counts."""

import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSReleaseCatalog, select_release
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict
from education_roi.ipeds.program_awards import (
    LABELS,
    IPEDSProgramAwardsError,
    _read_awards,
    register_program_awards,
    resolve_program_awards,
    verify_program_dictionary,
)
from education_roi.ipeds.program_awards_evidence import (
    IPEDSProgramAwardsTableError,
    resolve_program_awards_evidence,
)
from education_roi.ipeds.program_awards_pipeline import transform_program_awards
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.store import Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,CIPCODE,MAJORNUM,AWLEVEL,CTOTALT,XCTOTALT\n"


def sources(tmp_path: Path, rows: str) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    data, dictionary = tmp_path / "C2023_A.zip", tmp_path / "C2023_A_Dict.zip"
    with ZipFile(data, "w", ZIP_DEFLATED) as output:
        output.writestr("C2023_a.csv", HEADER + "236948,11.0101,1,5,999,R\n")
        output.writestr("C2023_a_RV.csv", HEADER + rows)
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("C2023_a_dict.xlsx", b"fixture")
    return data, dictionary


def test_dictionary_requires_exact_definitions_and_award_meanings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dictionary = sources(tmp_path, "236948,11.0101,1,5,12,R\n")[1]
    rows = [["1", key, "N", "6", "Cont", status, label] for key, (label, status) in LABELS.items()]

    def fake_rows(data: bytes, *, sheet_names: frozenset[str]) -> list[list[str]]:
        if sheet_names == frozenset({"Introduction"}):
            return [["(Final/revised release)", "2020 Classification of Instructional Programs"]]
        if sheet_names == frozenset({"FrequenciesRV"}):
            return [
                ["1", "MAJORNUM", "1", "First major"],
                ["1", "AWLEVEL", "5", "Bachelor's degree"],
            ]
        assert sheet_names == frozenset({"Varlist"})
        return rows

    monkeypatch.setattr("education_roi.ipeds.program_awards._xlsx_rows", fake_rows)
    verify_program_dictionary(dictionary)
    rows[1][6] = "CIP Code -  2010 Classification"
    with pytest.raises(IPEDSProgramAwardsError, match="definitions"):
        verify_program_dictionary(dictionary)


@pytest.mark.parametrize(
    "rows",
    [
        "236948,11.0101,1,5,12,R\n236948,11.0101,1,5,13,R\n",
        "236948,11.0101,1,5,12,R,extra\n",
        "236948,11.0101,1,5,nope,R\n",
    ],
)
def test_rejects_duplicate_or_malformed_source_rows(tmp_path: Path, rows: str) -> None:
    data = sources(tmp_path, rows)[0]
    with pytest.raises(IPEDSProgramAwardsError):
        _read_awards(data, "C2023_a_RV.csv")


def test_registration_and_exact_lookup_preserve_source_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards.verify_program_dictionary", lambda p: None
    )
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG), IPEDSComponent.COMPLETIONS_BY_PROGRAM
    )
    data, dictionary = sources(
        tmp_path / "sources",
        "236948,11.0101,1,5,12,R\n"
        "236948,11.0101,2,5,3,R\n"
        "236948,99,1,5,500,R\n"
        "236949,11.0101,1,5,-1,C\n"
        "236950,11.0101,1,5,0,R\n",
    )

    class FakeDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile((data, dictionary)[self.index - 1], target)
            return DownloadResult(target, url, url, target.stat().st_size)

    root = tmp_path / "project"
    registered = register_program_awards(
        release,
        ProjectPaths(root),
        downloader=FakeDownloader(),  # type: ignore[arg-type]
    )
    registry = Registry(root / "data/manifests/registry.sqlite")
    actual_data = (
        root / "data/raw" / registry.get_artifact(registered.data.artifact_id).storage_path
    )
    actual_dictionary = (
        root / "data/raw" / registry.get_artifact(registered.dictionary.artifact_id).storage_path
    )
    args = (actual_data, actual_dictionary, release, registered.data, registered.dictionary)
    observed = resolve_program_awards(*args, 236948, "11.0101", 1, 5)
    assert (observed.status, observed.award_count, observed.cip_version) == ("OBSERVED", 12, "2020")
    assert resolve_program_awards(*args, 236948, "11.0101", 2, 5).award_count == 3
    missing = resolve_program_awards(*args, 236949, "11.0101", 1, 5)
    assert (missing.status, missing.raw_award_count, missing.source_status) == (
        "INSUFFICIENT_DATA",
        "-1",
        "C",
    )
    assert resolve_program_awards(*args, 999999, "11.0101", 1, 5).status == "INSUFFICIENT_DATA"
    zero = resolve_program_awards(*args, 236950, "11.0101", 1, 5)
    assert (zero.status, zero.award_count) == ("OBSERVED", 0)
    with pytest.raises(IPEDSProgramAwardsError, match="six-digit CIP"):
        resolve_program_awards(*args, 236948, "99", 1, 5)
    cli = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-program-awards",
            "236948",
            "11.0101",
            "1",
            "5",
            "--catalog",
            str(CATALOG),
            "--root",
            str(root),
        ],
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["award_count"] == 12
    actual_data.chmod(0o644)
    actual_data.write_bytes(b"tampered")
    with pytest.raises(IPEDSProgramAwardsError, match="bytes do not match"):
        resolve_program_awards(*args, 236948, "11.0101", 1, 5)


def test_immutable_program_table_preserves_exact_keys_and_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards_pipeline.verify_program_dictionary", lambda p: None
    )
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards.verify_program_dictionary", lambda p: None
    )
    data, dictionary = sources(
        tmp_path / "source",
        "236948,11.0101,1,5,12,R\n"
        "236948,11.0101,2,5,3,R\n"
        "236948,99,1,5,500,R\n"
        "236949,11.0101,1,5,-1,C\n"
        "236950,11.0101,1,5,0,R\n",
    )
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG), IPEDSComponent.COMPLETIONS_BY_PROGRAM
    )

    class FakeDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile((data, dictionary)[self.index - 1], target)
            return DownloadResult(target, url, url, target.stat().st_size)

    root = tmp_path / "project"
    pair = register_program_awards(
        release,
        ProjectPaths(root),
        downloader=FakeDownloader(),  # type: ignore[arg-type]
    )
    archive = root / "data/raw" / pair.data.storage_path
    workbook = root / "data/raw" / pair.dictionary.storage_path
    first = transform_program_awards(
        archive, workbook, root / "data/processed", pair.data, pair.dictionary, release
    )
    second = transform_program_awards(
        archive, workbook, root / "data/processed", pair.data, pair.dictionary, release
    )
    assert first.manifest == second.manifest
    assert first.manifest.row_count == 5
    assert first.manifest.key_columns == ("unitid", "cip_code", "major_number", "award_level")
    rows = pl.read_parquet(first.parquet_path).to_dicts()
    assert len(rows) == 5
    assert next(row for row in rows if row["cip_code"] == "99")["is_aggregate_cip"]
    assert next(row for row in rows if row["unitid"] == 236949)["award_count"] is None
    assert next(row for row in rows if row["unitid"] == 236950)["award_count"] == 0
    evidence = resolve_program_awards_evidence(first.parquet_path, 236948, "11.0101", 1, 5)
    assert (evidence.status, evidence.award_count, evidence.cip_version) == ("OBSERVED", 12, "2020")
    assert evidence.data_artifact_id == pair.data.artifact_id
    assert evidence.table_sha256 == first.manifest.transformation.output_sha256
    assert (
        resolve_program_awards_evidence(first.parquet_path, 236948, "11.0101", 2, 5).award_count
        == 3
    )
    assert (
        resolve_program_awards_evidence(first.parquet_path, 236950, "11.0101", 1, 5).award_count
        == 0
    )
    assert (
        resolve_program_awards_evidence(first.parquet_path, 236949, "11.0101", 1, 5).status
        == "INSUFFICIENT_DATA"
    )
    absent = resolve_program_awards_evidence(first.parquet_path, 999999, "11.0101", 1, 5)
    assert absent.unavailable_reason == "exact program key absent from table"
    with pytest.raises(ValueError, match="six-digit CIP"):
        resolve_program_awards_evidence(first.parquet_path, 236948, "99", 1, 5)
    cli = CliRunner().invoke(
        app, ["ipeds", "build-program-awards", "--catalog", str(CATALOG), "--root", str(root)]
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["manifest"]["row_count"] == 5
    lookup = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-program-awards-table",
            str(first.parquet_path),
            "236948",
            "11.0101",
            "1",
            "5",
        ],
    )
    assert lookup.exit_code == 0, lookup.stdout
    assert json.loads(lookup.stdout)["award_count"] == 12
    forged = tmp_path / first.manifest.output_path
    forged.parent.mkdir(parents=True, exist_ok=True)
    pl.read_parquet(first.parquet_path).with_columns(
        pl.when(pl.col("unitid") == 236948)
        .then(pl.lit(999))
        .otherwise(pl.col("award_count"))
        .alias("award_count")
    ).write_parquet(forged)
    forged_manifest = first.manifest.model_dump(mode="json")
    forged_manifest["transformation"]["output_sha256"] = sha256_file(forged)[0]
    source_hashes = Path(first.manifest.output_path).parts[2:4]
    forged_manifest["transformation"]["transformation_id"] = (
        f"ipeds-c2023a-program-awards-v1:2023-24-final:"
        f"{source_hashes[0]}:{source_hashes[1]}:{sha256_file(forged)[0]}"
    )
    forged.with_suffix(".manifest.json").write_text(json.dumps(forged_manifest))
    with pytest.raises(IPEDSProgramAwardsTableError, match="source cell"):
        resolve_program_awards_evidence(forged, 236948, "11.0101", 1, 5)
    first.parquet_path.chmod(0o644)
    first.parquet_path.write_bytes(b"tampered")
    with pytest.raises(IPEDSProgramAwardsTableError, match="hash differs"):
        resolve_program_awards_evidence(first.parquet_path, 236948, "11.0101", 1, 5)
    with pytest.raises(IPEDSProcessedArtifactConflict, match="different bytes"):
        transform_program_awards(
            archive, workbook, root / "data/processed", pair.data, pair.dictionary, release
        )
