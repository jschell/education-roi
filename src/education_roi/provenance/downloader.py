"""Streaming HTTPS downloads with redirect and partial-file safety."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from education_roi.provenance.store import ProvenanceError, validate_source_url


class DownloadError(ProvenanceError):
    """A download did not complete safely."""


@dataclass(frozen=True)
class DownloadResult:
    """Completed temporary download awaiting artifact registration."""

    path: Path
    source_url: str
    final_url: str
    bytes_received: int


class HttpDownloader:
    """Download HTTPS content in bounded chunks to a unique temporary file."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        chunk_size: int = 1024 * 1024,
        max_bytes: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.max_bytes = max_bytes
        self.transport = transport

    def download(
        self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
    ) -> DownloadResult:
        """Stream a URL and return its temporary path; caller owns cleanup."""
        validate_source_url(url, allowed_domains)
        destination_directory.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix="download-", suffix=".partial", dir=destination_directory
        )
        temporary = Path(temporary_name)
        received = 0
        try:
            with (
                os.fdopen(file_descriptor, "wb") as output,
                httpx.Client(
                    follow_redirects=True,
                    timeout=self.timeout,
                    transport=self.transport,
                ) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                final_url = str(response.url)
                validate_source_url(final_url, allowed_domains)
                for chunk in response.iter_bytes(self.chunk_size):
                    received += len(chunk)
                    if self.max_bytes is not None and received > self.max_bytes:
                        raise DownloadError("download exceeded configured maximum size")
                    output.write(chunk)
                expected_length = response.headers.get("content-length")
                if expected_length is not None and received != int(expected_length):
                    message = f"content length mismatch: expected {expected_length}, got {received}"
                    raise DownloadError(message)
                output.flush()
                os.fsync(output.fileno())
            return DownloadResult(temporary, url, final_url, received)
        except (httpx.HTTPError, OSError, ValueError) as error:
            temporary.unlink(missing_ok=True)
            if isinstance(error, ProvenanceError):
                raise
            raise DownloadError(str(error)) from error
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
