"""Resumable orchestration for Zhang reproduction source artifacts."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from shutil import disk_usage

from education_roi.acs.models import ACSProduct, ACSRelease
from education_roi.acs.pipeline import transform_zhang_archive
from education_roi.acs.registration import RegisteredACSRelease, register_acs_release
from education_roi.config.paths import ProjectPaths
from education_roi.provenance.models import ArtifactManifest
from education_roi.provenance.store import Registry

DEFAULT_ZHANG_VINTAGES = tuple(range(2009, 2022))


def resolve_vintages(
    explicit: tuple[int, ...], from_year: int | None, to_year: int | None
) -> tuple[int, ...]:
    """Resolve one or more explicit vintages or an inclusive year range."""
    if explicit and (from_year is not None or to_year is not None):
        raise ValueError("use either --vintage or --from-year/--to-year, not both")
    if explicit:
        resolved = tuple(sorted(set(explicit)))
    elif from_year is not None or to_year is not None:
        if from_year is None or to_year is None:
            raise ValueError("--from-year and --to-year must be provided together")
        if from_year > to_year:
            raise ValueError("--from-year cannot exceed --to-year")
        resolved = tuple(range(from_year, to_year + 1))
    else:
        resolved = DEFAULT_ZHANG_VINTAGES
    if any(year < 2005 or year > 2100 for year in resolved):
        raise ValueError("ACS vintages must be between 2005 and 2100")
    return resolved


class BootstrapStatus(StrEnum):
    PLANNED = "PLANNED"
    COMPLETE = "COMPLETE"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BootstrapItem:
    source: str
    release: str
    status: BootstrapStatus
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "release": self.release,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BootstrapReport:
    execute: bool
    free_bytes: int
    minimum_free_bytes: int
    items: tuple[BootstrapItem, ...]

    @property
    def ready(self) -> bool:
        return bool(self.items) and all(
            item.status is BootstrapStatus.COMPLETE for item in self.items
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": "execute" if self.execute else "dry-run",
            "free_bytes": self.free_bytes,
            "minimum_free_bytes": self.minimum_free_bytes,
            "ready": self.ready,
            "items": [item.as_dict() for item in self.items],
        }


def _existing_bundle(registry: Registry, release_id: str) -> RegisteredACSRelease | None:
    people = registry.list_artifacts("acs-pums", release_id)
    dictionaries = registry.list_artifacts("acs-pums-dictionary", release_id)
    if not people or not dictionaries:
        return None
    return RegisteredACSRelease(people[-1], dictionaries[-1])


def _processed_manifest(
    paths: ProjectPaths, manifest: ArtifactManifest, release: ACSRelease
) -> Path:
    directory = paths.data / "processed" / "acs-pums" / release.release_id / manifest.sha256
    matches = tuple(directory.glob("*/zhang-sample.manifest.json")) if directory.exists() else ()
    return matches[0] if matches else directory / "missing"


def _acs_item(
    release: ACSRelease, paths: ProjectPaths, registry: Registry, execute: bool
) -> BootstrapItem:
    existing = _existing_bundle(registry, release.release_id)
    if existing is not None and _processed_manifest(paths, existing.person, release).exists():
        return BootstrapItem(
            "acs-pums", release.release_id, BootstrapStatus.COMPLETE, "registered and transformed"
        )
    if not execute:
        detail = (
            "transform registered artifacts"
            if existing is not None
            else "download, register, and transform"
        )
        return BootstrapItem("acs-pums", release.release_id, BootstrapStatus.PLANNED, detail)
    try:
        bundle = existing or register_acs_release(release, paths)
        archive = paths.data / "raw" / bundle.person.storage_path
        transform_zhang_archive(archive, paths.data / "processed", bundle.person, release)
    except Exception as error:  # noqa: BLE001 - report per-release failures and continue
        return BootstrapItem("acs-pums", release.release_id, BootstrapStatus.FAILED, str(error))
    return BootstrapItem(
        "acs-pums", release.release_id, BootstrapStatus.COMPLETE, "registered and transformed"
    )


def bootstrap_zhang_sources(
    paths: ProjectPaths,
    *,
    vintages: tuple[int, ...] = DEFAULT_ZHANG_VINTAGES,
    execute: bool = False,
    minimum_free_gb: float = 70.0,
) -> BootstrapReport:
    """Plan or execute supported ACS acquisition while exposing unresolved source blockers."""
    if not vintages or tuple(sorted(set(vintages))) != vintages:
        raise ValueError("vintages must be unique and ordered")
    if minimum_free_gb < 0:
        raise ValueError("minimum_free_gb cannot be negative")
    usage = disk_usage(paths.root)
    minimum_free_bytes = int(minimum_free_gb * 1024**3)
    if execute and usage.free < minimum_free_bytes:
        raise OSError(
            f"insufficient disk space: {usage.free / 1024**3:.2f} GiB free; "
            f"{minimum_free_gb:.2f} GiB required"
        )
    registry = Registry(paths.data / "manifests" / "registry.sqlite")
    items: list[BootstrapItem] = []
    for vintage in vintages:
        if vintage == 2020:
            items.append(
                BootstrapItem(
                    "acs-pums",
                    "2020-experimental-1yr-us",
                    BootstrapStatus.BLOCKED,
                    "experimental 2020 release requires a separately approved source policy",
                )
            )
            continue
        release = ACSRelease(
            vintage=vintage,
            product=ACSProduct.ONE_YEAR,
            geography="us",
            publication_status="final",
        )
        items.append(_acs_item(release, paths, registry, execute))
    items.append(
        BootstrapItem(
            "bls-cpi",
            "annual-CPI-U-through-2021",
            BootstrapStatus.BLOCKED,
            "BLS CPI acquisition adapter is not yet implemented",
        )
    )
    return BootstrapReport(execute, usage.free, minimum_free_bytes, tuple(items))
