"""Deterministic education-path cash-flow models and metrics."""

from education_roi.cashflow.completion import (
    BranchResult,
    BranchStatus,
    CompletionAssumptions,
    CompletionReturnSet,
    ReturnPerspective,
    completion_return_branches,
)
from education_roi.cashflow.costs import (
    CostAssumptions,
    EducationCostInput,
    EducationCostResult,
    build_education_cost_schedule,
    selection_adjusted_earnings,
    selection_adjusted_foregone_earnings,
)
from education_roi.cashflow.financing import (
    AnnualDebtPayment,
    LoanSchedule,
    LoanTerms,
    build_loan_schedule,
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
from education_roi.cashflow.results import (
    ComputationProvenance,
    FinancialMetrics,
    FinancialResult,
    FinancialResultStatus,
    calculate_financial_result,
)

__all__ = [
    "AnnualCashFlow",
    "AnnualDebtPayment",
    "BranchResult",
    "BranchStatus",
    "BreakEvenResult",
    "BreakEvenStatus",
    "CashFlowPoint",
    "CashFlowSeries",
    "CPIConversion",
    "CompletionAssumptions",
    "CompletionReturnSet",
    "ComputationProvenance",
    "CostAssumptions",
    "DollarMode",
    "EducationCostInput",
    "EducationCostResult",
    "FinancialMetrics",
    "FinancialResult",
    "FinancialResultStatus",
    "IRRResult",
    "IRRStatus",
    "LoanSchedule",
    "LoanTerms",
    "MoneyBasis",
    "ReturnPerspective",
    "ScenarioCashFlow",
    "break_even_age",
    "build_education_cost_schedule",
    "build_loan_schedule",
    "calculate_financial_result",
    "completion_return_branches",
    "incremental_cash_flow",
    "internal_rate_of_return",
    "lifetime_net_value",
    "net_present_value",
    "selection_adjusted_earnings",
    "selection_adjusted_foregone_earnings",
]
