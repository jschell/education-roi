from math import exp, log

import pytest

from education_roi.cashflow import DollarMode, EducationCostInput, FinancialResultStatus, MoneyBasis
from education_roi.reproduction import (
    AggregateReproductionResult,
    CovariateSlopeSpecification,
    EarningsCoefficients,
    ReproductionStatus,
    ReproductionTarget,
    build_age_earnings_profile,
    published_zhang_configuration,
    reproduce_aggregate_target,
)

REAL_2021 = MoneyBasis(DollarMode.REAL, 2021)


def coefficients(group: str, base: float, age: float, age_squared: float) -> EarningsCoefficients:
    return EarningsCoefficients(
        group,
        log(base),
        age,
        age_squared,
        CovariateSlopeSpecification.GROUP_SPECIFIC,
        {"female": 0.5, "married": 0.4, "region_northeast": 0.2},
        "fixed regression fixture",
    )


def costs() -> tuple[EducationCostInput, ...]:
    return tuple(
        EducationCostInput(age, 8_000, 1_000, 1_000, 4_000, 12_000, 10_000, 3_000, 3_268)
        for age in range(18, 22)
    )


def test_fixed_age_profile_matches_equation_four_and_retains_metadata() -> None:
    values = coefficients("bachelors", 10_000, 0.05, -0.0005)
    profile = build_age_earnings_profile(values)
    assert len(profile.points) == 48
    assert profile.points[0].age == 18
    assert profile.points[-1].age == 65
    assert profile.earnings_at(30) == pytest.approx(exp(log(10_000) + 0.05 * 30 - 0.0005 * 30**2))
    assert profile.coefficients.standardized_covariates["female"] == 0.5
    assert len(profile.coefficient_hash) == 64


def test_profile_hash_and_predictions_are_deterministic() -> None:
    values = coefficients("high_school", 9_000, 0.04, -0.0004)
    first = build_age_earnings_profile(values)
    second = build_age_earnings_profile(values)
    assert first == second
    with pytest.raises(ValueError, match="outside"):
        first.earnings_at(17)


def test_aggregate_profiles_flow_through_financial_engine() -> None:
    configuration = published_zhang_configuration()
    bachelors = build_age_earnings_profile(coefficients("bachelors", 18_000, 0.055, -0.00045))
    high_school = build_age_earnings_profile(coefficients("high_school", 14_000, 0.042, -0.0004))
    target = ReproductionTarget("fixture-irr", "fixed profile fixture", 0.10, 1.0)
    result = reproduce_aggregate_target(
        bachelor_profile=bachelors,
        high_school_profile=high_school,
        education_costs=costs(),
        basis=REAL_2021,
        configuration=configuration,
        target=target,
        dataset_hashes=("fixture-acs", "fixture-costs"),
        model_version="test",
    )
    assert result.financial_result.status is FinancialResultStatus.AVAILABLE
    assert result.financial_result.metrics is not None
    assert result.option_scenario.annual[0].earnings == 3_268
    assert result.option_scenario.annual[4].age == 22
    expected_foregone = high_school.earnings_at(18) * 1.15
    assert result.counterfactual_scenario.annual[0].earnings == pytest.approx(expected_foregone)
    assert result.comparison.status in {
        ReproductionStatus.PASS,
        ReproductionStatus.FAIL,
        ReproductionStatus.REVIEW,
    }
    assert result.comparison.ambiguity_notes


def test_aggregate_integration_is_deterministic_and_rejects_wrong_cost_years() -> None:
    configuration = published_zhang_configuration()
    bachelors = build_age_earnings_profile(coefficients("bachelors", 18_000, 0.055, -0.00045))
    high_school = build_age_earnings_profile(coefficients("high_school", 14_000, 0.042, -0.0004))
    target = ReproductionTarget("fixture-irr", "fixture", 0.10, 1.0)

    def reproduce(
        education_costs: tuple[EducationCostInput, ...],
    ) -> AggregateReproductionResult:
        return reproduce_aggregate_target(
            bachelor_profile=bachelors,
            high_school_profile=high_school,
            education_costs=education_costs,
            basis=REAL_2021,
            configuration=configuration,
            target=target,
            dataset_hashes=("fixture-acs", "fixture-costs"),
            model_version="test",
        )

    first = reproduce(costs())
    second = reproduce(costs())
    assert first.financial_result.configuration_hash == second.financial_result.configuration_hash
    with pytest.raises(ValueError, match="college ages"):
        reproduce(costs()[:3])
