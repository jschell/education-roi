"""Scenario enrollment review stays linked to its exact reported population."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.ipeds.enrollment import EnrollmentCohort
from education_roi.ipeds.enrollment_evidence import EnrollmentEvidence
from education_roi.scenarios import (
    AttendanceBasis,
    Credential,
    DatasetPin,
    ScenarioDefinition,
    load_scenario_file,
)
from education_roi.scenarios.enrollment_context import (
    ScenarioEnrollmentContextError,
    review_scenario_enrollment,
)

EXAMPLES = Path(__file__).parents[2] / "scenarios/examples"


def scenario_with_pin() -> ScenarioDefinition:
    original = load_scenario_file(EXAMPLES / "example-bachelors.yaml").scenario
    policy = original.data.model_copy(
        update={
            "pins": (
                *original.data.pins,
                DatasetPin(dataset="ipeds-fall-enrollment", release="2023-24-final"),
            ),
        }
    )
    return original.model_copy(update={"data": policy})


def observation() -> EnrollmentEvidence:
    return EnrollmentEvidence(
        status="OBSERVED",
        unitid=236948,
        cohort=EnrollmentCohort.FULL_TIME_FIRST_TIME,
        population="Full-time students, Undergraduate, Degree/certificate-seeking, First-time",
        efalevel=24,
        line=1,
        section=1,
        lstudy=1,
        enrollment_count=6928,
        raw_enrollment_count="6928",
        source_status="R",
        unavailable_reason=None,
        fall_year=2023,
        release_id="2023-24-final",
        publication_status="final",
        data_artifact_id="data-id",
        dictionary_artifact_id="dictionary-id",
        transformation_version="ipeds-ef2023a-enrollment-v1",
        table_sha256="a" * 64,
        manifest_sha256="b" * 64,
    )


def test_context_gates_pin_attendance_and_undergraduate_population(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def lookup(path: Path, unitid: int, cohort: EnrollmentCohort) -> EnrollmentEvidence:
        calls.append((path, unitid, cohort))
        return observation()

    monkeypatch.setattr(
        "education_roi.scenarios.enrollment_context.resolve_enrollment_evidence", lookup
    )
    scenario = scenario_with_pin()
    table = tmp_path / "table.parquet"
    context = review_scenario_enrollment(scenario, table, EnrollmentCohort.FULL_TIME_FIRST_TIME)
    assert calls == [(table, 236948, EnrollmentCohort.FULL_TIME_FIRST_TIME)]
    assert context.configuration_hash == scenario.configuration_hash
    assert context.enrollment_use == "CONTEXT_ONLY"
    assert context.evidence.enrollment_count == 6928
    assert scenario.education is not None and scenario.education.institution is not None
    assert scenario.education.completion.transfer.value == 0.05
    with pytest.raises(ScenarioEnrollmentContextError, match="pin"):
        review_scenario_enrollment(
            load_scenario_file(EXAMPLES / "example-bachelors.yaml").scenario,
            table,
            EnrollmentCohort.FULL_TIME_FIRST_TIME,
        )
    with pytest.raises(ScenarioEnrollmentContextError, match="part_time"):
        review_scenario_enrollment(scenario, table, EnrollmentCohort.PART_TIME_TRANSFER_IN)
    education = scenario.education.model_copy(update={"credential": Credential.MASTERS})
    with pytest.raises(ScenarioEnrollmentContextError, match="undergraduate"):
        review_scenario_enrollment(
            scenario.model_copy(update={"education": education}),
            table,
            EnrollmentCohort.FULL_TIME_TRANSFER_IN,
        )
    part_time = scenario.education.institution.model_copy(
        update={"attendance_basis": AttendanceBasis.PART_TIME}
    )
    education = scenario.education.model_copy(update={"institution": part_time})
    with pytest.raises(ScenarioEnrollmentContextError, match="full_time"):
        review_scenario_enrollment(
            scenario.model_copy(update={"education": education}),
            table,
            EnrollmentCohort.FULL_TIME_FIRST_TIME,
        )
    assert len(calls) == 1


def test_cli_reports_context_without_changing_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.scenarios.enrollment_context.resolve_enrollment_evidence",
        lambda path, unitid, cohort: observation(),
    )
    scenario = scenario_with_pin()
    original = load_scenario_file(EXAMPLES / "example-bachelors.yaml")
    scenario_file = tmp_path / "education.json"
    scenario_file.write_text(original.model_copy(update={"scenario": scenario}).model_dump_json())
    table = tmp_path / "table.parquet"
    table.write_bytes(b"fixture")
    cli = CliRunner().invoke(
        app,
        [
            "scenario",
            "review-enrollment",
            str(EXAMPLES / "workforce-high-school.yaml"),
            str(scenario_file),
            "--scenario-id",
            "example-bachelors",
            "--table",
            str(table),
            "--cohort",
            "full_time_first_time",
        ],
    )
    assert cli.exit_code == 0, cli.stdout
    result = json.loads(cli.stdout)
    assert result["enrollment_use"] == "CONTEXT_ONLY"
    assert result["evidence"]["enrollment_count"] == 6928
    assert result["institution_unitid"] == 236948
