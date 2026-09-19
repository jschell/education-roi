import pytest

from education_roi.cashflow import (
    AnnualCashFlow,
    BreakEvenStatus,
    CashFlowPoint,
    CashFlowSeries,
    DollarMode,
    IRRStatus,
    MoneyBasis,
    ScenarioCashFlow,
    break_even_age,
    incremental_cash_flow,
    internal_rate_of_return,
    lifetime_net_value,
    net_present_value,
)

REAL_2021 = MoneyBasis(DollarMode.REAL, 2021)


def series(*amounts: float, start_age: int = 18) -> CashFlowSeries:
    return CashFlowSeries(
        "test",
        REAL_2021,
        tuple(CashFlowPoint(start_age + index, amount) for index, amount in enumerate(amounts)),
    )


def annual(age: int, earnings: float, **overrides: float) -> AnnualCashFlow:
    return AnnualCashFlow(
        age=age,
        earnings=earnings,
        direct_education_cost=overrides.get("direct_education_cost", 0),
        incremental_living_cost=overrides.get("incremental_living_cost", 0),
        grant_aid=overrides.get("grant_aid", 0),
        financing_cost=overrides.get("financing_cost", 0),
    )


def test_scenario_components_and_counterfactual_create_opportunity_cost() -> None:
    college = ScenarioCashFlow(
        "college",
        REAL_2021,
        (
            annual(
                18,
                3,
                direct_education_cost=20,
                incremental_living_cost=4,
                grant_aid=5,
                financing_cost=1,
            ),
            annual(19, 40),
        ),
    )
    workforce = ScenarioCashFlow("workforce", REAL_2021, (annual(18, 30), annual(19, 35)))
    incremental = incremental_cash_flow(college, workforce)
    assert college.net_series().points[0].amount == -17
    assert [point.amount for point in incremental.points] == [-47, 5]
    assert college.lifetime_earnings == 43


def test_counterfactual_rejects_basis_or_age_mismatch() -> None:
    real = ScenarioCashFlow("real", REAL_2021, (annual(18, 1),))
    nominal = ScenarioCashFlow("nominal", MoneyBasis(DollarMode.NOMINAL), (annual(18, 1),))
    wrong_age = ScenarioCashFlow("wrong-age", REAL_2021, (annual(19, 1),))
    with pytest.raises(ValueError, match="money basis"):
        incremental_cash_flow(real, nominal)
    with pytest.raises(ValueError, match="identical ages"):
        incremental_cash_flow(real, wrong_age)


def test_npv_and_unique_irr_match_known_example() -> None:
    cash_flows = series(-100, 110)
    assert net_present_value(cash_flows, 0.10) == pytest.approx(0)
    result = internal_rate_of_return(cash_flows)
    assert result.status is IRRStatus.UNIQUE
    assert result.roots == pytest.approx((0.10,), abs=1e-9)


def test_irr_reports_multiple_no_root_and_indeterminate_cases() -> None:
    multiple = internal_rate_of_return(series(-100, 230, -132))
    assert multiple.status is IRRStatus.MULTIPLE
    assert multiple.roots == pytest.approx((0.10, 0.20), abs=1e-8)
    assert internal_rate_of_return(series(1, 2)).status is IRRStatus.NO_ROOT
    assert internal_rate_of_return(series(0, 0)).status is IRRStatus.INDETERMINATE


def test_break_even_and_lifetime_net_value() -> None:
    achieved = break_even_age(series(-100, 40, 60, 20))
    assert achieved.status is BreakEvenStatus.ACHIEVED
    assert achieved.age == 20
    assert achieved.cumulative_value == 0
    never = break_even_age(series(-100, 20, 30))
    assert never.status is BreakEvenStatus.NEVER
    assert never.age is None
    assert never.cumulative_value == -50
    assert lifetime_net_value(series(-100, 40, 60, 20)) == 20


def test_models_reject_implicit_or_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="dollar_year"):
        MoneyBasis(DollarMode.REAL)
    with pytest.raises(ValueError, match="cannot declare"):
        MoneyBasis(DollarMode.NOMINAL, 2021)
    with pytest.raises(ValueError, match="consecutive"):
        CashFlowSeries("gap", REAL_2021, (CashFlowPoint(18, 1), CashFlowPoint(20, 2)))
    with pytest.raises(ValueError, match="cannot be negative"):
        annual(18, 1, direct_education_cost=-1)
    with pytest.raises(ValueError, match="greater than -1"):
        net_present_value(series(-1, 2), -1)
