"""Attach reviewed institution graduation cohort evidence to a scenario."""

from pathlib import Path

from pydantic import Field

from education_roi.ipeds.graduation_evidence import GraduationEvidence, resolve_graduation_evidence
from education_roi.scenarios.models import (
    AttendanceBasis,
    Credential,
    ScenarioDefinition,
    StrictModel,
)


class ScenarioGraduationContextError(ValueError):
    """The scenario does not match the reviewed graduation cohort."""


class ScenarioGraduationContext(StrictModel):
    scenario_id: str
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    institution_unitid: int
    evidence: GraduationEvidence
    completion_use: str = "CONTEXT_ONLY"
    note: str = (
        "Institution-level first-time full-time bachelor's cohort at 150% of normal time. "
        "No on-time, late, transfer, or noncompletion scenario probability is inferred."
    )


def review_scenario_graduation(
    scenario: ScenarioDefinition, table: Path
) -> ScenarioGraduationContext:
    """Associate one exact final cohort without resolving outcome branch probabilities."""
    education = scenario.education
    institution = education.institution if education is not None else None
    if education is None or institution is None:
        raise ScenarioGraduationContextError("scenario requires an education institution")
    if education.credential is not Credential.BACHELORS:
        raise ScenarioGraduationContextError("graduation cohort requires a bachelor's scenario")
    if institution.attendance_basis is not AttendanceBasis.FULL_TIME:
        raise ScenarioGraduationContextError("graduation cohort requires full-time attendance")
    pins = {pin.dataset: pin.release for pin in scenario.data.pins}
    pinned = pins.get("ipeds-graduation-rates")
    if pinned not in {"2022-23-final", "2023-24-final"}:
        raise ScenarioGraduationContextError(
            "scenario must pin ipeds-graduation-rates to a reviewed final release"
        )
    evidence = resolve_graduation_evidence(table, institution.unitid)
    if evidence.release_id != pinned:
        raise ScenarioGraduationContextError(
            f"graduation table release {evidence.release_id} differs from scenario pin {pinned}"
        )
    if (
        evidence.cohort_scope != "bachelors_seeking_first_time_full_time"
        or evidence.award_outcome != "bachelors_degree"
        or evidence.normal_time_percent != 150
    ):
        raise ScenarioGraduationContextError("graduation table cohort differs from reviewed basis")
    return ScenarioGraduationContext(
        scenario_id=scenario.id,
        configuration_hash=scenario.configuration_hash,
        institution_unitid=institution.unitid,
        evidence=evidence,
    )
