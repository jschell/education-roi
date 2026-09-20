"""Reviewed IPEDS release catalog and deterministic selection policy."""

from enum import StrEnum
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class IPEDSCatalogError(ValueError):
    """The release catalog or requested selection is invalid or ambiguous."""


class IPEDSPublicationStatus(StrEnum):
    PRELIMINARY = "preliminary"
    PROVISIONAL = "provisional"
    FINAL = "final"


class IPEDSComponent(StrEnum):
    INSTITUTIONAL_CHARACTERISTICS = "institutional-characteristics"
    ACADEMIC_YEAR_CHARGES = "academic-year-charges"


class IPEDSRelease(BaseModel):
    """One human-reviewed release discovered through an official NCES inventory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_id: str = Field(pattern=r"^\d{4}-\d{2}-(?:preliminary|provisional|final)$")
    collection_year: int = Field(ge=1990, le=2200)
    component: IPEDSComponent
    publication_status: IPEDSPublicationStatus
    data_url: HttpUrl
    dictionary_url: HttpUrl
    inventory_url: HttpUrl

    @field_validator("data_url", "dictionary_url", "inventory_url")
    @classmethod
    def require_official_https(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not (host == "nces.ed.gov" or host.endswith(".nces.ed.gov")):
            raise ValueError("IPEDS catalog URLs must use HTTPS on an official NCES domain")
        return value

    @model_validator(mode="after")
    def release_matches_fields(self) -> Self:
        expected_prefix = f"{self.collection_year}-{str(self.collection_year + 1)[-2:]}-"
        if not self.release_id.startswith(expected_prefix):
            raise ValueError("release ID does not match collection year")
        if not self.release_id.endswith(f"-{self.publication_status.value}"):
            raise ValueError("release ID does not match publication status")
        return self


class IPEDSReleaseCatalog(BaseModel):
    """Versioned reviewed inventory; the catalog itself is an auditable input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0"
    reviewed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    releases: tuple[IPEDSRelease, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_release_component_pairs(self) -> Self:
        keys = [(item.release_id, item.component) for item in self.releases]
        if len(keys) != len(set(keys)):
            raise ValueError("catalog contains duplicate release/component entries")
        return self

    @classmethod
    def from_file(cls, path: Path) -> Self:
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise IPEDSCatalogError(f"invalid IPEDS release catalog {path}: {error}") from error


def select_release(
    catalog: IPEDSReleaseCatalog,
    component: IPEDSComponent,
    *,
    release_id: str | None = None,
    allow_nonfinal: bool = False,
) -> IPEDSRelease:
    """Select an exact release or newest final; provisional data requires opt-in."""
    candidates = tuple(item for item in catalog.releases if item.component is component)
    if release_id is not None:
        matches = tuple(item for item in candidates if item.release_id == release_id)
        if not matches:
            raise IPEDSCatalogError(f"catalog has no {component.value} release {release_id}")
        selected = matches[0]
        if selected.publication_status is not IPEDSPublicationStatus.FINAL and not allow_nonfinal:
            message = (
                f"release {release_id} is {selected.publication_status.value}; "
                "explicit opt-in required"
            )
            raise IPEDSCatalogError(message)
        return selected

    finals = tuple(
        item for item in candidates if item.publication_status is IPEDSPublicationStatus.FINAL
    )
    if not finals:
        raise IPEDSCatalogError(f"catalog has no final {component.value} release")
    newest_year = max(item.collection_year for item in finals)
    newest = tuple(item for item in finals if item.collection_year == newest_year)
    if len(newest) != 1:
        raise IPEDSCatalogError(
            f"catalog has ambiguous final {component.value} releases for {newest_year}"
        )
    return newest[0]
