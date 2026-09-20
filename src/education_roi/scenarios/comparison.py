"""Comparable multi-scenario and pairwise financial reports."""

from hashlib import sha256
from itertools import combinations
from json import dumps

from education_roi.cashflow import (
    BranchResult,
    BranchStatus,
    CashFlowPoint,
    CashFlowSeries,
    ComputationProvenance,
    DollarMode,
    MoneyBasis,
    ReturnPerspective,
    calculate_financial_result,
)
from education_roi.scenarios.analysis import (
    AnalysisStatus,
    EarningsFixture,
    ScenarioAnalysis,
    analyze_scenario,
)
from education_roi.scenarios.models import ResolvedScenarioGraph, StrictModel
from education_roi.scenarios.resolution import ResolvedConfigurationGraph


class ScenarioComparisonError(ValueError):
    pass


class PairwiseComparison(StrictModel):
    option_id: str
    counterfactual_id: str
    status: AnalysisStatus
    result: dict[str, object] | None
    comparison_hash: str


class ComparisonReport(StrictModel):
    schema_version: str = "1.0"
    status: AnalysisStatus
    perspective: ReturnPerspective
    quantile: float
    common_counterfactual_id: str
    scenario_analyses: tuple[ScenarioAnalysis, ...]
    pairwise_comparisons: tuple[PairwiseComparison, ...]
    validation_findings: tuple[str, ...]
    provisional: bool = True
    report_hash: str

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def _money_basis(mode: str, dollar_year: int | None) -> MoneyBasis:
    return MoneyBasis(DollarMode(mode), dollar_year)


def _pairwise(
    option: ScenarioAnalysis,
    counterfactual: ScenarioAnalysis,
    perspective: ReturnPerspective,
    discount_rate: float,
    basis: MoneyBasis,
) -> PairwiseComparison:
    identity = {"option_id": option.scenario_id, "counterfactual_id": counterfactual.scenario_id}
    if (
        option.status is AnalysisStatus.INSUFFICIENT_DATA
        or counterfactual.status is AnalysisStatus.INSUFFICIENT_DATA
    ):
        payload = {**identity, "status": AnalysisStatus.INSUFFICIENT_DATA.value, "result": None}
    else:
        option_points = option.annual_cash_flow
        baseline_points = counterfactual.annual_cash_flow
        points = tuple(
            CashFlowPoint(int(left["age"]), float(left["net_amount"]) - float(right["net_amount"]))
            for left, right in zip(option_points, baseline_points, strict=True)
        )
        series = CashFlowSeries(
            f"{option.scenario_id} vs {counterfactual.scenario_id}", basis, points
        )
        artifact_ids = tuple(
            sorted(
                {
                    str(identifier)
                    for analysis in (option, counterfactual)
                    if analysis.result is not None
                    for identifier in analysis.result["provenance"]["dataset_artifact_ids"]  # type: ignore[index,union-attr]
                }
            )
        )
        provenance = ComputationProvenance(
            model_name="scenario-pairwise-comparison",
            model_version="0.1.0",
            dataset_artifact_ids=artifact_ids,
            assumptions={
                "option_analysis_hash": option.analysis_hash,
                "counterfactual_analysis_hash": counterfactual.analysis_hash,
                "discount_rate": discount_rate,
            },
        )
        branch = BranchResult(
            perspective, BranchStatus.AVAILABLE, series, None, provenance.assumptions
        )
        option_earnings = sum(float(item["earnings"]) for item in option_points)
        result = calculate_financial_result(
            branch,
            discount_rate=discount_rate,
            lifetime_earnings=option_earnings,
            provenance=provenance,
        )
        payload = {**identity, "status": AnalysisStatus.AVAILABLE.value, "result": result.as_dict()}
    digest = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return PairwiseComparison(**payload, comparison_hash=digest)


def compare_scenarios(
    source_graph: ResolvedScenarioGraph,
    resolved_graph: ResolvedConfigurationGraph,
    fixture: EarningsFixture,
    scenario_ids: tuple[str, ...],
    perspective: ReturnPerspective,
) -> ComparisonReport:
    if len(scenario_ids) < 2:
        raise ScenarioComparisonError("comparison requires at least two scenario IDs")
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ScenarioComparisonError("scenario IDs must be unique")
    definitions = {item.id: item for item in source_graph.scenarios}
    try:
        scenarios = tuple(definitions[item] for item in scenario_ids)
    except KeyError as error:
        raise ScenarioComparisonError(f"unknown scenario {error.args[0]}") from error
    counterfactuals = {item.counterfactual for item in scenarios}
    if None in counterfactuals or len(counterfactuals) != 1:
        raise ScenarioComparisonError(
            "compared scenarios require one common explicit counterfactual"
        )
    counterfactual_id = next(iter(counterfactuals))
    assert counterfactual_id is not None
    bases = {item.assumptions.money_basis for item in scenarios}
    horizons = {(item.assumptions.start_age, item.assumptions.terminal_age) for item in scenarios}
    if len(bases) != 1 or len(horizons) != 1:
        raise ScenarioComparisonError(
            "compared scenarios require identical money bases and horizons"
        )
    relevant_ids = {*scenario_ids, counterfactual_id}
    quantiles = {
        profile.quantile
        for item in relevant_ids
        for profile in fixture.profiles.get(item, {}).values()
    }
    if len(quantiles) != 1:
        raise ScenarioComparisonError("comparison requires one aligned earnings quantile")
    quantile = next(iter(quantiles))
    analyses = tuple(
        analyze_scenario(source_graph, resolved_graph, fixture, item, perspective)
        for item in scenario_ids
    )
    basis_config = scenarios[0].assumptions.money_basis
    basis = _money_basis(basis_config.mode, basis_config.dollar_year)
    pairwise = tuple(
        _pairwise(
            left,
            right,
            perspective,
            definitions[left.scenario_id].assumptions.real_discount_rate,
            basis,
        )
        for left, right in combinations(analyses, 2)
    )
    status = (
        AnalysisStatus.INSUFFICIENT_DATA
        if any(item.status is AnalysisStatus.INSUFFICIENT_DATA for item in analyses)
        else AnalysisStatus.AVAILABLE
    )
    findings = (
        "PROVISIONAL: fixture-backed analysis is not decision-grade evidence",
        f"earnings quantile aligned at {quantile}",
        "money basis and modeled horizon match",
    )
    payload = {
        "schema_version": "1.0",
        "status": status.value,
        "perspective": perspective.value,
        "quantile": quantile,
        "common_counterfactual_id": counterfactual_id,
        "scenario_analyses": [item.as_dict() for item in analyses],
        "pairwise_comparisons": [item.model_dump(mode="json") for item in pairwise],
        "validation_findings": list(findings),
        "provisional": True,
    }
    report_hash = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return ComparisonReport(
        status=status,
        perspective=perspective,
        quantile=quantile,
        common_counterfactual_id=counterfactual_id,
        scenario_analyses=analyses,
        pairwise_comparisons=pairwise,
        validation_findings=findings,
        report_hash=report_hash,
    )
