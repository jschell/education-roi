import os
from pathlib import Path

import pytest

from education_roi.ipeds.archive import read_charge_rows
from education_roi.ipeds.catalog import IPEDSReleaseCatalog
from education_roi.ipeds.dictionary import read_dictionary
from education_roi.provenance.downloader import HttpDownloader


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("EDU_ROI_LIVE_TESTS") != "1", reason="live tests disabled")
def test_census_https_smoke(tmp_path: Path) -> None:
    result = HttpDownloader(timeout=30, max_bytes=1_000_000).download(
        "https://www.census.gov/robots.txt", tmp_path, ("census.gov",)
    )
    try:
        assert result.bytes_received > 0
        assert result.final_url.startswith("https://")
    finally:
        result.path.unlink(missing_ok=True)


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("EDU_ROI_LIVE_TESTS") != "1", reason="live tests disabled")
def test_ipeds_https_smoke(tmp_path: Path) -> None:
    """Confirm the configured official host remains reachable without pinning a release URL."""
    result = HttpDownloader(timeout=30, max_bytes=2_000_000).download(
        "https://nces.ed.gov/robots.txt", tmp_path, ("nces.ed.gov",)
    )
    try:
        assert result.bytes_received > 0
        assert result.final_url.startswith("https://nces.ed.gov/")
    finally:
        result.path.unlink(missing_ok=True)


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("EDU_ROI_LIVE_TESTS") != "1", reason="live tests disabled")
def test_ipeds_catalog_charges_data_and_dictionary_pair(tmp_path: Path) -> None:
    """Check the exact catalog pair, including the multi-sheet official dictionary."""
    catalog = IPEDSReleaseCatalog.from_file(
        Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
    )
    release = next(item for item in catalog.releases if item.release_id == "2023-24-provisional")
    downloader = HttpDownloader(timeout=90, max_bytes=10_000_000)
    data = downloader.download(str(release.data_url), tmp_path, ("nces.ed.gov",))
    dictionary = downloader.download(str(release.dictionary_url), tmp_path, ("nces.ed.gov",))
    try:
        assert 236948 in read_charge_rows(data.path)
        assert set(read_dictionary(dictionary.path)) == {"UNITID", "CHG2AY3", "CHG4AY3"}
    finally:
        data.path.unlink(missing_ok=True)
        dictionary.path.unlink(missing_ok=True)
