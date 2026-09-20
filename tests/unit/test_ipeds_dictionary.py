from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from education_roi.config.paths import ProjectPaths
from education_roi.ipeds import (
    IPEDSDictionaryError,
    IPEDSReleaseCatalog,
    read_dictionary,
    register_ipeds_release,
)
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.models import ApprovalState

PROJECT_ROOT = Path(__file__).parents[2]


def dictionary_zip(path: Path, body: str) -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("IC2023_AY_Dict.csv", body)
    return path


def test_dictionary_requires_and_retains_charge_variable_rows(tmp_path: Path) -> None:
    path = dictionary_zip(
        tmp_path / "dictionary.zip",
        "varname,title,description\n"
        "UNITID,Institution ID,IPEDS identifier\n"
        "CHG2AY3,In-state tuition and fees,Academic-year charge\n"
        "CHG4AY3,Books and supplies,Estimated books charge\n",
    )
    definitions = read_dictionary(path)
    assert set(definitions) == {"UNITID", "CHG2AY3", "CHG4AY3"}
    assert "In-state tuition and fees" in definitions["CHG2AY3"].metadata


def test_dictionary_missing_required_variable_fails(tmp_path: Path) -> None:
    path = dictionary_zip(
        tmp_path / "dictionary.zip",
        "varname,title\nUNITID,Institution ID\nCHG2AY3,Tuition\n",
    )
    with pytest.raises(IPEDSDictionaryError, match="CHG4AY3"):
        read_dictionary(path)


def test_dictionary_duplicate_definition_fails(tmp_path: Path) -> None:
    path = dictionary_zip(
        tmp_path / "dictionary.zip",
        "varname,title\nUNITID,ID\nCHG2AY3,Tuition\nCHG2AY3,Again\nCHG4AY3,Books\n",
    )
    with pytest.raises(IPEDSDictionaryError, match="duplicate"):
        read_dictionary(path)


def test_dictionary_rejects_ambiguous_archive(tmp_path: Path) -> None:
    path = tmp_path / "dictionary.zip"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("one.csv", "UNITID")
        archive.writestr("two.csv", "CHG2AY3")
    with pytest.raises(IPEDSDictionaryError, match="exactly one"):
        read_dictionary(path)


def test_paired_release_registration_validates_both_artifacts(tmp_path: Path) -> None:
    charges = tmp_path / "charges.zip"
    with ZipFile(charges, "w", ZIP_DEFLATED) as archive:
        archive.writestr("IC2023_AY.csv", "UNITID,CHG2AY3,CHG4AY3\n236948,12000,900\n")
    dictionary = dictionary_zip(
        tmp_path / "dictionary.zip",
        "varname,title\nUNITID,ID\nCHG2AY3,Tuition\nCHG4AY3,Books\n",
    )
    catalog = IPEDSReleaseCatalog.from_file(
        PROJECT_ROOT / "data/manifests/ipeds-release-catalog.json"
    )

    class FakeDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            source = (charges, dictionary)[self.index]
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile(source, target)
            return DownloadResult(target, url, url, target.stat().st_size)

    registered = register_ipeds_release(
        catalog.releases[0],
        ProjectPaths(tmp_path / "project"),
        downloader=FakeDownloader(),  # type: ignore[arg-type]
    )
    assert registered.charges.state is ApprovalState.VALIDATED
    assert registered.dictionary.state is ApprovalState.VALIDATED
    assert registered.charges.dataset_id != registered.dictionary.dataset_id
    assert registered.charges.release == registered.dictionary.release == "2023-24-provisional"
