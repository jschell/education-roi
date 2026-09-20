"""Download, validate, and register a pinned IPEDS charges release."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.archive import read_charge_rows
from education_roi.ipeds.catalog import IPEDSRelease
from education_roi.ipeds.dictionary import read_dictionary
from education_roi.ipeds.source import (
    IPEDS_CHARGES_DATASET,
    IPEDS_DICTIONARY_DATASET,
    IPEDS_SCHEMA_VERSION,
)
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.provenance.store import ArtifactStore, Registry


@dataclass(frozen=True)
class RegisteredIPEDSRelease:
    charges: ArtifactManifest
    dictionary: ArtifactManifest


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


def register_ipeds_release(
    release: IPEDSRelease,
    paths: ProjectPaths,
    *,
    downloader: HttpDownloader | None = None,
) -> RegisteredIPEDSRelease:
    """Validate and immutably register the catalog-paired data and dictionary."""
    downloader = downloader or HttpDownloader()
    downloads = []
    try:
        for url in (str(release.data_url), str(release.dictionary_url)):
            downloads.append(
                downloader.download(
                    url, paths.data / ".downloads", IPEDS_CHARGES_DATASET.allowed_domains
                )
            )
        read_charge_rows(downloads[0].path)
        read_dictionary(downloads[1].path)
        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        store = ArtifactStore(paths.data / "raw", registry)
        manifests: list[ArtifactManifest] = []
        for definition, download in zip(
            (IPEDS_CHARGES_DATASET, IPEDS_DICTIONARY_DATASET), downloads, strict=True
        ):
            registry.add_dataset(definition)
            manifest = store.register(
                download.path,
                definition,
                release=release.release_id,
                source_url=download.source_url,
                final_url=download.final_url,
                publication_status=release.publication_status.value,
                schema_version=IPEDS_SCHEMA_VERSION,
                vintage=release.release_id,
                artifact_name=Path(urlparse(download.final_url).path).name,
            )
            if manifest.state is ApprovalState.DOWNLOADED:
                manifest = registry.transition(
                    manifest.artifact_id,
                    ApprovalState.VALIDATED,
                    "paired IPEDS charges and dictionary schema validated",
                )
            manifests.append(manifest)
        return RegisteredIPEDSRelease(manifests[0], manifests[1])
    finally:
        for download in downloads:
            download.path.unlink(missing_ok=True)
