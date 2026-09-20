"""Completion-conditioned and enrollment-weighted cash-flow branches."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from education_roi.cashflow.models import (
    CashFlowPoint,
    CashFlowSeries,
    ScenarioCashFlow,
    incremental_cash_flow,
)


class ReturnPerspective(StrEnum):
    CONDITIONAL_GRADUATE = "conditional_graduate"
    ENROLLMENT = "enrollment"


class BranchStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class CompletionAssumptions:
    """Explicit completion probability and branch timing assumptions."""

    completion_probability: float | None
    graduation_age: int
    noncompletion_exit_age: int | None

    def __post_init__(self) -> None:
        if self.completion_probability is not None and (
            not isfinite(self.completion_probability) or not 0 <= self.completion_probability <= 1
        ):
            raise ValueError("completion_probability must be between 0 and 1")
        if self.graduation_age < 0:
            raise ValueError("graduation_age cannot be negative")
        if self.noncompletion_exit_age is not None and self.noncompletion_exit_age < 0:
            raise ValueError("noncompletion_exit_age cannot be negative")

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "completion_probability": self.completion_probability,
            "graduation_age": self.graduation_age,
            "noncompletion_exit_age": self.noncompletion_exit_age,
        }


@dataclass(frozen=True)
class BranchResult:
    perspective: ReturnPerspective
    status: BranchStatus
    cash_flow: CashFlowSeries | None
    reason: str | None
    assumptions: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.status is BranchStatus.AVAILABLE:
            if self.cash_flow is None or self.reason is not None:
                raise ValueError("available branch requires cash flow and no reason")
        elif self.cash_flow is not None or not self.reason:
            raise ValueError("insufficient-data branch requires a reason and no cash flow")


@dataclass(frozen=True)
class CompletionReturnSet:
    conditional_graduate: BranchResult
    enrollment: BranchResult


def _validate_timing(scenario: ScenarioCashFlow, age: int, label: str) -> None:
    if age not in tuple(item.age for item in scenario.annual):
        raise ValueError(f"{label} must fall within the scenario age range")


def completion_return_branches(
    graduate: ScenarioCashFlow,
    counterfactual: ScenarioCashFlow,
    assumptions: CompletionAssumptions,
    noncompleter: ScenarioCashFlow | None = None,
) -> CompletionReturnSet:
    """Build distinct graduate-conditional and probability-weighted enrollment returns."""
    _validate_timing(graduate, assumptions.graduation_age, "graduation_age")
    graduate_incremental = incremental_cash_flow(graduate, counterfactual)
    record = assumptions.as_dict()
    conditional = BranchResult(
        ReturnPerspective.CONDITIONAL_GRADUATE,
        BranchStatus.AVAILABLE,
        graduate_incremental,
        None,
        record,
    )
    probability = assumptions.completion_probability
    if probability is None:
        return CompletionReturnSet(
            conditional,
            BranchResult(
                ReturnPerspective.ENROLLMENT,
                BranchStatus.INSUFFICIENT_DATA,
                None,
                "completion probability is required for enrollment return",
                record,
            ),
        )
    if probability == 1:
        return CompletionReturnSet(
            conditional,
            BranchResult(
                ReturnPerspective.ENROLLMENT,
                BranchStatus.AVAILABLE,
                CashFlowSeries(
                    f"{graduate.name} enrollment return vs {counterfactual.name}",
                    graduate_incremental.basis,
                    graduate_incremental.points,
                ),
                None,
                record,
            ),
        )
    if noncompleter is None:
        return CompletionReturnSet(
            conditional,
            BranchResult(
                ReturnPerspective.ENROLLMENT,
                BranchStatus.INSUFFICIENT_DATA,
                None,
                "non-completer cash flow is required when completion probability is below 1",
                record,
            ),
        )
    if assumptions.noncompletion_exit_age is None:
        return CompletionReturnSet(
            conditional,
            BranchResult(
                ReturnPerspective.ENROLLMENT,
                BranchStatus.INSUFFICIENT_DATA,
                None,
                "non-completion exit age is required for the non-completer branch",
                record,
            ),
        )
    _validate_timing(noncompleter, assumptions.noncompletion_exit_age, "noncompletion_exit_age")
    noncompletion_incremental = incremental_cash_flow(noncompleter, counterfactual)
    if tuple(point.age for point in graduate_incremental.points) != tuple(
        point.age for point in noncompletion_incremental.points
    ):
        raise ValueError("graduate and non-completer branches must cover identical ages")
    weighted = CashFlowSeries(
        f"{graduate.name} enrollment return vs {counterfactual.name}",
        graduate_incremental.basis,
        tuple(
            CashFlowPoint(
                graduate_point.age,
                probability * graduate_point.amount
                + (1 - probability) * noncompletion_point.amount,
            )
            for graduate_point, noncompletion_point in zip(
                graduate_incremental.points, noncompletion_incremental.points, strict=True
            )
        ),
    )
    return CompletionReturnSet(
        conditional,
        BranchResult(ReturnPerspective.ENROLLMENT, BranchStatus.AVAILABLE, weighted, None, record),
    )
