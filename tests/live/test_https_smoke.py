import os
from pathlib import Path

import pytest

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
