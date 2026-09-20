import pytest

from education_roi.cashflow import LoanTerms, build_loan_schedule


def test_known_fixed_payment_amortization() -> None:
    schedule = build_loan_schedule(
        LoanTerms("federal direct", 10_000, 0.06, 10, payments_per_year=12)
    )
    assert schedule.periodic_payment == pytest.approx(111.0205, abs=0.0001)
    assert schedule.total_payments == pytest.approx(13_322.46, abs=0.02)
    assert schedule.total_interest == pytest.approx(3_322.46, abs=0.02)
    assert schedule.annual_payments[-1].ending_balance == pytest.approx(0, abs=1e-8)
    for year in schedule.annual_payments:
        assert year.payment == pytest.approx(year.principal + year.interest)


def test_zero_interest_and_zero_debt() -> None:
    zero_interest = build_loan_schedule(LoanTerms("zero interest", 12_000, 0, 2))
    assert zero_interest.periodic_payment == 500
    assert zero_interest.total_interest == pytest.approx(0, abs=1e-9)
    assert zero_interest.total_payments == pytest.approx(12_000)

    zero_debt = build_loan_schedule(LoanTerms("no debt", 0, 0.06, 10))
    assert zero_debt.periodic_payment == 0
    assert zero_debt.total_payments == 0
    assert zero_debt.total_interest == 0
    assert all(year.ending_balance == 0 for year in zero_debt.annual_payments)


def test_origination_fee_reduces_proceeds_and_is_separate_financing_cost() -> None:
    schedule = build_loan_schedule(LoanTerms("private", 10_000, 0.05, 5, origination_fee_rate=0.04))
    assert schedule.terms.origination_fee == 400
    assert schedule.terms.net_proceeds == 9_600
    assert schedule.total_financing_cost == pytest.approx(schedule.total_interest + 400)
    assert sum(schedule.financing_costs_by_year()) < schedule.total_payments


def test_unsubsidized_interest_accrues_during_enrollment_and_grace() -> None:
    unsubsidized = build_loan_schedule(
        LoanTerms(
            "unsubsidized federal",
            10_000,
            0.06,
            10,
            enrollment_years=4,
            grace_months=6,
            subsidized_during_enrollment=False,
        )
    )
    subsidized = build_loan_schedule(
        LoanTerms(
            "subsidized federal",
            10_000,
            0.06,
            10,
            enrollment_years=4,
            grace_months=6,
            subsidized_during_enrollment=True,
        )
    )
    assert unsubsidized.balance_at_repayment == pytest.approx(13_090.83, abs=0.02)
    assert subsidized.balance_at_repayment == 10_000
    assert unsubsidized.periodic_payment > subsidized.periodic_payment
    assert unsubsidized.total_interest > subsidized.total_interest


def test_annual_schedule_reconciles_balance_and_costs() -> None:
    schedule = build_loan_schedule(LoanTerms("private", 25_000, 0.08, 7))
    assert len(schedule.annual_payments) == 7
    assert sum(year.principal for year in schedule.annual_payments) == pytest.approx(
        schedule.balance_at_repayment
    )
    assert sum(schedule.financing_costs_by_year()) == pytest.approx(
        sum(year.interest for year in schedule.annual_payments)
    )
    assert schedule.terms.as_dict()["annual_interest_rate"] == 0.08


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"amount_borrowed": -1}, "amount_borrowed"),
        ({"annual_interest_rate": -0.01}, "annual_interest_rate"),
        ({"origination_fee_rate": 1}, "origination_fee_rate"),
        ({"repayment_years": 0}, "repayment_years"),
        ({"enrollment_years": -1}, "enrollment"),
        ({"grace_months": -1}, "grace"),
        ({"payments_per_year": 0}, "payments_per_year"),
    ],
)
def test_invalid_loan_terms_are_rejected(overrides: dict[str, float], error: str) -> None:
    values: dict[str, object] = {
        "name": "loan",
        "amount_borrowed": 1_000,
        "annual_interest_rate": 0.05,
        "repayment_years": 10,
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=error):
        LoanTerms(**values)  # type: ignore[arg-type]
