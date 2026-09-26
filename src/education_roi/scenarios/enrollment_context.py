"""Attach verified fall enrollment context to an education scenario."""

from pathlib import Path

from pydantic import Field

from education_roi.ipeds.enrollment import EnrollmentCohort
from education_roi.ipeds.enrollment_evidence import EnrollmentEvidence, resolve_enrollment_evidence
from education_roi.scenarios.models import (
    AttendanceBasis,
    Credential,
    ScenarioDefinition,
    StrictModel,
)


class ScenarioEnrollmentContextError(ValueError):
    """The scenario does not match the selected enrollment population or release."""


class ScenarioEnrollmentContext(StrictModel):
    scenario_id: str
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    institution_unitid: int
    evidence: EnrollmentEvidence
    enrollment_use: str = "CONTEXT_ONLY"
    note: str = (
        "Institutional fall enrollment in an exact reported category. This is not an "
        "admission, completion, transfer-out, or individual outcome probability."
    )


def review_scenario_enrollment(
    scenario: ScenarioDefinition, table: Path, cohort: EnrollmentCohort
) -> ScenarioEnrollmentContext:
    """Associate one verified enrollment count without changing scenario outcomes."""
    education = scenario.education
    institution = education.institution if education is not None else None
    if education is None or institution is None:
        raise ScenarioEnrollmentContextError("scenario requires an education institution")
    if cohort is not EnrollmentCohort.ALL_STUDENTS:
        if education.credential not in (
            Credential.CERTIFICATE,
            Credential.ASSOCIATE,
            Credential.BACHELORS,
        ):
            raise ScenarioEnrollmentContextError(
                "selected cohort requires an undergraduate scenario"
            )
        expected_attendance = (
            AttendanceBasis.FULL_TIME
            if cohort
            in (EnrollmentCohort.FULL_TIME_FIRST_TIME, EnrollmentCohort.FULL_TIME_TRANSFER_IN)
            else AttendanceBasis.PART_TIME
        )
        if institution.attendance_basis is not expected_attendance:
            raise ScenarioEnrollmentContextError(
                f"selected enrollment cohort requires {expected_attendance.value} attendance"
            )
    pins = {pin.dataset: pin.release for pin in scenario.data.pins}
    if pins.get("ipeds-fall-enrollment") != "2023-24-final":
        raise ScenarioEnrollmentContextError(
            "scenario must pin ipeds-fall-enrollment to 2023-24-final"
        )
    evidence = resolve_enrollment_evidence(table, institution.unitid, cohort)
    return ScenarioEnrollmentContext(
        scenario_id=scenario.id,
        configuration_hash=scenario.configuration_hash,
        institution_unitid=institution.unitid,
        evidence=evidence,
    )
