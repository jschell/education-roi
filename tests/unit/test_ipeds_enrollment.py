"""Reviewed final EF2023A composite-key enrollment evidence."""

import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSReleaseCatalog, select_release
from education_roi.ipeds.enrollment import (
    COHORTS,
    DEFINITIONS,
    EnrollmentCohort,
    IPEDSEnrollmentError,
    read_enrollment_rows,
    register_enrollment,
    resolve_enrollment,
    verify_enrollment_dictionary,
)
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.store import Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,EFALEVEL,LINE,SECTION,LSTUDY,EFTOTLT,XEFTOTLT\n"


def sources(root: Path, rows: str) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    data, dictionary = root / "EF2023A.zip", root / "EF2023A_Dict.zip"
    with ZipFile(data, "w") as archive:
        archive.writestr("ef2023a.csv", HEADER + "236948,1,29,3,4,999,R\n")
        archive.writestr("ef2023a_rv.csv", HEADER + rows)
    with ZipFile(dictionary, "w") as archive:
        archive.writestr("ef2023a.xlsx", b"fixture")
    return data, dictionary


def test_dictionary_requires_final_labels_and_composite_levels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dictionary = sources(tmp_path, "236948,1,29,3,4,55620,R\n")[1]
    definitions = [
        ["1", code, "N", "6", "Cont", status, label]
        for code, (status, label) in DEFINITIONS.items()
    ]
    frequencies = [
        ["EFALEVEL", "20166", "EF2023A_rv", level, label, "1", "1"]
        for level, _, _, _, label in COHORTS.values()
    ]

    def rows(data: bytes, *, sheet_names: frozenset[str]) -> list[list[str]]:
        if sheet_names == {"Introduction"}:
            return [["(Final/revised release)"]]
        if sheet_names == {"Varlist"}:
            return definitions
        assert sheet_names == {"FrequenciesRV"}
        return frequencies

    monkeypatch.setattr("education_roi.ipeds.enrollment._xlsx_rows", rows)
    verify_enrollment_dictionary(dictionary)
    frequencies[1][4] = "Wrong population"
    with pytest.raises(IPEDSEnrollmentError, match="reviewed cohort"):
        verify_enrollment_dictionary(dictionary)


@pytest.mark.parametrize(
    "rows",
    [
        "236948,1,29,3,4,1,R\n236948,1,29,3,4,2,R\n",
        "236948,24,99,1,1,10,R\n",
        "236948,1,29,3,4,nope,R\n",
        "236948,1,29,3,4,1,R,extra\n",
    ],
)
def test_rejects_duplicate_layout_or_malformed_rows(tmp_path: Path, rows: str) -> None:
    data = sources(tmp_path, rows)[0]
    with pytest.raises(IPEDSEnrollmentError):
        read_enrollment_rows(data, "ef2023a_rv.csv")


def test_paired_registration_and_exact_cohort_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.enrollment.verify_enrollment_dictionary", lambda p: None
    )
    release = select_release(IPEDSReleaseCatalog.from_file(CATALOG), IPEDSComponent.FALL_ENROLLMENT)
    data, dictionary = sources(
        tmp_path / "source",
        "236948,1,29,3,4,55620,R\n"
        "236948,24,1,1,1,6928,R\n"
        "236948,39,2,1,1,1415,R\n"
        "236948,44,15,2,1,83,R\n"
        "236948,59,16,2,1,141,R\n"
        "236949,1,29,3,4,0,R\n"
        "236949,24,1,1,1,-1,C\n"
        "236949,39,2,1,1,,A\n",
    )

    class Downloader:
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
    pair = register_enrollment(release, ProjectPaths(root), downloader=Downloader())  # type: ignore[arg-type]
    registry = Registry(root / "data/manifests/registry.sqlite")
    actual_data = root / "data/raw" / registry.get_artifact(pair.data.artifact_id).storage_path
    actual_dictionary = (
        root / "data/raw" / registry.get_artifact(pair.dictionary.artifact_id).storage_path
    )
    args = (actual_data, actual_dictionary, release, pair.data, pair.dictionary)
    first = resolve_enrollment(*args, 236948, EnrollmentCohort.FULL_TIME_FIRST_TIME)
    assert (first.status, first.enrollment_count, first.efalevel, first.source_status) == (
        "OBSERVED",
        6928,
        "24",
        "R",
    )
    assert (
        resolve_enrollment(*args, 236948, EnrollmentCohort.FULL_TIME_TRANSFER_IN).enrollment_count
        == 1415
    )
    assert (
        resolve_enrollment(*args, 236948, EnrollmentCohort.PART_TIME_FIRST_TIME).enrollment_count
        == 83
    )
    assert (
        resolve_enrollment(*args, 236948, EnrollmentCohort.PART_TIME_TRANSFER_IN).enrollment_count
        == 141
    )
    assert resolve_enrollment(*args, 236949, EnrollmentCohort.ALL_STUDENTS).enrollment_count == 0
    negative = resolve_enrollment(*args, 236949, EnrollmentCohort.FULL_TIME_FIRST_TIME)
    assert (negative.status, negative.raw_enrollment_count, negative.source_status) == (
        "INSUFFICIENT_DATA",
        "-1",
        "C",
    )
    blank = resolve_enrollment(*args, 236949, EnrollmentCohort.FULL_TIME_TRANSFER_IN)
    assert (blank.status, blank.raw_enrollment_count, blank.source_status) == (
        "INSUFFICIENT_DATA",
        "",
        "A",
    )
    assert (
        resolve_enrollment(*args, 999999, EnrollmentCohort.ALL_STUDENTS).status
        == "INSUFFICIENT_DATA"
    )
    cli = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-enrollment",
            "236948",
            "full_time_first_time",
            "--catalog",
            str(CATALOG),
            "--root",
            str(root),
        ],
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["enrollment_count"] == 6928
    actual_data.chmod(0o644)
    actual_data.write_bytes(b"tampered")
    with pytest.raises(IPEDSEnrollmentError, match="bytes do not match"):
        resolve_enrollment(*args, 236948, EnrollmentCohort.ALL_STUDENTS)


def test_immutable_enrollment_table_keeps_exact_cohorts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import polars as pl

    from education_roi.ipeds.enrollment_pipeline import VERSION, transform_enrollment
    from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict
    from education_roi.provenance.integrity import sha256_file

    monkeypatch.setattr(
        "education_roi.ipeds.enrollment.verify_enrollment_dictionary", lambda p: None
    )
    monkeypatch.setattr(
        "education_roi.ipeds.enrollment_pipeline.verify_enrollment_dictionary", lambda p: None
    )
    release = select_release(IPEDSReleaseCatalog.from_file(CATALOG), IPEDSComponent.FALL_ENROLLMENT)
    data, dictionary = sources(
        tmp_path / "source",
        "236948,1,29,3,4,55620,R\n"
        "236948,24,1,1,1,6928,R\n"
        "236948,39,2,1,1,1415,R\n"
        "236949,1,29,3,4,0,R\n"
        "236949,24,1,1,1,-1,C\n"
        "236949,39,2,1,1,,A\n",
    )

    class Downloader:
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
    pair = register_enrollment(release, ProjectPaths(root), downloader=Downloader())  # type: ignore[arg-type]
    registry = Registry(root / "data/manifests/registry.sqlite")
    actual_data = root / "data/raw" / registry.get_artifact(pair.data.artifact_id).storage_path
    actual_dictionary = (
        root / "data/raw" / registry.get_artifact(pair.dictionary.artifact_id).storage_path
    )
    args = (
        actual_data,
        actual_dictionary,
        root / "data/processed",
        pair.data,
        pair.dictionary,
        release,
    )
    result = transform_enrollment(*args)
    frame = pl.read_parquet(result.parquet_path)
    assert result.manifest.row_count == 6
    assert result.manifest.key_columns == ("unitid", "efalevel")
    assert frame.select("unitid", "efalevel").rows() == [
        (236948, 1),
        (236948, 24),
        (236948, 39),
        (236949, 1),
        (236949, 24),
        (236949, 39),
    ]
    records = frame.to_dicts()
    assert (records[1]["cohort"], records[1]["line"], records[1]["enrollment_count"]) == (
        "full_time_first_time",
        1,
        6928,
    )
    assert (
        records[3]["enrollment_count"],
        records[4]["raw_enrollment_count"],
        records[4]["enrollment_count"],
        records[4]["source_status"],
    ) == (0, "-1", None, "C")
    assert (
        records[5]["raw_enrollment_count"],
        records[5]["source_status"],
        records[5]["unavailable_reason"],
    ) == ("", "A", "missing or negative source count")
    assert frame["transformation_version"].to_list() == [VERSION] * 6
    assert result.manifest.transformation.output_sha256 == sha256_file(result.parquet_path)[0]
    repeat = transform_enrollment(*args)
    assert repeat.manifest == result.manifest
    cli = CliRunner().invoke(
        app, ["ipeds", "build-enrollment", "--catalog", str(CATALOG), "--root", str(root)]
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["manifest"]["row_count"] == 6
    result.parquet_path.chmod(0o644)
    result.parquet_path.write_bytes(b"tampered")
    with pytest.raises(IPEDSProcessedArtifactConflict, match="different bytes"):
        transform_enrollment(*args)
