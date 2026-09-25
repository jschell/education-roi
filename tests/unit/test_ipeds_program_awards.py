"""Exact C2023_A program award evidence remains distinct from graduate counts."""

import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSReleaseCatalog, select_release
from education_roi.ipeds.program_awards import (
    LABELS,
    IPEDSProgramAwardsError,
    _read_awards,
    register_program_awards,
    resolve_program_awards,
    verify_program_dictionary,
)
from education_roi.provenance.downloader import DownloadResult
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
