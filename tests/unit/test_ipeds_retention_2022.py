"""Exact EF2022D final revised registration and historical cohort semantics."""

import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds import IPEDSComponent, IPEDSReleaseCatalog, select_release
from education_roi.ipeds.retention import IPEDSRetentionError
from education_roi.ipeds.retention_2022 import (
    DATA,
    DICTIONARY,
    register_retention_2022,
    require_release,
    resolve_retention_2022,
    verify_dictionary,
)
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.models import ApprovalState
from education_roi.provenance.store import Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,RRFTCTA,XRRFTCTA,RET_NMF,XRET_NMF,RET_PCF,XRET_PCF\n"


def test_legacy_registration_and_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG),
        IPEDSComponent.FALL_RETENTION,
        release_id="2022-23-final",
    )
    data = tmp_path / "EF2022D.zip"
    dictionary = tmp_path / "EF2022D_Dict.zip"
    with ZipFile(data, "w", ZIP_DEFLATED) as output:
        output.writestr("ef2022d.csv", HEADER + "236948,1,R,1,R,100,R\n")
        output.writestr("ef2022d_rv.csv", HEADER + "236948,7165,R,6707,R,94,R\n236949,-1,N,,N,,N\n")
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("ef2022d.xlsx", b"fixture")
    monkeypatch.setattr("education_roi.ipeds.retention_2022.verify_dictionary", lambda path: None)

    class FakeDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            self.index += 1
            destination_directory.mkdir(parents=True, exist_ok=True)
            path = destination_directory / f"download-{self.index}.zip"
            copyfile((data, dictionary)[self.index - 1], path)
            return DownloadResult(path, url, url, path.stat().st_size)

    project = ProjectPaths(tmp_path / "project")
    registered = register_retention_2022(release, project, downloader=FakeDownloader())  # type: ignore[arg-type]
    assert registered.data.state is ApprovalState.VALIDATED
    assert registered.dictionary.state is ApprovalState.VALIDATED
    registry = Registry(project.data / "manifests/registry.sqlite")
    assert registry.list_artifacts(DATA.dataset_id, release.release_id)
    assert registry.list_artifacts(DICTIONARY.dataset_id, release.release_id)
    result = resolve_retention_2022(
        project.data / "raw" / registered.data.storage_path,
        project.data / "raw" / registered.dictionary.storage_path,
        release,
        registered.data,
        registered.dictionary,
        236948,
    )
    assert (result.entry_cohort_year, result.observation_year) == (2021, 2022)
    assert (
        result.adjusted_cohort,
        result.enrolled_next_fall,
        result.reported_retention_percent,
    ) == (7165, 6707, 94)
    assert result.status == "OBSERVED"
    cli = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-retention",
            "236948",
            "--catalog",
            str(CATALOG),
            "--root",
            str(project.root),
            "--release-id",
            release.release_id,
        ],
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["entry_cohort_year"] == 2021
    assert (
        resolve_retention_2022(
            project.data / "raw" / registered.data.storage_path,
            project.data / "raw" / registered.dictionary.storage_path,
            release,
            registered.data,
            registered.dictionary,
            236949,
        ).status
        == "INSUFFICIENT_DATA"
    )


def test_legacy_dictionary_and_release_gates(tmp_path: Path) -> None:
    catalog = IPEDSReleaseCatalog.from_file(CATALOG)
    current = select_release(catalog, IPEDSComponent.FALL_RETENTION, release_id="2023-24-final")
    with pytest.raises(IPEDSRetentionError, match="EF2022D"):
        require_release(current)
    path = tmp_path / "dict.zip"
    with ZipFile(path, "w", ZIP_DEFLATED) as output:
        output.writestr("ef2022d.xlsx", b"invalid workbook")
    with pytest.raises(IPEDSRetentionError, match="could not verify"):
        verify_dictionary(path)
