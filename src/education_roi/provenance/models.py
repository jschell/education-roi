"""Validated provenance contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ApprovalState(StrEnum):
    """Lifecycle states for source artifacts."""

    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    VALIDATED = "VALIDATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


ALLOWED_TRANSITIONS: dict[ApprovalState, frozenset[ApprovalState]] = {
    ApprovalState.DISCOVERED: frozenset({ApprovalState.DOWNLOADED, ApprovalState.REJECTED}),
    ApprovalState.DOWNLOADED: frozenset(
        {ApprovalState.VALIDATED, ApprovalState.REVIEW_REQUIRED, ApprovalState.REJECTED}
    ),
    ApprovalState.VALIDATED: frozenset(
        {ApprovalState.APPROVED, ApprovalState.REVIEW_REQUIRED, ApprovalState.REJECTED}
    ),
    ApprovalState.REVIEW_REQUIRED: frozenset(
        {ApprovalState.VALIDATED, ApprovalState.APPROVED, ApprovalState.REJECTED}
    ),
    ApprovalState.APPROVED: frozenset({ApprovalState.REVIEW_REQUIRED, ApprovalState.REJECTED}),
    ApprovalState.REJECTED: frozenset(),
}


class DatasetDefinition(BaseModel):
    """Stable identity and source policy for a dataset."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    publisher: str = Field(min_length=1)
    name: str = Field(min_length=1)
    allowed_domains: tuple[str, ...] = Field(min_length=1)

    @field_validator("allowed_domains")
    @classmethod
    def normalize_domains(cls, domains: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(domain.lower().rstrip(".") for domain in domains)


class ArtifactManifest(BaseModel):
    """Machine-readable identity for immutable source bytes."""

    model_config = ConfigDict(frozen=True)

    manifest_version: str = "1.0"
    artifact_id: str = Field(pattern=r"^[a-z][a-z0-9-]+:[^:]+:[0-9a-f]{64}$")
    dataset_id: str
    publisher: str
    release: str
    vintage: str | None = None
    retrieved_at: datetime
    source_url: HttpUrl
    final_url: HttpUrl
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(ge=0)
    publication_status: str
    schema_version: str
    software_version: str
    storage_path: str
    state: ApprovalState = ApprovalState.DOWNLOADED

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("storage_path")
    @classmethod
    def require_relative_storage_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("storage_path must be a safe relative path")
        return value


class TransformationManifest(BaseModel):
    """Lineage for a processed artifact."""

    model_config = ConfigDict(frozen=True)

    manifest_version: str = "1.0"
    transformation_id: str
    created_at: datetime
    software_version: str
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_artifact_ids: tuple[str, ...] = Field(min_length=1)
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
