from pathlib import Path

import pytest
from pydantic import ValidationError

from education_roi.scenarios import (
    Credential,
    EducationConfig,
    MoneyBasisConfig,
    ScenarioDocument,
    ScenarioGraphError,
    ValueSpec,
    ValueStatus,
    load_scenario_file,
    resolve_scenario_graph,
)

EXAMPLES = Path(__file__).parents[2] / "scenarios" / "examples"


def documents() -> tuple[ScenarioDocument, ScenarioDocument]:
    workforce = load_scenario_file(EXAMPLES / "workforce-high-school.yaml")
    bachelors = load_scenario_file(EXAMPLES / "example-bachelors.yaml")
    return workforce, bachelors


def test_examples_resolve_deterministically_with_counterfactual_first() -> None:
    workforce, bachelors = documents()
    first = resolve_scenario_graph((bachelors, workforce))
    second = resolve_scenario_graph((workforce, bachelors))
    assert first == second
    assert first.topological_order == ("workforce-high-school", "example-bachelors")
    assert len(first.graph_hash) == 64
    assert all(len(item.configuration_hash) == 64 for item in first.scenarios)


def test_missing_reference_cycle_and_money_basis_mismatch_are_rejected() -> None:
    workforce, bachelors = documents()
    missing = bachelors.model_copy(
        update={"scenario": bachelors.scenario.model_copy(update={"counterfactual": "missing"})}
    )
    with pytest.raises(ScenarioGraphError, match="references missing"):
        resolve_scenario_graph((workforce, missing))

    cyclic_workforce = workforce.model_copy(
        update={
            "scenario": workforce.scenario.model_copy(
                update={"counterfactual": "example-bachelors"}
            )
        }
    )
    with pytest.raises(ScenarioGraphError, match="cyclic"):
        resolve_scenario_graph((cyclic_workforce, bachelors))

    nominal = workforce.scenario.assumptions.model_copy(
        update={"money_basis": MoneyBasisConfig(mode="nominal")}
    )
    mismatched = workforce.model_copy(
        update={"scenario": workforce.scenario.model_copy(update={"assumptions": nominal})}
    )
    with pytest.raises(ScenarioGraphError, match="incompatible money bases"):
        resolve_scenario_graph((mismatched, bachelors))


def test_value_states_never_infer_missing_values_as_zero() -> None:
    with pytest.raises(ValidationError, match="explicit value"):
        ValueSpec(status=ValueStatus.PROVIDED, source="scenario")
    with pytest.raises(ValidationError, match="pinned vintage"):
        ValueSpec(status=ValueStatus.RESOLVE_FROM_DATA, source="ipeds")
    unresolved = ValueSpec(
        status=ValueStatus.INSUFFICIENT_DATA,
        source="federal-student-aid",
    )
    assert unresolved.value is None


def test_credential_duration_and_negative_costs_are_rejected() -> None:
    _, bachelors = documents()
    education = bachelors.scenario.education
    assert education is not None
    with pytest.raises(ValidationError, match="bachelors duration"):
        EducationConfig(
            credential=Credential.BACHELORS,
            expected_duration_years=1,
            institution=education.institution,
            program=education.program,
            completion=education.completion,
        )
    costs = bachelors.scenario.costs.model_dump(mode="json")
    costs["incremental_living_cost"]["value"] = -1
    payload = bachelors.model_dump(mode="json")
    payload["scenario"]["costs"] = costs
    with pytest.raises(ValidationError, match="cost values cannot be negative"):
        ScenarioDocument.model_validate(payload)


def test_json_schema_is_versioned_and_forbids_unknown_fields() -> None:
    schema = ScenarioDocument.model_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "1.0"
    assert schema["additionalProperties"] is False
    workforce, _ = documents()
    payload = workforce.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        ScenarioDocument.model_validate(payload)
