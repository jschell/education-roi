from pathlib import Path

import pytest

from education_roi.cashflow import ReturnPerspective
from education_roi.scenarios import (
    AnalysisStatus,
    ComparisonBundleError,
    ComparisonReport,
    EarningsFixture,
    FixtureValueProvider,
    ResolvedConfigurationGraph,
    ResolvedScenarioGraph,
    ScenarioAnalysis,
    ScenarioComparisonError,
    compare_scenarios,
    load_scenario_file,
    resolve_configuration_graph,
    resolve_scenario_graph,
    verify_comparison_bundle,
    write_comparison_bundle,
)

EXAMPLES = Path(__file__).parents[2] / "scenarios" / "examples"


def graphs() -> tuple[ResolvedScenarioGraph, ResolvedConfigurationGraph]:
    source = resolve_scenario_graph(
        (
            load_scenario_file(EXAMPLES / "workforce-high-school.yaml"),
            load_scenario_file(EXAMPLES / "example-bachelors.yaml"),
        )
    )
    return source, resolve_configuration_graph(source, FixtureValueProvider({}))


def test_comparison_requires_two_unique_scenarios() -> None:
    source, resolved = graphs()
    with pytest.raises(ScenarioComparisonError, match="at least two"):
        compare_scenarios(
            source,
            resolved,
            EarningsFixture(profiles={}),
            ("example-bachelors",),
            ReturnPerspective.CONDITIONAL_GRADUATE,
        )


def test_comparison_bundle_is_deterministic_and_detects_tampering(tmp_path: Path) -> None:
    source, resolved = graphs()
    analyses = tuple(
        ScenarioAnalysis(
            scenario_id=item,
            counterfactual_id="workforce-high-school",
            perspective=ReturnPerspective.CONDITIONAL_GRADUATE,
            status=AnalysisStatus.INSUFFICIENT_DATA,
            reason="synthetic fixture intentionally incomplete",
            analysis_hash=f"analysis-{index}",
        )
        for index, item in enumerate(("option-a", "option-b"))
    )
    report = ComparisonReport(
        status=AnalysisStatus.INSUFFICIENT_DATA,
        perspective=ReturnPerspective.CONDITIONAL_GRADUATE,
        quantile=0.5,
        common_counterfactual_id="workforce-high-school",
        scenario_analyses=analyses,
        pairwise_comparisons=(),
        validation_findings=("PROVISIONAL: synthetic fixture",),
        report_hash="report-hash",
    )
    fixture = EarningsFixture(profiles={})
    files = (EXAMPLES / "example-bachelors.yaml", EXAMPLES / "workforce-high-school.yaml")
    first = write_comparison_bundle(
        tmp_path / "run-a",
        scenario_files=files,
        source_graph=source,
        resolved_graph=resolved,
        earnings_fixture=fixture,
        report=report,
    )
    second = write_comparison_bundle(
        tmp_path / "run-b",
        scenario_files=files,
        source_graph=source,
        resolved_graph=resolved,
        earnings_fixture=fixture,
        report=report,
    )
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    manifest = verify_comparison_bundle(first)
    assert len(manifest["files"]) == 9
    assert (first / "results.csv").read_text(encoding="utf-8").startswith("record_type,")
    (first / "comparison.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ComparisonBundleError, match="integrity mismatch"):
        verify_comparison_bundle(first)


def test_bundle_never_overwrites_existing_run(tmp_path: Path) -> None:
    source, resolved = graphs()
    destination = tmp_path / "existing"
    destination.mkdir()
    report = ComparisonReport(
        status=AnalysisStatus.INSUFFICIENT_DATA,
        perspective=ReturnPerspective.CONDITIONAL_GRADUATE,
        quantile=0.5,
        common_counterfactual_id="workforce-high-school",
        scenario_analyses=(),
        pairwise_comparisons=(),
        validation_findings=("PROVISIONAL",),
        report_hash="hash",
    )
    with pytest.raises(ComparisonBundleError, match="already exists"):
        write_comparison_bundle(
            destination,
            scenario_files=(EXAMPLES / "workforce-high-school.yaml",),
            source_graph=source,
            resolved_graph=resolved,
            earnings_fixture=EarningsFixture(profiles={}),
            report=report,
        )
