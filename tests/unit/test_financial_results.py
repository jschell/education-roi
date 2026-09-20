import json

import pytest

from education_roi.cashflow import (
    BranchResult,
    BranchStatus,
    BreakEvenStatus,
    CashFlowPoint,
    CashFlowSeries,
    ComputationProvenance,
    DollarMode,
    FinancialResultStatus,
    IRRStatus,
    MoneyBasis,
    ReturnPerspective,
    calculate_financial_result,
)

REAL_2021 = MoneyBasis(DollarMode.REAL, 2021)


def provenance(**assumptions: object) -> ComputationProvenance:
    return ComputationProvenance(
        "education-roi-financial-engine",
        "0.1.0",
        ("acs-pums:2021:abc123", "bls-cpi:2021:def456"),
        {"selection_adjustment": 0.25, **assumptions},
        ("cpi-2012-to-2021",),
    )


def available_branch(*amounts: float) -> BranchResult:
    return BranchResult(
        ReturnPerspective.CONDITIONAL_GRADUATE,
        BranchStatus.AVAILABLE,
        CashFlowSeries(
            "college vs workforce",
            REAL_2021,
            tuple(CashFlowPoint(18 + offset, amount) for offset, amount in enumerate(amounts)),
        ),
        None,
        {"completion_probability": 1.0},
    )


def test_complete_result_matches_independent_reference_metrics() -> None:
    result = calculate_financial_result(
        available_branch(-100, 110),
        discount_rate=0.10,
        lifetime_earnings=110,
        provenance=provenance(discount_rate=0.10),
    )
    assert result.status is FinancialResultStatus.AVAILABLE
    assert result.metrics is not None
    assert result.metrics.net_present_value == pytest.approx(0)
    assert result.metrics.internal_rate_of_return.status is IRRStatus.UNIQUE
    assert result.metrics.internal_rate_of_return.roots == pytest.approx((0.10,), abs=1e-9)
    assert result.metrics.lifetime_net_value == 10
    assert result.metrics.lifetime_earnings == 110
    assert result.metrics.break_even.status is BreakEvenStatus.ACHIEVED
    assert result.metrics.break_even.age == 19
    assert len(result.configuration_hash) == 64


def test_configuration_hash_is_deterministic_and_input_sensitive() -> None:
    branch = available_branch(-100, 110)
    first = calculate_financial_result(
        branch, discount_rate=0.04, lifetime_earnings=110, provenance=provenance()
    )
    second = calculate_financial_result(
        branch, discount_rate=0.04, lifetime_earnings=110, provenance=provenance()
    )
    changed = calculate_financial_result(
        branch, discount_rate=0.05, lifetime_earnings=110, provenance=provenance()
    )
    assert first.configuration_hash == second.configuration_hash
    assert first.configuration_hash != changed.configuration_hash


def test_result_is_machine_readable_and_preserves_metric_states() -> None:
    result = calculate_financial_result(
        available_branch(-100, -20, -30),
        discount_rate=0.04,
        lifetime_earnings=50,
        provenance=provenance(),
    )
    payload = result.as_dict()
    assert json.loads(json.dumps(payload)) == payload
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    irr = metrics["internal_rate_of_return"]
    break_even = metrics["break_even"]
    assert isinstance(irr, dict) and irr["status"] == "NO_ROOT"
    assert isinstance(break_even, dict) and break_even["status"] == "NEVER"


def test_insufficient_branch_and_missing_earnings_are_explicit() -> None:
    missing_branch = BranchResult(
        ReturnPerspective.ENROLLMENT,
        BranchStatus.INSUFFICIENT_DATA,
        None,
        "completion probability is required",
        {"completion_probability": None},
    )
    result = calculate_financial_result(
        missing_branch, discount_rate=0.04, lifetime_earnings=None, provenance=provenance()
    )
    assert result.status is FinancialResultStatus.INSUFFICIENT_DATA
    assert result.metrics is None
    assert result.reason == "completion probability is required"
    missing_earnings = calculate_financial_result(
        available_branch(-100, 110),
        discount_rate=0.04,
        lifetime_earnings=None,
        provenance=provenance(),
    )
    assert missing_earnings.status is FinancialResultStatus.INSUFFICIENT_DATA
    assert missing_earnings.reason is not None
    assert "lifetime earnings" in missing_earnings.reason


def test_provenance_and_result_inputs_are_validated() -> None:
    with pytest.raises(ValueError, match="artifact identifier"):
        ComputationProvenance("model", "1", (), {})
    with pytest.raises(ValueError, match="JSON-compatible"):
        provenance(invalid={1, 2})
    with pytest.raises(ValueError, match="greater than -1"):
        calculate_financial_result(
            available_branch(-1, 2),
            discount_rate=-1,
            lifetime_earnings=2,
            provenance=provenance(),
        )
