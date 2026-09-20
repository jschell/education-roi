from pathlib import Path

from education_roi.cashflow import ReturnPerspective
from education_roi.scenarios import (
    AnalysisStatus,
    EarningsFixture,
    EarningsProfile,
    FixtureValueProvider,
    OutcomeName,
    ResolutionStatus,
    ResolvedConfigurationGraph,
    ResolvedScenario,
    ResolvedValue,
    ValueStatus,
    analyze_scenario,
    load_scenario_file,
    resolve_configuration_graph,
    resolve_scenario_graph,
)

EXAMPLES = Path(__file__).parents[2] / "scenarios" / "examples"


def test_analysis_refuses_unresolved_required_values() -> None:
    source = resolve_scenario_graph(
        (
            load_scenario_file(EXAMPLES / "workforce-high-school.yaml"),
            load_scenario_file(EXAMPLES / "example-bachelors.yaml"),
        )
    )
    resolved = resolve_configuration_graph(source, FixtureValueProvider({}))
    result = analyze_scenario(
        source,
        resolved,
        EarningsFixture(profiles={}),
        "example-bachelors",
        ReturnPerspective.CONDITIONAL_GRADUATE,
    )
    assert result.status is AnalysisStatus.INSUFFICIENT_DATA
    assert "unresolved required values" in (result.reason or "")
    assert result.result is None


def test_enrollment_requires_profiles_for_every_nonzero_outcome() -> None:
    source = resolve_scenario_graph(
        (
            load_scenario_file(EXAMPLES / "workforce-high-school.yaml"),
            load_scenario_file(EXAMPLES / "example-bachelors.yaml"),
        )
    )
    initial = resolve_configuration_graph(source, FixtureValueProvider({}))
    repaired = []
    for scenario in initial.scenarios:
        values = tuple(
            ResolvedValue(
                path=item.path,
                status=ResolutionStatus.RESOLVED,
                value=0,
                source="test-fixture",
                input_status=ValueStatus.PROVIDED,
            )
            if item.status is ResolutionStatus.INSUFFICIENT_DATA
            else item
            for item in scenario.values
        )
        repaired.append(
            ResolvedScenario(
                id=scenario.id,
                configuration_hash=scenario.configuration_hash,
                status=ResolutionStatus.RESOLVED,
                values=values,
                dataset_references=scenario.dataset_references,
                resolution_hash=scenario.resolution_hash,
            )
        )
    resolved = ResolvedConfigurationGraph(
        schema_version=initial.schema_version,
        source_graph_hash=initial.source_graph_hash,
        topological_order=initial.topological_order,
        status=ResolutionStatus.RESOLVED,
        scenarios=tuple(repaired),
        resolution_hash=initial.resolution_hash,
    )
    ages = range(18, 66)
    profile = EarningsProfile(
        source="acs-pums",
        vintage="2024-5yr",
        artifact_id="synthetic-acs",
        quantile=0.5,
        enrollment_years=4,
        earnings_by_age={age: float(max(0, age - 21) * 1000) for age in ages},
    )
    baseline = profile.model_copy(update={"enrollment_years": 0})
    fixture = EarningsFixture(
        profiles={
            "example-bachelors": {OutcomeName.GRADUATE_ON_TIME: profile},
            "workforce-high-school": {OutcomeName.BASE: baseline},
        }
    )
    result = analyze_scenario(
        source, resolved, fixture, "example-bachelors", ReturnPerspective.ENROLLMENT
    )
    assert result.status is AnalysisStatus.INSUFFICIENT_DATA
    assert "graduate_late" in (result.reason or "")
