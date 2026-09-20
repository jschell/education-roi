"""Aggregate Zhang profile integration with the deterministic financial engine."""

from dataclasses import dataclass

from education_roi.acs.crosswalk import CrosswalkStatus
from education_roi.cashflow import (
    AnnualCashFlow,
    BranchResult,
    BranchStatus,
    ComputationProvenance,
    CostAssumptions,
    EducationCostInput,
    FinancialResult,
    FinancialResultStatus,
    IRRStatus,
    MoneyBasis,
    ReturnPerspective,
    ScenarioCashFlow,
    build_education_cost_schedule,
    calculate_financial_result,
    incremental_cash_flow,
    selection_adjusted_earnings,
    selection_adjusted_foregone_earnings,
)
from education_roi.reproduction.comparison import (
    ReproductionComparison,
    ReproductionTarget,
    compare_target,
)
from education_roi.reproduction.config import ZhangConfiguration
from education_roi.reproduction.profiles import EarningsProfile


@dataclass(frozen=True)
class AggregateReproductionResult:
    financial_result: FinancialResult
    comparison: ReproductionComparison
    option_scenario: ScenarioCashFlow
    counterfactual_scenario: ScenarioCashFlow


def reproduce_aggregate_target(
    *,
    bachelor_profile: EarningsProfile,
    high_school_profile: EarningsProfile,
    education_costs: tuple[EducationCostInput, ...],
    basis: MoneyBasis,
    configuration: ZhangConfiguration,
    target: ReproductionTarget,
    dataset_hashes: tuple[str, ...],
    model_version: str,
) -> AggregateReproductionResult:
    """Construct four-year costs, selection-adjusted earnings, metrics, and target comparison."""
    if tuple(item.age for item in education_costs) != configuration.college_ages:
        raise ValueError("education costs must cover the configured college ages exactly")
    graduate_ages = tuple(range(configuration.college_ages[-1] + 1, configuration.maximum_age + 1))
    option = build_education_cost_schedule(
        bachelor_profile.group,
        basis,
        education_costs,
        CostAssumptions(configuration.nontuition_attribution, configuration.selection_adjustment),
        tuple(bachelor_profile.earnings_at(age) for age in graduate_ages),
    ).scenario
    counterfactual_annual = []
    for age in range(configuration.minimum_age, configuration.maximum_age + 1):
        high_school = high_school_profile.earnings_at(age)
        if age in configuration.college_ages:
            earnings = selection_adjusted_foregone_earnings(
                high_school,
                configuration.selection_earnings_premium,
                configuration.selection_adjustment,
            )
        else:
            earnings = selection_adjusted_earnings(
                bachelor_profile.earnings_at(age), high_school, configuration.selection_adjustment
            )
        counterfactual_annual.append(AnnualCashFlow(age, earnings, 0, 0, 0, 0))
    counterfactual = ScenarioCashFlow(
        "selection-adjusted high school", basis, tuple(counterfactual_annual)
    )
    incremental = incremental_cash_flow(option, counterfactual)
    branch = BranchResult(
        ReturnPerspective.CONDITIONAL_GRADUATE,
        BranchStatus.AVAILABLE,
        incremental,
        None,
        configuration.as_dict(),
    )
    provenance = ComputationProvenance(
        "zhang-aggregate-reproduction",
        model_version,
        dataset_hashes,
        {
            **configuration.as_dict(),
            "bachelor_coefficient_hash": bachelor_profile.coefficient_hash,
            "high_school_coefficient_hash": high_school_profile.coefficient_hash,
        },
    )
    financial = calculate_financial_result(
        branch,
        discount_rate=configuration.discount_rate,
        lifetime_earnings=option.lifetime_earnings,
        provenance=provenance,
    )
    reproduced_value = None
    if (
        financial.status is FinancialResultStatus.AVAILABLE
        and financial.metrics is not None
        and financial.metrics.internal_rate_of_return.status is IRRStatus.UNIQUE
    ):
        reproduced_value = financial.metrics.internal_rate_of_return.roots[0]
    comparison = compare_target(
        target,
        reproduced_value,
        configuration_hash=financial.configuration_hash,
        dataset_hashes=dataset_hashes,
        crosswalk_status=CrosswalkStatus.PROVISIONAL,
        ambiguity_notes=(
            "aggregate fixture; source coefficients and restricted cost cells pending",
        ),
    )
    return AggregateReproductionResult(financial, comparison, option, counterfactual)
