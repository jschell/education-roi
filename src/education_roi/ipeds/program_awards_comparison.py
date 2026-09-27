"""Review one exact C2022_A→C2023_A program award key across verified tables."""

from pathlib import Path

from pydantic import Field

from education_roi.ipeds.identity import (
    InstitutionHistory,
    InstitutionPairingReport,
    InstitutionRelationship,
    pair_unitids,
)
from education_roi.ipeds.program_awards_evidence import (
    IPEDSProgramAwardsTableError,
    ProgramAwardEvidence,
    resolve_program_awards_evidence,
)
from education_roi.scenarios.models import StrictModel


class IPEDSProgramAwardsComparisonError(ValueError):
    """The reviewed releases, key, or table evidence are incompatible."""


class ProgramAwardKeyComparison(StrictModel):
    status: str
    source_unitid: int = Field(gt=0)
    target_unitid: int = Field(gt=0)
    cip_code: str
    major_number: int
    award_level: int
    relative_count_threshold: float = Field(gt=0)
    previous: ProgramAwardEvidence
    current: ProgramAwardEvidence
    institution_pairing: InstitutionPairingReport
    absolute_count_change: int | None
    relative_count_change: float | None
    review_reasons: tuple[str, ...]
    interpretation: str = (
        "Awards are counts from distinct reporting periods, not distinct graduates, "
        "completion probabilities, or a causal change in program quality."
    )


def compare_program_award_key(
    previous_table: Path,
    current_table: Path,
    unitid: int,
    cip_code: str,
    major_number: int,
    award_level: int,
    *,
    target_unitid: int | None = None,
    relative_count_threshold: float = 0.25,
    institution_history: InstitutionHistory | None = None,
) -> ProgramAwardKeyComparison:
    """Compare only a compatible exact key after full-table and identity verification."""
    if relative_count_threshold <= 0:
        raise ValueError("relative count threshold must be positive")
    target = target_unitid if target_unitid is not None else unitid
    try:
        previous = resolve_program_awards_evidence(
            previous_table, unitid, cip_code, major_number, award_level
        )
        current = resolve_program_awards_evidence(
            current_table, target, cip_code, major_number, award_level
        )
    except IPEDSProgramAwardsTableError as error:
        raise IPEDSProgramAwardsComparisonError(str(error)) from error
    if (
        previous.release_id != "2022-23-final"
        or current.release_id != "2023-24-final"
        or previous.cip_version != "2020"
        or current.cip_version != "2020"
        or (previous.period_start, previous.period_end) != ("2021-07-01", "2022-06-30")
        or (current.period_start, current.period_end) != ("2022-07-01", "2023-06-30")
    ):
        raise IPEDSProgramAwardsComparisonError("requires ordered, compatible C2022_A/C2023_A")
    pairing = pair_unitids(
        (unitid,),
        (target,),
        previous.release_id,
        current.release_id,
        history=institution_history,
    )
    reasons = []
    comparable = (
        len(pairing.pairings) == 1
        and not pairing.findings
        and pairing.pairings[0].relationship is InstitutionRelationship.CONTINUING
        and not pairing.pairings[0].review_required
    )
    if not comparable:
        reasons.append("institution identity or target coverage requires review")
    if previous.status != "OBSERVED" or current.status != "OBSERVED":
        reasons.append("an exact program award count is unavailable in one release")
    if previous.source_status != current.source_status:
        reasons.append("source imputation status changed across releases")
    if previous.source_status_review_required or current.source_status_review_required:
        reasons.append("a source imputation status requires review")
    absolute = None
    relative = None
    if comparable and previous.award_count is not None and current.award_count is not None:
        absolute = current.award_count - previous.award_count
        relative = abs(absolute) / previous.award_count if previous.award_count > 0 else None
        if absolute != 0 and (relative is None or relative >= relative_count_threshold):
            reasons.append("relative award-count change meets review threshold")
    return ProgramAwardKeyComparison(
        status="REVIEW_REQUIRED" if reasons else "ACCEPTABLE",
        source_unitid=unitid,
        target_unitid=target,
        cip_code=cip_code,
        major_number=major_number,
        award_level=award_level,
        relative_count_threshold=relative_count_threshold,
        previous=previous,
        current=current,
        institution_pairing=pairing,
        absolute_count_change=absolute,
        relative_count_change=relative,
        review_reasons=tuple(reasons),
    )
