"""Source-independent release-discovery contracts."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DiscoveredRelease:
    """A publisher release candidate before download."""

    dataset_id: str
    release: str
    source_url: str
    publication_status: str


class ReleaseDiscoverer(Protocol):
    """Implemented later by source-specific adapters."""

    def discover(self) -> tuple[DiscoveredRelease, ...]: ...


class Downloader(Protocol):
    """Streaming downloader boundary for production adapters and test doubles."""

    def download(self, release: DiscoveredRelease) -> tuple[str, str]:
        """Return a temporary file path and the final redirect URL."""
        ...
