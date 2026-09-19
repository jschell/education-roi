"""Validated download and registration of an exact ACS release bundle."""

import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from education_roi.acs.archive import person_csv_columns
from education_roi.acs.models import ACSRelease
from education_roi.acs.source import (
    ACS_PUMS_DATASET,
    ACS_PUMS_DICTIONARY_DATASET,
    REQUIRED_PERSON_COLUMNS,
)
from education_roi.config.paths import ProjectPaths
from education_roi.provenance.downloader import DownloadResult, HttpDownloader
from education_roi.provenance.models import ArtifactManifest, DatasetDefinition
from education_roi.provenance.store import ArtifactStore, Registry


class ACSBundleError(ValueError):
    """An ACS release bundle failed pre-registration validation."""


class ACSDictionaryError(ACSBundleError):
    """The official data dictionary does not satisfy the required schema contract."""


class ACSPersonSchemaError(ACSBundleError):
    """The person archive does not satisfy the required schema contract."""


@dataclass(frozen=True)
class RegisteredACSRelease:
    """The raw person file and dictionary registered as one release bundle."""

    person: ArtifactManifest
    dictionary: ArtifactManifest


@dataclass(frozen=True)
class _ArtifactSpec:
    definition: DatasetDefinition
    url: str
    schema_version: str


def validate_dictionary(path: Path) -> frozenset[str]:
    """Read Census NAME records and require every analytical person variable."""
    variables: set[str] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.reader(source):
                if len(row) >= 2 and row[0] == "NAME":
                    variables.add(row[1])
    except (OSError, UnicodeError, csv.Error) as error:
        raise ACSDictionaryError(f"could not parse ACS dictionary: {error}") from error
    missing = sorted(REQUIRED_PERSON_COLUMNS.difference(variables))
    if missing:
        raise ACSDictionaryError(
            f"ACS dictionary is missing required variables: {', '.join(missing)}"
        )
    return frozenset(variables)


def _specs(release: ACSRelease) -> tuple[_ArtifactSpec, _ArtifactSpec]:
    schema_version = f"{release.vintage}-{release.product.release_label}"
    return (
        _ArtifactSpec(ACS_PUMS_DATASET, release.person_archive_url, schema_version),
        _ArtifactSpec(ACS_PUMS_DICTIONARY_DATASET, release.dictionary_url, schema_version),
    )


def register_acs_release(
    release: ACSRelease,
    paths: ProjectPaths,
    *,
    downloader: HttpDownloader | None = None,
) -> RegisteredACSRelease:
    """Download, validate, then immutably register the person ZIP and dictionary."""
    downloader = downloader or HttpDownloader()
    specs = _specs(release)
    downloads: list[DownloadResult] = []
    try:
        for spec in specs:
            downloads.append(
                downloader.download(
                    spec.url,
                    paths.data / ".downloads",
                    spec.definition.allowed_domains,
                )
            )
        person_columns = person_csv_columns(downloads[0].path)
        missing_person_columns = sorted(REQUIRED_PERSON_COLUMNS.difference(person_columns))
        if missing_person_columns:
            raise ACSPersonSchemaError(
                "ACS person archive is missing required columns: "
                + ", ".join(missing_person_columns)
            )
        validate_dictionary(downloads[1].path)

        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        store = ArtifactStore(paths.data / "raw", registry)
        manifests: list[ArtifactManifest] = []
        for spec, download in zip(specs, downloads, strict=True):
            registry.add_dataset(spec.definition)
            manifests.append(
                store.register(
                    download.path,
                    spec.definition,
                    release=release.release_id,
                    source_url=download.source_url,
                    final_url=download.final_url,
                    publication_status=release.publication_status,
                    schema_version=spec.schema_version,
                    vintage=str(release.vintage),
                    artifact_name=Path(urlparse(spec.url).path).name,
                )
            )
        return RegisteredACSRelease(person=manifests[0], dictionary=manifests[1])
    finally:
        for download in downloads:
            download.path.unlink(missing_ok=True)
