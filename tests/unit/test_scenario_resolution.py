from pathlib import Path

import pytest

from education_roi.scenarios import (
    FixtureValueProvider,
    ProviderValue,
    ResolutionStatus,
    ResolvedScenarioGraph,
    ScenarioResolutionError,
    load_scenario_file,
    resolve_configuration_graph,
    resolve_scenario_graph,
)

EXAMPLES = Path(__file__).parents[2] / "scenarios" / "examples"


def graph() -> ResolvedScenarioGraph:
    return resolve_scenario_graph(
        (
            load_scenario_file(EXAMPLES / "example-bachelors.yaml"),
            load_scenario_file(EXAMPLES / "workforce-high-school.yaml"),
        )
    )


def fixture_values() -> dict[str, ProviderValue]:
    return {
        "example-bachelors.costs.tuition_and_fees": ProviderValue(
            value=12000,
            source="ipeds",
            vintage="2023-24-provisional",
            artifact_id="ipeds-artifact-sha256",
            transformation_ids=("select-unitid-236948",),
        ),
        "example-bachelors.costs.books_and_supplies": ProviderValue(
            value=900,
            source="ipeds",
            vintage="2023-24-provisional",
            artifact_id="ipeds-artifact-sha256",
            transformation_ids=("select-unitid-236948",),
        ),
        "example-bachelors.costs.grants_and_scholarships": ProviderValue(
            value=5000,
            source="college-scorecard",
            vintage="2024-10",
            artifact_id="scorecard-artifact-sha256",
            transformation_ids=("select-unitid-236948",),
        ),
    }


def test_resolution_is_deterministic_and_preserves_zero_and_provenance() -> None:
    first = resolve_configuration_graph(graph(), FixtureValueProvider(fixture_values()))
    second = resolve_configuration_graph(
        graph(), FixtureValueProvider(dict(reversed(tuple(fixture_values().items()))))
    )
    assert first == second
    assert first.topological_order == ("workforce-high-school", "example-bachelors")
    assert len(first.resolution_hash) == 64
    bachelors = first.scenarios[1]
    tuition = next(item for item in bachelors.values if item.path == "costs.tuition_and_fees")
    living = next(item for item in bachelors.values if item.path == "costs.incremental_living_cost")
    assert tuition.artifact_id == "ipeds-artifact-sha256"
    assert tuition.transformation_ids == ("select-unitid-236948",)
    assert living.value == 0
    assert living.source == "scenario-assumption"
    assert bachelors.status is ResolutionStatus.INSUFFICIENT_DATA


def test_absent_provider_value_propagates_insufficient_data_not_zero() -> None:
    resolved = resolve_configuration_graph(graph(), FixtureValueProvider({}))
    bachelors = resolved.scenarios[1]
    tuition = next(item for item in bachelors.values if item.path == "costs.tuition_and_fees")
    assert tuition.status is ResolutionStatus.INSUFFICIENT_DATA
    assert tuition.value is None
    assert "exact pinned release" in (tuition.note or "")


def test_provider_cannot_substitute_a_different_source_or_vintage() -> None:
    values = fixture_values()
    values["example-bachelors.costs.tuition_and_fees"] = ProviderValue(
        value=1,
        source="ipeds",
        vintage="2024-25-provisional",
        artifact_id="wrong-release",
    )
    with pytest.raises(ScenarioResolutionError, match="expected ipeds 2023-24-provisional"):
        resolve_configuration_graph(graph(), FixtureValueProvider(values))


def test_unpinned_value_request_is_rejected() -> None:
    source_graph = graph()
    bachelors = source_graph.scenarios[1]
    pins = tuple(pin for pin in bachelors.data.pins if pin.dataset != "ipeds")
    changed = bachelors.model_copy(
        update={"data": bachelors.data.model_copy(update={"pins": pins})}
    )
    changed_graph = source_graph.__class__(
        source_graph.schema_version,
        source_graph.topological_order,
        (source_graph.scenarios[0], changed),
        source_graph.graph_hash,
    )
    with pytest.raises(ScenarioResolutionError, match="unpinned dataset ipeds"):
        resolve_configuration_graph(changed_graph, FixtureValueProvider(fixture_values()))
