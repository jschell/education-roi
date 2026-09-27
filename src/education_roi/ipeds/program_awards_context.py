"""Review historical CIP and institution identity before consulting program awards."""

from pathlib import Path

from pydantic import Field

from education_roi.ipeds.cip import CIPCrosswalk, CIPResolution, resolve_cip
from education_roi.ipeds.identity import (
    InstitutionHistory,
    InstitutionRelationship,
    InstitutionResolution,
    resolve_unitid,
)
from education_roi.ipeds.program_awards_evidence import (
    ProgramAwardEvidence,
    resolve_program_awards_evidence,
)
from education_roi.scenarios.models import StrictModel

TARGET_RELEASE = "2023-24-final"
TARGET_CIP_VERSION = "2020"


class ProgramAwardContext(StrictModel):
    status: str
    source_unitid: int = Field(gt=0)
    source_release: str
    source_cip_code: str
    source_cip_version: str
    target_release: str
    cip_resolution: CIPResolution
    institution_resolution: InstitutionResolution
    evidence: ProgramAwardEvidence | None = None
    review_reasons: tuple[str, ...]
    interpretation: str = (
        "A cross-edition code or institution change does not establish comparable program "
        "production. Observed counts are awards, not distinct graduates or completion odds."
    )


def review_program_awards_context(
    table: Path,
    unitid: int,
    source_release: str,
    cip_code: str,
    cip_version: str,
    major_number: int,
    award_level: int,
    *,
    crosswalk: CIPCrosswalk | None = None,
    history: InstitutionHistory | None = None,
    target_cip_code: str | None = None,
    target_unitid: int | None = None,
) -> ProgramAwardContext:
    """Read verified awards only after exact CIP and continuing UNITID resolution."""
    if not source_release or not cip_version or major_number not in (1, 2) or award_level <= 0:
        raise ValueError("requires a source release, CIP edition, major 1/2, and award level")
    cip = resolve_cip(
        cip_code,
        cip_version,
        TARGET_CIP_VERSION,
        crosswalk=crosswalk,
        target_code=target_cip_code,
    )
    institution = resolve_unitid(
        unitid,
        source_release,
        TARGET_RELEASE,
        history=history,
        target_unitid=target_unitid,
    )
    reasons = []
    if cip.review_required:
        reasons.append("CIP mapping requires review before comparing program awards")
    if (
        institution.review_required
        or institution.relationship is not InstitutionRelationship.CONTINUING
    ):
        reasons.append("institution identity requires review before comparing program awards")
    evidence = None
    if not reasons:
        assert institution.target_unitid is not None
        evidence = resolve_program_awards_evidence(
            table, institution.target_unitid, cip.target_code, major_number, award_level
        )
    return ProgramAwardContext(
        status="REVIEW_REQUIRED" if reasons else evidence.status if evidence else "INVALID",
        source_unitid=unitid,
        source_release=source_release,
        source_cip_code=cip_code,
        source_cip_version=cip_version,
        target_release=TARGET_RELEASE,
        cip_resolution=cip,
        institution_resolution=institution,
        evidence=evidence,
        review_reasons=tuple(reasons),
    )
