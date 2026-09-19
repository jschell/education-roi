"""Explicit, auditable fallback selection for ACS estimates."""

from dataclasses import dataclass
from enum import StrEnum

import polars as pl

from education_roi.acs.statistics import WeightedEstimate, weighted_quantile


class FallbackStatus(StrEnum):
    """Outcome of evaluating an ordered fallback hierarchy."""

    SELECTED = "SELECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class SampleScope:
    """Human- and machine-readable definition of one candidate estimate scope."""

    level: str
    geography: str
    age: str
    major: str


@dataclass(frozen=True)
class FallbackCandidate:
    """A pre-filtered frame at one explicitly defined level of specificity."""

    scope: SampleScope
    frame: pl.DataFrame


@dataclass(frozen=True)
class SupportThresholds:
    """Minimum support required to publish an estimate."""

    min_unweighted_n: int
    min_weighted_n: float

    def __post_init__(self) -> None:
        if self.min_unweighted_n < 1:
            raise ValueError("min_unweighted_n must be at least 1")
        if not self.min_weighted_n > 0:
            raise ValueError("min_weighted_n must be greater than zero")


@dataclass(frozen=True)
class FallbackAttempt:
    """Support observed for one attempted scope and why it passed or failed."""

    scope: SampleScope
    unweighted_n: int
    weighted_n: float
    sufficient: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class FallbackEstimate:
    """A selected estimate or an explicit insufficient-data result."""

    status: FallbackStatus
    estimate: WeightedEstimate | None
    selected_scope: SampleScope | None
    attempts: tuple[FallbackAttempt, ...]
    fallback_used: bool


def _support(
    candidate: FallbackCandidate,
    thresholds: SupportThresholds,
    value_column: str,
    weight_column: str,
) -> tuple[FallbackAttempt, pl.DataFrame]:
    missing = sorted({value_column, weight_column}.difference(candidate.frame.columns))
    if missing:
        raise ValueError(
            f"fallback level {candidate.scope.level!r} is missing columns: {', '.join(missing)}"
        )
    usable = (
        candidate.frame.select(value_column, weight_column)
        .drop_nulls()
        .filter(pl.col(weight_column) > 0)
    )
    unweighted_n = usable.height
    weighted_n = float(usable.get_column(weight_column).sum())
    failures: list[str] = []
    if unweighted_n < thresholds.min_unweighted_n:
        failures.append(f"unweighted_n {unweighted_n} < {thresholds.min_unweighted_n}")
    if weighted_n < thresholds.min_weighted_n:
        failures.append(f"weighted_n {weighted_n:g} < {thresholds.min_weighted_n:g}")
    return (
        FallbackAttempt(
            scope=candidate.scope,
            unweighted_n=unweighted_n,
            weighted_n=weighted_n,
            sufficient=not failures,
            failures=tuple(failures),
        ),
        usable,
    )


def fallback_weighted_quantile(
    candidates: list[FallbackCandidate] | tuple[FallbackCandidate, ...],
    quantile: float,
    thresholds: SupportThresholds,
    *,
    value_column: str = "wage_salary_adjusted",
    weight_column: str = "person_weight",
) -> FallbackEstimate:
    """Select the first supported quantile from an exact-to-broad hierarchy.

    Candidate frames must already represent the scopes named in their metadata. The function never
    broadens, pools, or substitutes a dataset implicitly.
    """
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    if not candidates:
        raise ValueError("fallback hierarchy requires at least one candidate")
    levels = [candidate.scope.level for candidate in candidates]
    if len(levels) != len(set(levels)):
        raise ValueError("fallback hierarchy level names must be unique")

    attempts: list[FallbackAttempt] = []
    for index, candidate in enumerate(candidates):
        attempt, usable = _support(candidate, thresholds, value_column, weight_column)
        attempts.append(attempt)
        if attempt.sufficient:
            return FallbackEstimate(
                status=FallbackStatus.SELECTED,
                estimate=weighted_quantile(
                    usable,
                    quantile,
                    value_column=value_column,
                    weight_column=weight_column,
                ),
                selected_scope=candidate.scope,
                attempts=tuple(attempts),
                fallback_used=index > 0,
            )
    return FallbackEstimate(
        status=FallbackStatus.INSUFFICIENT_DATA,
        estimate=None,
        selected_scope=None,
        attempts=tuple(attempts),
        fallback_used=False,
    )
