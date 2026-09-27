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
from education_roi.ipeds.cip import CIPCrosswalk
from education_roi.ipeds.identity import InstitutionHistory
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict
from education_roi.ipeds.program_awards import (
    LABELS,
    PROGRAM_DATA_2022,
    IPEDSProgramAwardsError,
    _read_awards,
    register_program_awards,
    resolve_program_awards,
    verify_program_dictionary,
)
from education_roi.ipeds.program_awards_comparison import (
    IPEDSProgramAwardsComparisonError,
    compare_program_award_key,
)
from education_roi.ipeds.program_awards_context import review_program_awards_context
from education_roi.ipeds.program_awards_evidence import (
    IPEDSProgramAwardsTableError,
    resolve_program_awards_evidence,
)
from education_roi.ipeds.program_awards_pipeline import VERSION_2022, transform_program_awards
from education_roi.ipeds.program_awards_status import (
    LABELS as IMPUTATION_LABELS,
)
from education_roi.ipeds.program_awards_status import (
    interpret_award_status,
)
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.store import Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
CIP_CROSSWALK = Path(__file__).parents[2] / "data/crosswalks/nces-cip-2010-to-2020.json"
UNITID_HISTORY = Path(__file__).parents[2] / "data/crosswalks/nces-hd2022-to-hd2023-events.json"
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
        if sheet_names == frozenset({"Imputation values"}):
            return [
                ["CodeValue", "ValueLabel"],
                *[[code, label] for code, label in IMPUTATION_LABELS.items()],
            ]
        assert sheet_names == frozenset({"Varlist"})
        return rows

    monkeypatch.setattr("education_roi.ipeds.program_awards._xlsx_rows", fake_rows)
    verify_program_dictionary(dictionary)
    rows[1][6] = "CIP Code -  2010 Classification"
    with pytest.raises(IPEDSProgramAwardsError, match="definitions"):
        verify_program_dictionary(dictionary)


def test_prior_dictionary_requires_legacy_sheet_and_imputation_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dictionary = tmp_path / "C2022_A_Dict.zip"
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("c2022_a.xlsx", b"fixture")

    def fake_rows(data: bytes, *, sheet_names: frozenset[str]) -> list[list[str]]:
        if sheet_names == frozenset({"Introduction"}):
            return [["Final/revised release:", "2020 Classification of Instructional Programs"]]
        if sheet_names == frozenset({"varlist"}):
            return [
                ["1", key, "N", "6", "Cont", status, label]
                for key, (label, status) in LABELS.items()
            ]
        if sheet_names == frozenset({"FrequenciesRV"}):
            return [
                ["1", "MAJORNUM", "1", "First major"],
                ["1", "AWLEVEL", "5", "Bachelor's degree"],
            ]
        assert sheet_names == frozenset({"Imputation values"})
        return [
            ["Code values for item imputation variables Xvarname"],
            ["CodeValue", "ValueLabel"],
            *[
                [code, label + (";" if code == "Z" else "")]
                for code, label in IMPUTATION_LABELS.items()
            ],
        ]

    monkeypatch.setattr("education_roi.ipeds.program_awards._xlsx_rows", fake_rows)
    verify_program_dictionary(dictionary, "2022-23-final")


def test_program_award_imputation_labels_preserve_raw_status() -> None:
    assert interpret_award_status("R").label == "Reported"
    assert not interpret_award_status("R").review_required
    assert interpret_award_status("C").label == "Analyst corrected reported value"
    assert interpret_award_status("C").review_required
    assert interpret_award_status("Z").label == "Implied zero"
    assert interpret_award_status("Z").review_required
    assert interpret_award_status("Z", "2022-23-final").label == "Implied zero;"
    assert interpret_award_status("J").label == "Logical imputation"
    assert interpret_award_status("J").review_required
    assert interpret_award_status("?").label is None
    assert interpret_award_status("?").review_required


def test_prior_year_registration_and_lookup_keep_release_definitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG),
        IPEDSComponent.COMPLETIONS_BY_PROGRAM,
        release_id="2022-23-final",
    )
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    data, dictionary = source_dir / "C2022_A.zip", source_dir / "C2022_A_Dict.zip"
    with ZipFile(data, "w", ZIP_DEFLATED) as output:
        output.writestr("c2022_a.csv", HEADER + "100654,01.0999,1,05,100,R\n")
        output.writestr("c2022_a_rv.csv", HEADER + "100654,01.0999,1,05,9,C\n")
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("c2022_a.xlsx", b"fixture")
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards.verify_program_dictionary",
        lambda path, release_id=None: None,
    )
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards_pipeline.verify_program_dictionary",
        lambda path, release_id=None: None,
    )

    class FakeDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            self.index += 1
            destination_directory.mkdir(parents=True, exist_ok=True)
            target = destination_directory / f"download-{self.index}.zip"
            copyfile((data, dictionary)[self.index - 1], target)
            return DownloadResult(target, url, url, target.stat().st_size)

    paths = ProjectPaths(tmp_path / "project")
    pair = register_program_awards(release, paths, downloader=FakeDownloader())  # type: ignore[arg-type]
    assert pair.data.dataset_id == PROGRAM_DATA_2022.dataset_id
    observation = resolve_program_awards(
        paths.data / "raw" / pair.data.storage_path,
        paths.data / "raw" / pair.dictionary.storage_path,
        release,
        pair.data,
        pair.dictionary,
        100654,
        "01.0999",
        1,
        5,
    )
    assert observation.award_count == 9
    assert observation.raw_award_count == "9"
    assert observation.source_status_label == "Analyst corrected reported value"
    assert observation.source_status_review_required
    assert (observation.period_start, observation.period_end) == ("2021-07-01", "2022-06-30")
    cli = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-program-awards",
            "100654",
            "01.0999",
            "1",
            "5",
            "--catalog",
            str(CATALOG),
            "--root",
            str(paths.root),
            "--release-id",
            "2022-23-final",
        ],
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["award_count"] == 9
    archive = paths.data / "raw" / pair.data.storage_path
    workbook = paths.data / "raw" / pair.dictionary.storage_path
    first = transform_program_awards(
        archive, workbook, paths.data / "processed", pair.data, pair.dictionary, release
    )
    second = transform_program_awards(
        archive, workbook, paths.data / "processed", pair.data, pair.dictionary, release
    )
    assert first.manifest == second.manifest
    assert first.manifest.row_count == 1
    assert first.manifest.transformation.parameters["data_member"] == "c2022_a_rv.csv"
    assert first.manifest.transformation.parameters["transformation_version"] == VERSION_2022
    row = pl.read_parquet(first.parquet_path).to_dicts()[0]
    assert (row["award_count"], row["source_status"], row["award_level"]) == (9, "C", 5)
    assert (row["period_start"], row["period_end"]) == ("2021-07-01", "2022-06-30")
    built = CliRunner().invoke(
        app,
        [
            "ipeds",
            "build-program-awards",
            "--catalog",
            str(CATALOG),
            "--root",
            str(paths.root),
            "--release-id",
            "2022-23-final",
        ],
    )
    assert built.exit_code == 0, built.stdout
    assert json.loads(built.stdout)["manifest"]["row_count"] == 1
    evidence = resolve_program_awards_evidence(first.parquet_path, 100654, "01.0999", 1, 5)
    assert evidence.status == "OBSERVED"
    assert evidence.award_count == 9
    assert evidence.source_status_label == "Analyst corrected reported value"
    assert evidence.source_status_review_required
    assert evidence.transformation_version == VERSION_2022
    assert evidence.table_sha256 == first.manifest.transformation.output_sha256
    lookup = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-program-awards-table",
            str(first.parquet_path),
            "100654",
            "01.0999",
            "1",
            "5",
        ],
    )
    assert lookup.exit_code == 0, lookup.stdout
    assert json.loads(lookup.stdout)["period_start"] == "2021-07-01"
    assert (
        resolve_program_awards_evidence(first.parquet_path, 999999, "01.0999", 1, 5).status
        == "INSUFFICIENT_DATA"
    )


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
        "education_roi.ipeds.program_awards.verify_program_dictionary",
        lambda p, release_id=None: None,
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
    assert (observed.source_status_label, observed.source_status_review_required) == (
        "Reported",
        False,
    )
    assert resolve_program_awards(*args, 236948, "11.0101", 2, 5).award_count == 3
    missing = resolve_program_awards(*args, 236949, "11.0101", 1, 5)
    assert (missing.status, missing.raw_award_count, missing.source_status) == (
        "INSUFFICIENT_DATA",
        "-1",
        "C",
    )
    assert missing.source_status_label == "Analyst corrected reported value"
    assert missing.source_status_review_required
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
        "education_roi.ipeds.program_awards_pipeline.verify_program_dictionary",
        lambda p, release_id=None: None,
    )
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards.verify_program_dictionary",
        lambda p, release_id=None: None,
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
    assert evidence.source_status_label == "Reported"
    assert not evidence.source_status_review_required
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
    contextual = review_program_awards_context(
        first.parquet_path,
        236948,
        "2023-24-final",
        "11.0101",
        "2010",
        1,
        5,
        crosswalk=CIPCrosswalk.from_file(CIP_CROSSWALK),
    )
    assert contextual.status == "OBSERVED"
    assert contextual.evidence is not None and contextual.evidence.award_count == 12
    assert not contextual.review_reasons
    reviewed = review_program_awards_context(
        first.parquet_path,
        236948,
        "2023-24-final",
        "43.0116",
        "2010",
        1,
        5,
        crosswalk=CIPCrosswalk.from_file(CIP_CROSSWALK),
    )
    assert reviewed.status == "REVIEW_REQUIRED"
    assert reviewed.cip_resolution.target_code == "43.0403"
    assert reviewed.evidence is None
    cli_context = CliRunner().invoke(
        app,
        [
            "ipeds",
            "review-program-awards-context",
            str(first.parquet_path),
            "236948",
            "2023-24-final",
            "11.0101",
            "2010",
            "1",
            "5",
            "--crosswalk",
            str(CIP_CROSSWALK),
        ],
    )
    assert cli_context.exit_code == 0, cli_context.stdout
    assert json.loads(cli_context.stdout)["evidence"]["award_count"] == 12
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


def test_program_context_blocks_merged_and_unresolved_institution_identity() -> None:
    history = InstitutionHistory.from_file(UNITID_HISTORY)
    for unitid, expected in ((128577, "merged"), (413972, "unresolved")):
        result = review_program_awards_context(
            Path("unused.parquet"),
            unitid,
            "2022-23-final",
            "11.0101",
            "2020",
            1,
            5,
            history=history,
        )
        assert result.status == "REVIEW_REQUIRED"
        assert result.institution_resolution.relationship.value == expected
        assert result.evidence is None


def test_exact_program_key_comparison_verifies_both_tables_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards.verify_program_dictionary",
        lambda path, release_id=None: None,
    )
    monkeypatch.setattr(
        "education_roi.ipeds.program_awards_pipeline.verify_program_dictionary",
        lambda path, release_id=None: None,
    )
    catalog = IPEDSReleaseCatalog.from_file(CATALOG)
    paths = ProjectPaths(tmp_path / "project")
    tables = []
    for release_id, count in (("2022-23-final", 9), ("2023-24-final", 12)):
        release = select_release(
            catalog, IPEDSComponent.COMPLETIONS_BY_PROGRAM, release_id=release_id
        )
        data = tmp_path / f"{release_id}-data.zip"
        dictionary = tmp_path / f"{release_id}-dictionary.zip"
        with ZipFile(data, "w", ZIP_DEFLATED) as output:
            output.writestr(release.data_member or "", HEADER + f"100654,01.0999,1,05,{count},R\n")
        with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
            output.writestr(
                "c2022_a.xlsx" if release_id == "2022-23-final" else "C2023_a_dict.xlsx",
                b"fixture",
            )

        class FakeDownloader:
            def __init__(self, files: tuple[Path, Path], name: str) -> None:
                self.files = files
                self.name = name
                self.index = 0

            def download(
                self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
            ) -> DownloadResult:
                self.index += 1
                destination_directory.mkdir(parents=True, exist_ok=True)
                target = destination_directory / f"download-{self.name}-{self.index}.zip"
                copyfile(self.files[self.index - 1], target)
                return DownloadResult(target, url, url, target.stat().st_size)

        pair = register_program_awards(
            release,
            paths,
            downloader=FakeDownloader((data, dictionary), release_id),  # type: ignore[arg-type]
        )
        built = transform_program_awards(
            paths.data / "raw" / pair.data.storage_path,
            paths.data / "raw" / pair.dictionary.storage_path,
            paths.data / "processed",
            pair.data,
            pair.dictionary,
            release,
        )
        tables.append(built.parquet_path)
    previous, current = tables
    report = compare_program_award_key(previous, current, 100654, "01.0999", 1, 5)
    assert report.status == "REVIEW_REQUIRED"
    assert report.absolute_count_change == 3
    assert report.relative_count_change == pytest.approx(1 / 3)
    assert report.previous.table_sha256 != report.current.table_sha256
    assert (
        compare_program_award_key(
            previous, current, 100654, "01.0999", 1, 5, relative_count_threshold=0.5
        ).status
        == "ACCEPTABLE"
    )
    cli = CliRunner().invoke(
        app,
        [
            "ipeds",
            "compare-program-award-key",
            str(previous),
            str(current),
            "100654",
            "01.0999",
            "1",
            "5",
            "--fail-on-review",
        ],
    )
    assert cli.exit_code == 1
    assert json.loads(cli.stdout)["absolute_count_change"] == 3
    history = InstitutionHistory.model_validate(
        {
            "history_id": "reviewed-example",
            "source_release": "2022-23-final",
            "target_release": "2023-24-final",
            "source_url": "https://nces.ed.gov/ipeds/datacenter/data/HD2023.zip",
            "source_sha256": "a" * 64,
            "entries": [
                {
                    "source_unitid": 100654,
                    "target_unitid": 100655,
                    "relationship": "merged",
                    "confidence": "high",
                }
            ],
        }
    )
    blocked = compare_program_award_key(
        previous, current, 100654, "01.0999", 1, 5, institution_history=history
    )
    assert blocked.status == "REVIEW_REQUIRED"
    assert blocked.absolute_count_change is None
    with pytest.raises(IPEDSProgramAwardsComparisonError, match="ordered"):
        compare_program_award_key(current, previous, 100654, "01.0999", 1, 5)
