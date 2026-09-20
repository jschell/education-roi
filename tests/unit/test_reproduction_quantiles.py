from math import exp

import pytest

from education_roi.cashflow import CashFlowPoint, CashFlowSeries, DollarMode, MoneyBasis
from education_roi.reproduction.quantiles import (
    DECILES,
    QuantileCashFlow,
    QuantileDefinition,
    QuantileEarningsCoefficients,
    QuantileSolverMetadata,
    SolverStatus,
    build_quantile_earnings_profile,
    calculate_quantile_irrs,
    validate_profile_against_reference,
)
from education_roi.reproduction.reporting import provisional_reproduction_report


def solver(status: SolverStatus = SolverStatus.CONVERGED) -> QuantileSolverMetadata:
    return QuantileSolverMetadata(
        "interior-point",
        "independent-fixture-solver",
        "1.0",
        status,
        14,
        1e-9,
        123.5 if status is SolverStatus.CONVERGED else None,
        "fixture convergence record",
    )


def cash_flow(quantile: float, final_value: float) -> QuantileCashFlow:
    series = CashFlowSeries(
        f"P{round(quantile * 100)} fixture",
        MoneyBasis(DollarMode.REAL, 2021),
        (CashFlowPoint(18, -100), CashFlowPoint(19, final_value)),
    )
    return QuantileCashFlow(QuantileDefinition(quantile), series, "option-hash", "hs-hash")


def test_decile_definitions_label_rank_invariance_and_median() -> None:
    assert len(DECILES) == 9
    assert QuantileDefinition(0.10).label == "P10"
    median = QuantileDefinition(0.50).as_dict()
    assert median["is_median"] is True
    assert median["rank_invariance_assumption"] is True
    assert "not an individual probability" in str(median["interpretation"])
    with pytest.raises(ValueError, match="nine earnings deciles"):
        QuantileDefinition(0.25)


def test_profile_matches_hard_coded_independent_fixture() -> None:
    coefficients = QuantileEarningsCoefficients(
        "bachelors",
        QuantileDefinition(0.50),
        9.0,
        0.04,
        -0.0004,
        "synthetic coefficients; not paper values",
    )
    fit = build_quantile_earnings_profile(coefficients, solver(), minimum_age=18, maximum_age=20)
    assert fit.profile is not None
    # Values were generated independently and frozen; the implementation under test does not
    # participate in constructing this reference mapping.
    reference = {
        18: 14_623.717851741809,
        19: 14_996.918115378601,
        20: 15_367.343732049992,
    }
    validation = validate_profile_against_reference(
        fit.profile,
        reference,
        reference_implementation="frozen external math fixture v1",
        absolute_tolerance=1e-9,
        relative_tolerance=1e-12,
    )
    assert validation.passed
    assert validation.as_dict()["definition"] == QuantileDefinition(0.50).as_dict()
    assert validation.as_dict()["coefficient_hash"] == coefficients.coefficient_hash
    assert fit.profile.earnings_at(19) == pytest.approx(reference[19])


def test_failed_solver_produces_no_profile() -> None:
    coefficients = QuantileEarningsCoefficients(
        "high-school", QuantileDefinition(0.10), 9, 0.04, -0.0004, "fixture"
    )
    fit = build_quantile_earnings_profile(coefficients, solver(SolverStatus.FAILED))
    assert fit.profile is None
    solver_payload = fit.as_dict()["solver"]
    assert isinstance(solver_payload, dict)
    assert solver_payload["status"] == "FAILED"


def test_median_and_nonmedian_irr_are_calculated_and_sorted() -> None:
    results = calculate_quantile_irrs([cash_flow(0.50, 120), cash_flow(0.10, 110)])
    assert [result.definition.label for result in results] == ["P10", "P50"]
    assert results[0].internal_rate_of_return.roots == pytest.approx((0.10,), abs=1e-9)
    assert results[1].internal_rate_of_return.roots == pytest.approx((0.20,), abs=1e-9)
    assert results[0].definition.is_median is False
    assert results[1].definition.is_median is True
    assert results[0].cash_flow_hash != results[1].cash_flow_hash
    assert results[0].as_dict()["cash_flow"] == {
        "name": "P10 fixture",
        "basis": {"mode": "real", "dollar_year": 2021},
        "points": [{"age": 18, "amount": -100}, {"age": 19, "amount": 110}],
    }


def test_reports_are_deterministic_and_keep_provisional_blockers_visible() -> None:
    coefficients = QuantileEarningsCoefficients(
        "bachelors", QuantileDefinition(0.50), 9, 0.04, -0.0004, "fixture only"
    )
    fit = build_quantile_earnings_profile(coefficients, solver(), minimum_age=18, maximum_age=18)
    assert fit.profile is not None
    validation = validate_profile_against_reference(
        fit.profile,
        {18: exp(9 + 0.04 * 18 - 0.0004 * 18**2)},
        reference_implementation="independent fixture",
        absolute_tolerance=0,
        relative_tolerance=0,
    )
    irrs = calculate_quantile_irrs([cash_flow(0.50, 120)])
    arguments = {
        "configuration_hash": "config-hash",
        "dataset_hashes": ("fixture-data-hash",),
        "sample_flow": ({"step": "input", "unweighted_n": 10, "weighted_n": 100.0},),
        "profiles": (fit,),
        "profile_validations": (validation,),
        "cash_flows": irrs,
        "comparisons": (
            {
                "target_id": "table-3-men",
                "status": "REVIEW",
                "published_value": 0.0906,
                "reproduced_value": None,
                "absolute_difference": None,
            },
        ),
        "blockers": (
            "authoritative ACS inputs and exact coefficients unavailable",
            "restricted cost cells unavailable",
            "Table A1 crosswalk unavailable",
        ),
        "ambiguity_notes": ("covariate slope interpretation unresolved",),
    }
    first = provisional_reproduction_report(**arguments)  # type: ignore[arg-type]
    second = provisional_reproduction_report(**arguments)  # type: ignore[arg-type]
    assert first.to_json() == second.to_json()
    assert first.to_markdown() == second.to_markdown()
    assert '"certification_status":"PROVISIONAL"' in first.to_json()
    assert "## Discrepancies" in first.to_markdown()
    assert "Table A1 crosswalk unavailable" in first.to_markdown()
