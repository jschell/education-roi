"""Download, validate, and register a pinned IPEDS charges release."""

from pathlib import Path
from urllib.parse import urlparse

from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.archive import read_charge_rows
from education_roi.ipeds.source import IPEDS_CHARGES_DATASET, IPEDS_SCHEMA_VERSION
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.provenance.store import ArtifactStore, Registry


def register_ipeds_charges(
    *,
    url: str,
    release: str,
    publication_status: str,
    paths: ProjectPaths,
    downloader: HttpDownloader | None = None,
) -> ArtifactManifest:
    """Register an explicit official release URL after full schema validation."""
    if publication_status not in {"preliminary", "provisional", "final"}:
        raise ValueError("IPEDS publication status must be preliminary, provisional, or final")
    downloader = downloader or HttpDownloader()
    download = downloader.download(
        url, paths.data / ".downloads", IPEDS_CHARGES_DATASET.allowed_domains
    )
    try:
        read_charge_rows(download.path)
        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        registry.add_dataset(IPEDS_CHARGES_DATASET)
        manifest = ArtifactStore(paths.data / "raw", registry).register(
            download.path,
            IPEDS_CHARGES_DATASET,
            release=release,
            source_url=download.source_url,
            final_url=download.final_url,
            publication_status=publication_status,
            schema_version=IPEDS_SCHEMA_VERSION,
            vintage=release,
            artifact_name=Path(urlparse(download.final_url).path).name or "ipeds-charges.zip",
        )
        if manifest.state is ApprovalState.DOWNLOADED:
            return registry.transition(
                manifest.artifact_id,
                ApprovalState.VALIDATED,
                "IPEDS ZIP, CSV schema, UNITID uniqueness, and required charge columns validated",
            )
        return manifest
    finally:
        download.path.unlink(missing_ok=True)

