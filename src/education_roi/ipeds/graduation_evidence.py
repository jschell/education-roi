"""Resolve a verified processed graduation observation without forecasting completion."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field

from education_roi.ipeds.graduation_comparison import (
    IPEDSGraduationComparisonError,
    _table,
    _verify_processing_manifest,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel


class GraduationEvidenceStatus(StrEnum):
    OBSERVED = "OBSERVED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class GraduationEvidence(StrictModel):
    status: GraduationEvidenceStatus
    unitid: int = Field(gt=0)
    release_id: str
    publication_status: str
    cohort_year: int
    cohort_scope: str
    award_outcome: str
    normal_time_percent: int
    adjusted_cohort: int | None
    bachelors_awards: int | None
    observed_rate: float | None
    unavailable_reason: str | None
    cohort_status: str | None
    award_status: str | None
    data_artifact_id: str
    dictionary_artifact_id: str
    transformation_version: str
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation: str = (
        "Observed institution cohort rate; not a program-specific or individual "
        "completion probability. No scenario completion branch is resolved."
    )


def resolve_graduation_evidence(path: Path, unitid: int) -> GraduationEvidence:
    """Read one institution from a hash-verified final processed GR table."""
    if unitid <= 0:
        raise ValueError("UNITID must be positive")
    rows, metadata = _table(path)
    if metadata["release_id"] not in {"2022-23-final", "2023-24-final"}:
        raise IPEDSGraduationComparisonError(
            "graduation evidence requires a reviewed final release"
        )
    manifest_hash = _verify_processing_manifest(path, metadata, len(rows))
    row = rows.get(unitid)
    if row is None:
        status = GraduationEvidenceStatus.INSUFFICIENT_DATA
        reason = "institution absent from the exact processed cohort table"
    elif row["observed_rate"] is None:
        status = GraduationEvidenceStatus.INSUFFICIENT_DATA
        reason = str(row["unavailable_reason"])
    else:
        status = GraduationEvidenceStatus.OBSERVED
        reason = None
    return GraduationEvidence(
        status=status,
        unitid=unitid,
        release_id=str(metadata["release_id"]),
        publication_status=str(metadata["publication_status"]),
        cohort_year=int(metadata["cohort_year"]),
        cohort_scope=str(metadata["cohort_scope"]),
        award_outcome=str(metadata["award_outcome"]),
        normal_time_percent=int(metadata["normal_time_percent"]),
        adjusted_cohort=row["adjusted_cohort"] if row else None,
        bachelors_awards=row["bachelors_awards"] if row else None,
        observed_rate=row["observed_rate"] if row else None,
        unavailable_reason=reason,
        cohort_status=row["cohort_status"] if row else None,
        award_status=row["award_status"] if row else None,
        data_artifact_id=str(metadata["data_artifact_id"]),
        dictionary_artifact_id=str(metadata["dictionary_artifact_id"]),
        transformation_version=str(metadata["transformation_version"]),
        table_sha256=sha256_file(path)[0],
        manifest_sha256=manifest_hash,
    )
