import pytest

from education_roi.cashflow import (
    AnnualCashFlow,
    BranchStatus,
    CompletionAssumptions,
    DollarMode,
    MoneyBasis,
    ReturnPerspective,
    ScenarioCashFlow,
    completion_return_branches,
)

REAL_2021 = MoneyBasis(DollarMode.REAL, 2021)


def year(age: int, earnings: float, cost: float = 0) -> AnnualCashFlow:
    return AnnualCashFlow(age, earnings, cost, 0, 0, 0)


def scenarios() -> tuple[ScenarioCashFlow, ScenarioCashFlow, ScenarioCashFlow]:
    graduate = ScenarioCashFlow(
        "graduate",
        REAL_2021,
        tuple(
            year(age, earnings, cost)
            for age, earnings, cost in (
                (18, 3_000, 20_000),
                (19, 3_000, 20_000),
                (20, 3_000, 20_000),
                (21, 3_000, 20_000),
                (22, 55_000, 0),
                (23, 58_000, 0),
            )
        ),
    )
    noncompleter = ScenarioCashFlow(
        "non-completer",
        REAL_2021,
        tuple(
            year(age, earnings, cost)
            for age, earnings, cost in (
                (18, 3_000, 20_000),
                (19, 3_000, 20_000),
                (20, 28_000, 0),
                (21, 30_000, 0),
                (22, 32_000, 0),
                (23, 34_000, 0),
            )
        ),
    )
    counterfactual = ScenarioCashFlow(
        "workforce",
        REAL_2021,
        tuple(
            year(age, earnings)
            for age, earnings in zip(range(18, 24), range(25_000, 31_000, 1_000), strict=True)
        ),
    )
    return graduate, noncompleter, counterfactual


def test_conditional_and_enrollment_returns_remain_distinct() -> None:
    graduate, noncompleter, counterfactual = scenarios()
    result = completion_return_branches(
        graduate,
        counterfactual,
        CompletionAssumptions(0.6, graduation_age=22, noncompletion_exit_age=20),
        noncompleter,
    )
    assert result.conditional_graduate.perspective is ReturnPerspective.CONDITIONAL_GRADUATE
    assert result.enrollment.perspective is ReturnPerspective.ENROLLMENT
    assert result.conditional_graduate.status is BranchStatus.AVAILABLE
    assert result.enrollment.status is BranchStatus.AVAILABLE
    assert result.conditional_graduate.cash_flow is not None
    assert result.enrollment.cash_flow is not None
    graduate_amounts = [point.amount for point in result.conditional_graduate.cash_flow.points]
    enrollment_amounts = [point.amount for point in result.enrollment.cash_flow.points]
    assert graduate_amounts[2] == -44_000
    assert enrollment_amounts[2] == pytest.approx(0.6 * -44_000 + 0.4 * 1_000)
    assert graduate_amounts != enrollment_amounts


def test_dropout_costs_and_assumptions_are_explicit() -> None:
    graduate, noncompleter, counterfactual = scenarios()
    assert [item.direct_education_cost for item in noncompleter.annual] == [
        20_000,
        20_000,
        0,
        0,
        0,
        0,
    ]
    result = completion_return_branches(
        graduate,
        counterfactual,
        CompletionAssumptions(0.5, graduation_age=22, noncompletion_exit_age=20),
        noncompleter,
    )
    assert result.enrollment.assumptions == {
        "completion_probability": 0.5,
        "graduation_age": 22,
        "noncompletion_exit_age": 20,
    }


def test_missing_probability_is_explicitly_insufficient() -> None:
    graduate, noncompleter, counterfactual = scenarios()
    result = completion_return_branches(
        graduate,
        counterfactual,
        CompletionAssumptions(None, graduation_age=22, noncompletion_exit_age=20),
        noncompleter,
    )
    assert result.conditional_graduate.status is BranchStatus.AVAILABLE
    assert result.enrollment.status is BranchStatus.INSUFFICIENT_DATA
    assert result.enrollment.cash_flow is None
    assert result.enrollment.reason == "completion probability is required for enrollment return"


def test_missing_noncompletion_evidence_is_not_replaced_with_graduate_return() -> None:
    graduate, _, counterfactual = scenarios()
    result = completion_return_branches(
        graduate,
        counterfactual,
        CompletionAssumptions(0.75, graduation_age=22, noncompletion_exit_age=20),
    )
    assert result.enrollment.status is BranchStatus.INSUFFICIENT_DATA
    assert result.enrollment.reason is not None
    assert "non-completer cash flow" in result.enrollment.reason
    assert result.enrollment.cash_flow is None


def test_missing_dropout_timing_is_explicitly_insufficient() -> None:
    graduate, noncompleter, counterfactual = scenarios()
    result = completion_return_branches(
        graduate,
        counterfactual,
        CompletionAssumptions(0.75, graduation_age=22, noncompletion_exit_age=None),
        noncompleter,
    )
    assert result.enrollment.status is BranchStatus.INSUFFICIENT_DATA
    assert result.enrollment.reason is not None
    assert "exit age" in result.enrollment.reason


def test_certain_completion_needs_no_noncompleter_branch() -> None:
    graduate, _, counterfactual = scenarios()
    result = completion_return_branches(
        graduate,
        counterfactual,
        CompletionAssumptions(1, graduation_age=22, noncompletion_exit_age=None),
    )
    assert result.enrollment.status is BranchStatus.AVAILABLE
    assert result.enrollment.cash_flow is not None
    assert result.conditional_graduate.cash_flow is not None
    assert result.enrollment.cash_flow.points == result.conditional_graduate.cash_flow.points


def test_invalid_probability_or_timing_is_rejected() -> None:
    with pytest.raises(ValueError, match="completion_probability"):
        CompletionAssumptions(1.1, graduation_age=22, noncompletion_exit_age=20)
    graduate, noncompleter, counterfactual = scenarios()
    with pytest.raises(ValueError, match="graduation_age"):
        completion_return_branches(
            graduate,
            counterfactual,
            CompletionAssumptions(0.5, graduation_age=30, noncompletion_exit_age=20),
            noncompleter,
        )
