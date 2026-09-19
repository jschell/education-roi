from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from education_roi.provenance.downloader import DownloadError, HttpDownloader
from education_roi.provenance.store import DomainNotAllowedError


class BrokenStream(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        yield b"partial"
        raise httpx.ReadError("connection interrupted")


@pytest.mark.integration
def test_streamed_download_and_allowed_redirect(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://files.example.gov/data"})
        return httpx.Response(200, content=b"abcdef", headers={"content-length": "6"})

    result = HttpDownloader(chunk_size=2, transport=httpx.MockTransport(handler)).download(
        "https://example.gov/start", tmp_path, ("example.gov",)
    )

    assert result.path.read_bytes() == b"abcdef"
    assert result.final_url == "https://files.example.gov/data"
    assert result.bytes_received == 6
    assert result.path.suffix == ".partial"


@pytest.mark.integration
def test_disallowed_redirect_removes_partial_file(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.gov":
            return httpx.Response(302, headers={"location": "https://evil.example/data"})
        return httpx.Response(200, content=b"untrusted")

    with pytest.raises(DomainNotAllowedError):
        HttpDownloader(transport=httpx.MockTransport(handler)).download(
            "https://example.gov/start", tmp_path, ("example.gov",)
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
def test_interrupted_download_removes_partial_file(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=BrokenStream())

    with pytest.raises(DownloadError, match="interrupted"):
        HttpDownloader(transport=httpx.MockTransport(handler)).download(
            "https://example.gov/data", tmp_path, ("example.gov",)
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
def test_http_error_and_size_limit_remove_partial_files(tmp_path: Path) -> None:
    error_transport = httpx.MockTransport(lambda request: httpx.Response(500))
    with pytest.raises(DownloadError):
        HttpDownloader(transport=error_transport).download(
            "https://example.gov/data", tmp_path, ("example.gov",)
        )

    content_transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"12345"))
    with pytest.raises(DownloadError, match="maximum size"):
        HttpDownloader(max_bytes=4, transport=content_transport).download(
            "https://example.gov/data", tmp_path, ("example.gov",)
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
def test_timeout_removes_partial_file(tmp_path: Path) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(DownloadError, match="timed out"):
        HttpDownloader(transport=httpx.MockTransport(timeout)).download(
            "https://example.gov/data", tmp_path, ("example.gov",)
        )

    assert list(tmp_path.iterdir()) == []
