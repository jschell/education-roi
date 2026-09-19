"""Deterministic education-path cash-flow models and metrics."""

from education_roi.cashflow.costs import (
    CostAssumptions,
    EducationCostInput,
    EducationCostResult,
    build_education_cost_schedule,
    selection_adjusted_earnings,
    selection_adjusted_foregone_earnings,
)
from education_roi.cashflow.inflation import CPIConversion
from education_roi.cashflow.metrics import (
    BreakEvenResult,
    BreakEvenStatus,
    IRRResult,
    IRRStatus,
    break_even_age,
    internal_rate_of_return,
    lifetime_net_value,
    net_present_value,
)
from education_roi.cashflow.models import (
    AnnualCashFlow,
    CashFlowPoint,
    CashFlowSeries,
    DollarMode,
    MoneyBasis,
    ScenarioCashFlow,
    incremental_cash_flow,
)

__all__ = [
    "AnnualCashFlow",
    "BreakEvenResult",
    "BreakEvenStatus",
    "CashFlowPoint",
    "CashFlowSeries",
    "CPIConversion",
    "CostAssumptions",
    "DollarMode",
    "EducationCostInput",
    "EducationCostResult",
    "IRRResult",
    "IRRStatus",
    "MoneyBasis",
    "ScenarioCashFlow",
    "break_even_age",
    "build_education_cost_schedule",
    "incremental_cash_flow",
    "internal_rate_of_return",
    "lifetime_net_value",
    "net_present_value",
    "selection_adjusted_earnings",
    "selection_adjusted_foregone_earnings",
]
