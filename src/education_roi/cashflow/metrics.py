"""Deterministic metrics over explicit annual cash-flow series."""

from dataclasses import dataclass
from enum import StrEnum
from math import exp, isfinite, log1p

from education_roi.cashflow.models import CashFlowSeries


class IRRStatus(StrEnum):
    """Whether a bounded IRR search found a unique, ambiguous, or absent result."""

    UNIQUE = "UNIQUE"
    MULTIPLE = "MULTIPLE"
    NO_ROOT = "NO_ROOT"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class IRRResult:
    """IRR roots and the exact search interval used."""

    status: IRRStatus
    roots: tuple[float, ...]
    lower_rate: float
    upper_rate: float


class BreakEvenStatus(StrEnum):
    """Outcome of an undiscounted cumulative incremental-value search."""

    ACHIEVED = "ACHIEVED"
    NEVER = "NEVER"


@dataclass(frozen=True)
class BreakEvenResult:
    """First age with nonnegative cumulative incremental value, if any."""

    status: BreakEvenStatus
    age: int | None
    cumulative_value: float


def net_present_value(series: CashFlowSeries, discount_rate: float) -> float:
    """Discount end-of-period flows, treating the first age as period zero."""
    if not isfinite(discount_rate) or discount_rate <= -1:
        raise ValueError("discount_rate must be finite and greater than -1")
    return sum(
        point.amount / (1 + discount_rate) ** period for period, point in enumerate(series.points)
    )


def lifetime_net_value(series: CashFlowSeries) -> float:
    """Return undiscounted lifetime net value."""
    return sum(point.amount for point in series.points)


def break_even_age(series: CashFlowSeries) -> BreakEvenResult:
    """Find the first age at which cumulative incremental value is nonnegative."""
    cumulative = 0.0
    for point in series.points:
        cumulative += point.amount
        if cumulative >= 0:
            return BreakEvenResult(BreakEvenStatus.ACHIEVED, point.age, cumulative)
    return BreakEvenResult(BreakEvenStatus.NEVER, None, cumulative)


def _bisect_root(
    series: CashFlowSeries, lower: float, upper: float, value_tolerance: float
) -> float:
    lower_value = net_present_value(series, lower)
    for _ in range(200):
        midpoint = (lower + upper) / 2
        midpoint_value = net_present_value(series, midpoint)
        if abs(midpoint_value) <= value_tolerance or upper - lower <= 1e-12:
            return midpoint
        if (lower_value < 0) == (midpoint_value < 0):
            lower = midpoint
            lower_value = midpoint_value
        else:
            upper = midpoint
    return (lower + upper) / 2


def internal_rate_of_return(
    series: CashFlowSeries,
    *,
    lower_rate: float = -0.999,
    upper_rate: float = 10.0,
    search_intervals: int = 10_000,
    value_tolerance: float = 1e-9,
) -> IRRResult:
    """Find all sign-changing IRR roots in a documented bounded rate interval.

    The logarithmic grid improves coverage near -100% and across large positive rates. Even-
    multiplicity roots that merely touch zero are not claimed unless a grid point itself is within
    tolerance; callers can widen or refine the search explicitly.
    """
    if not (-1 < lower_rate < upper_rate) or not all(
        isfinite(value) for value in (lower_rate, upper_rate)
    ):
        raise ValueError("IRR bounds must be finite with -1 < lower_rate < upper_rate")
    if search_intervals < 2:
        raise ValueError("search_intervals must be at least 2")
    if not isfinite(value_tolerance) or value_tolerance <= 0:
        raise ValueError("value_tolerance must be finite and positive")

    amounts = tuple(point.amount for point in series.points)
    if all(amount == 0 for amount in amounts):
        return IRRResult(IRRStatus.INDETERMINATE, (), lower_rate, upper_rate)
    if not (any(amount < 0 for amount in amounts) and any(amount > 0 for amount in amounts)):
        return IRRResult(IRRStatus.NO_ROOT, (), lower_rate, upper_rate)

    lower_log = log1p(lower_rate)
    upper_log = log1p(upper_rate)
    rates = tuple(
        exp(lower_log + (upper_log - lower_log) * index / search_intervals) - 1
        for index in range(search_intervals + 1)
    )
    roots: list[float] = []
    previous_rate = rates[0]
    previous_value = net_present_value(series, previous_rate)
    if abs(previous_value) <= value_tolerance:
        roots.append(previous_rate)
    for rate in rates[1:]:
        value = net_present_value(series, rate)
        root: float | None = None
        if abs(value) <= value_tolerance:
            root = rate
        elif (previous_value < 0) != (value < 0):
            root = _bisect_root(series, previous_rate, rate, value_tolerance)
        if root is not None and (not roots or abs(root - roots[-1]) > 1e-8):
            roots.append(root)
        previous_rate = rate
        previous_value = value

    status = (
        IRRStatus.NO_ROOT
        if not roots
        else IRRStatus.UNIQUE
        if len(roots) == 1
        else IRRStatus.MULTIPLE
    )
    return IRRResult(status, tuple(roots), lower_rate, upper_rate)
