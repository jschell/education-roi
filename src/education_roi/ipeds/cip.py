"""Versioned CIP crosswalk contracts with no implicit code reinterpretation."""

from enum import StrEnum
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from pydantic import ConfigDict, Field, HttpUrl, field_validator, model_validator

from education_roi.scenarios.models import StrictModel

CIP_CODE_PATTERN = r"^\d{2}(?:\.\d{2,4})?$"


class CIPCrosswalkError(ValueError):
    """A CIP mapping is missing, incompatible, or ambiguous."""


class CIPRelationship(StrEnum):
    EXACT = "exact"
    REVISED = "revised"
    SPLIT = "split"
    MERGED = "merged"


class CIPMappingConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CIPMapping(StrictModel):
    source_code: str = Field(pattern=CIP_CODE_PATTERN)
    target_code: str = Field(pattern=CIP_CODE_PATTERN)
    relationship: CIPRelationship
    confidence: CIPMappingConfidence
    note: str | None = None


class CIPCrosswalk(StrictModel):
    """One immutable, directional NCES CIP edition crosswalk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    crosswalk_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mappings: tuple[CIPMapping, ...] = Field(min_length=1)

    @field_validator("source_url")
    @classmethod
    def require_official_nces_source(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not (host == "nces.ed.gov" or host.endswith(".nces.ed.gov")):
            raise ValueError("CIP crosswalk source must use HTTPS on an official NCES domain")
        return value

    @model_validator(mode="after")
    def validate_direction_and_rows(self) -> Self:
        if self.source_version == self.target_version:
            raise ValueError("crosswalk source and target versions must differ")
        pairs = [(mapping.source_code, mapping.target_code) for mapping in self.mappings]
        if len(pairs) != len(set(pairs)):
            raise ValueError("CIP crosswalk contains duplicate source/target pairs")
        return self

    @classmethod
    def from_file(cls, path: Path) -> Self:
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CIPCrosswalkError(f"invalid CIP crosswalk {path}: {error}") from error


class CIPResolution(StrictModel):
    source_code: str = Field(pattern=CIP_CODE_PATTERN)
    source_version: str
    target_code: str = Field(pattern=CIP_CODE_PATTERN)
    target_version: str
    relationship: CIPRelationship
    confidence: CIPMappingConfidence
    crosswalk_id: str | None = None
    crosswalk_sha256: str | None = None
    review_required: bool


def resolve_cip(
    source_code: str,
    source_version: str,
    target_version: str,
    *,
    crosswalk: CIPCrosswalk | None = None,
    target_code: str | None = None,
) -> CIPResolution:
    """Resolve one code, requiring explicit evidence and disambiguation across versions."""
    if source_version == target_version:
        if crosswalk is not None or (target_code is not None and target_code != source_code):
            raise CIPCrosswalkError("same-version CIP resolution must preserve the source code")
        return CIPResolution(
            source_code=source_code,
            source_version=source_version,
            target_code=source_code,
            target_version=target_version,
            relationship=CIPRelationship.EXACT,
            confidence=CIPMappingConfidence.HIGH,
            review_required=False,
        )
    if crosswalk is None:
        raise CIPCrosswalkError(
            f"CIP {source_version} to {target_version} requires an explicit crosswalk"
        )
    if (crosswalk.source_version, crosswalk.target_version) != (
        source_version,
        target_version,
    ):
        raise CIPCrosswalkError("CIP crosswalk direction does not match requested versions")
    matches = tuple(mapping for mapping in crosswalk.mappings if mapping.source_code == source_code)
    if target_code is not None:
        matches = tuple(mapping for mapping in matches if mapping.target_code == target_code)
    if not matches:
        raise CIPCrosswalkError(f"CIP crosswalk has no mapping for {source_version} {source_code}")
    if len(matches) != 1:
        targets = ", ".join(sorted(mapping.target_code for mapping in matches))
        raise CIPCrosswalkError(
            f"CIP mapping for {source_code} is ambiguous; choose one target: {targets}"
        )
    mapping = matches[0]
    return CIPResolution(
        source_code=source_code,
        source_version=source_version,
        target_code=mapping.target_code,
        target_version=target_version,
        relationship=mapping.relationship,
        confidence=mapping.confidence,
        crosswalk_id=crosswalk.crosswalk_id,
        crosswalk_sha256=crosswalk.source_sha256,
        review_required=(
            mapping.relationship is not CIPRelationship.EXACT
            or mapping.confidence is not CIPMappingConfidence.HIGH
        ),
    )
