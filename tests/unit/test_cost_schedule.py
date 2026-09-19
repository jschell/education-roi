import pytest

from education_roi.cashflow import (
    CostAssumptions,
    CPIConversion,
    DollarMode,
    EducationCostInput,
    MoneyBasis,
    build_education_cost_schedule,
    selection_adjusted_earnings,
    selection_adjusted_foregone_earnings,
)

REAL_2012 = MoneyBasis(DollarMode.REAL, 2012)
REAL_2021 = MoneyBasis(DollarMode.REAL, 2021)
PREFERRED = CostAssumptions(nontuition_attribution=0.5, selection_adjustment=0.25)


def cost_year(age: int, **overrides: float) -> EducationCostInput:
    values = {
        "tuition": 10_000.0,
        "fees": 1_000.0,
        "books": 1_000.0,
        "other_nontuition": 4_000.0,
        "living_cost": 12_000.0,
        "counterfactual_living_cost": 10_000.0,
        "grant_aid": 3_000.0,
        "student_earnings": 3_268.0,
        "loan_proceeds": 0.0,
    }
    values.update(overrides)
    return EducationCostInput(age=age, **values)


def test_cpi_identity_known_conversion_and_machine_readable_record() -> None:
    identity = CPIConversion("CPI-U annual average", 2021, 2021, 270.970, 270.970)
    assert identity.factor == 1
    assert identity.convert(100, REAL_2021) == 100

    conversion = CPIConversion("CPI-U annual average", 2012, 2021, 229.594, 270.970)
    assert conversion.convert(2_740, REAL_2012) == pytest.approx(3_233.79, abs=0.01)
    assert conversion.as_assumption() == {
        "name": "cpi_conversion",
        "series": "CPI-U annual average",
        "source_year": 2012,
        "target_year": 2021,
        "source_index": 229.594,
        "target_index": 270.970,
        "factor": conversion.factor,
    }


def test_cpi_rejects_real_nominal_and_dollar_year_mismatches() -> None:
    conversion = CPIConversion("CPI-U", 2012, 2021, 230, 271)
    with pytest.raises(ValueError, match="nominal"):
        conversion.convert(100, MoneyBasis(DollarMode.NOMINAL))
    with pytest.raises(ValueError, match="dollar year"):
        conversion.convert(100, REAL_2021)


def test_four_year_zhang_style_cost_construction_and_assumptions() -> None:
    result = build_education_cost_schedule(
        "college",
        REAL_2021,
        tuple(cost_year(age) for age in range(18, 22)),
        PREFERRED,
    )
    first = result.scenario.annual[0]
    assert first.direct_education_cost == 14_000
    assert first.incremental_living_cost == 2_000
    assert first.grant_aid == 3_000
    assert first.earnings == 3_268
    assert first.net_amount == -9_732
    assert result.assumptions == {
        "nontuition_attribution": 0.5,
        "selection_adjustment": 0.25,
        "enrollment_years": 4,
        "enrollment_ages": [18, 19, 20, 21],
        "loans_treated_as_aid": False,
    }


@pytest.mark.parametrize("enrollment_years", [4, 5, 6])
def test_enrollment_length_delays_graduate_earnings(enrollment_years: int) -> None:
    result = build_education_cost_schedule(
        "college",
        REAL_2021,
        tuple(cost_year(18 + offset) for offset in range(enrollment_years)),
        PREFERRED,
        graduate_earnings=(50_000, 55_000),
    )
    assert result.scenario.annual[enrollment_years].age == 18 + enrollment_years
    assert result.scenario.annual[enrollment_years].earnings == 50_000
    assert result.assumptions["enrollment_years"] == enrollment_years


def test_grants_reduce_cost_loans_do_not_and_living_cost_is_incremental() -> None:
    no_loan = build_education_cost_schedule(
        "college", REAL_2021, (cost_year(18, grant_aid=5_000),), PREFERRED
    )
    with_loan = build_education_cost_schedule(
        "college",
        REAL_2021,
        (cost_year(18, grant_aid=5_000, loan_proceeds=20_000),),
        PREFERRED,
    )
    assert no_loan.scenario.annual[0].net_amount == with_loan.scenario.annual[0].net_amount
    assert with_loan.scenario.annual[0].grant_aid == 5_000
    assert with_loan.scenario.annual[0].incremental_living_cost == 2_000


@pytest.mark.parametrize("attribution,expected", [(0, 12_000), (0.5, 14_000), (1, 16_000)])
def test_nontuition_attribution_cases(attribution: float, expected: float) -> None:
    assumptions = CostAssumptions(attribution, 0.25)
    result = build_education_cost_schedule("college", REAL_2021, (cost_year(18),), assumptions)
    assert result.scenario.annual[0].direct_education_cost == expected


@pytest.mark.parametrize("adjustment,expected", [(0, 20_000), (0.25, 23_750), (0.5, 27_500)])
def test_selection_adjustment_applies_to_earnings_gap(adjustment: float, expected: float) -> None:
    assert selection_adjusted_earnings(35_000, 20_000, adjustment) == expected


def test_preferred_selection_adjustment_changes_foregone_earnings_not_irr() -> None:
    adjusted = selection_adjusted_foregone_earnings(20_000, 0.60, 0.25)
    assert adjusted == 23_000


def test_custom_schedule_and_invalid_inputs() -> None:
    result = build_education_cost_schedule(
        "custom",
        REAL_2021,
        tuple(cost_year(age) for age in range(25, 28)),
        CostAssumptions(1, 0),
    )
    assert [year.age for year in result.scenario.annual] == [25, 26, 27]
    with pytest.raises(ValueError, match="consecutive"):
        build_education_cost_schedule("gap", REAL_2021, (cost_year(18), cost_year(20)), PREFERRED)
