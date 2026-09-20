"""Complete financial results with deterministic computational provenance."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from json import dumps
from math import isfinite

from education_roi.cashflow.completion import BranchResult, BranchStatus, ReturnPerspective
from education_roi.cashflow.metrics import (
    BreakEvenResult,
    IRRResult,
    break_even_age,
    internal_rate_of_return,
    lifetime_net_value,
    net_present_value,
)


class FinancialResultStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ComputationProvenance:
    """Model, data, and assumptions needed to reproduce a calculation."""

    model_name: str
    model_version: str
    dataset_artifact_ids: tuple[str, ...]
    assumptions: dict[str, object]
    transformation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.model_name.strip() or not self.model_version.strip():
            raise ValueError("model name and version cannot be empty")
        if not self.dataset_artifact_ids:
            raise ValueError("at least one dataset artifact identifier is required")
        identifiers = self.dataset_artifact_ids + self.transformation_ids
        if any(not identifier.strip() for identifier in identifiers):
            raise ValueError("provenance identifiers cannot be empty")
        if len(set(self.dataset_artifact_ids)) != len(self.dataset_artifact_ids):
            raise ValueError("dataset artifact identifiers must be unique")
        try:
            dumps(self.assumptions, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("assumptions must be JSON-compatible and finite") from error

    def as_dict(self) -> dict[str, object]:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "dataset_artifact_ids": list(self.dataset_artifact_ids),
            "transformation_ids": list(self.transformation_ids),
            "assumptions": self.assumptions,
        }


@dataclass(frozen=True)
class FinancialMetrics:
    net_present_value: float
    internal_rate_of_return: IRRResult
    lifetime_net_value: float
    lifetime_earnings: float
    break_even: BreakEvenResult

    def as_dict(self) -> dict[str, object]:
        return {
            "net_present_value": self.net_present_value,
            "internal_rate_of_return": {
                "status": self.internal_rate_of_return.status.value,
                "roots": list(self.internal_rate_of_return.roots),
                "lower_rate": self.internal_rate_of_return.lower_rate,
                "upper_rate": self.internal_rate_of_return.upper_rate,
            },
            "lifetime_net_value": self.lifetime_net_value,
            "lifetime_earnings": self.lifetime_earnings,
            "break_even": {
                "status": self.break_even.status.value,
                "age": self.break_even.age,
                "cumulative_value": self.break_even.cumulative_value,
            },
        }


@dataclass(frozen=True)
class FinancialResult:
    perspective: ReturnPerspective
    status: FinancialResultStatus
    metrics: FinancialMetrics | None
    reason: str | None
    configuration_hash: str
    provenance: ComputationProvenance

    def as_dict(self) -> dict[str, object]:
        return {
            "perspective": self.perspective.value,
            "status": self.status.value,
            "metrics": None if self.metrics is None else self.metrics.as_dict(),
            "reason": self.reason,
            "configuration_hash": self.configuration_hash,
            "provenance": self.provenance.as_dict(),
        }


def _configuration_hash(
    branch: BranchResult,
    discount_rate: float,
    lifetime_earnings: float | None,
    provenance: ComputationProvenance,
) -> str:
    cash_flow = branch.cash_flow
    payload = {
        "perspective": branch.perspective.value,
        "branch_status": branch.status.value,
        "reason": branch.reason,
        "discount_rate": discount_rate,
        "lifetime_earnings": lifetime_earnings,
        "cash_flow": None
        if cash_flow is None
        else {
            "name": cash_flow.name,
            "basis": {
                "mode": cash_flow.basis.mode.value,
                "dollar_year": cash_flow.basis.dollar_year,
            },
            "points": [[point.age, point.amount] for point in cash_flow.points],
        },
        "branch_assumptions": branch.assumptions,
        "provenance": provenance.as_dict(),
    }
    encoded = dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(encoded).hexdigest()


def calculate_financial_result(
    branch: BranchResult,
    *,
    discount_rate: float,
    lifetime_earnings: float | None,
    provenance: ComputationProvenance,
) -> FinancialResult:
    """Calculate all deterministic metrics or propagate insufficient evidence."""
    if not isfinite(discount_rate) or discount_rate <= -1:
        raise ValueError("discount_rate must be finite and greater than -1")
    if lifetime_earnings is not None and (not isfinite(lifetime_earnings) or lifetime_earnings < 0):
        raise ValueError("lifetime_earnings must be finite and nonnegative")
    configuration_hash = _configuration_hash(branch, discount_rate, lifetime_earnings, provenance)
    if branch.status is BranchStatus.INSUFFICIENT_DATA:
        return FinancialResult(
            branch.perspective,
            FinancialResultStatus.INSUFFICIENT_DATA,
            None,
            branch.reason,
            configuration_hash,
            provenance,
        )
    if branch.cash_flow is None:  # pragma: no cover - BranchResult validation protects this
        raise ValueError("available branch is missing cash flow")
    if lifetime_earnings is None:
        return FinancialResult(
            branch.perspective,
            FinancialResultStatus.INSUFFICIENT_DATA,
            None,
            "lifetime earnings are required for a complete financial result",
            configuration_hash,
            provenance,
        )
    metrics = FinancialMetrics(
        net_present_value=net_present_value(branch.cash_flow, discount_rate),
        internal_rate_of_return=internal_rate_of_return(branch.cash_flow),
        lifetime_net_value=lifetime_net_value(branch.cash_flow),
        lifetime_earnings=lifetime_earnings,
        break_even=break_even_age(branch.cash_flow),
    )
    return FinancialResult(
        branch.perspective,
        FinancialResultStatus.AVAILABLE,
        metrics,
        None,
        configuration_hash,
        provenance,
    )
