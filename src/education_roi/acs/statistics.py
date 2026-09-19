"""Weighted descriptive statistics with explicit sample support."""

from dataclasses import dataclass
from math import isfinite, sqrt

import polars as pl

from education_roi.acs.source import REPLICATE_WEIGHT_COLUMNS


@dataclass(frozen=True)
class WeightedEstimate:
    """A point estimate with its unweighted and weighted sample support."""

    quantile: float
    value: float
    unweighted_n: int
    weighted_n: float


@dataclass(frozen=True)
class SDRUncertainty:
    """ACS successive-difference-replication sampling uncertainty."""

    estimate: float
    standard_error: float
    margin_of_error_90: float
    confidence_interval_90: tuple[float, float]
    replicate_count: int = 80
    method: str = "ACS successive difference replication"


def successive_difference_uncertainty(
    estimate: float, replicate_estimates: list[float] | tuple[float, ...]
) -> SDRUncertainty:
    """Apply the Census SDR formula and its standard 90% confidence interval."""
    if len(replicate_estimates) != 80:
        raise ValueError("ACS SDR requires exactly 80 replicate estimates")
    values = (estimate, *replicate_estimates)
    if not all(isfinite(value) for value in values):
        raise ValueError("ACS SDR estimates must be finite")
    standard_error = sqrt((4 / 80) * sum((replicate - estimate) ** 2 for replicate in values[1:]))
    margin = 1.645 * standard_error
    return SDRUncertainty(
        estimate=estimate,
        standard_error=standard_error,
        margin_of_error_90=margin,
        confidence_interval_90=(estimate - margin, estimate + margin),
    )


def _weighted_mean(frame: pl.DataFrame, value_column: str, weight_column: str) -> float:
    selected = frame.select(value_column, weight_column).drop_nulls()
    denominator = float(selected.get_column(weight_column).sum())
    if denominator == 0:
        raise ValueError(f"weighted mean has a zero denominator for {weight_column}")
    numerator = float(selected.select((pl.col(value_column) * pl.col(weight_column)).sum()).item())
    return numerator / denominator


def replicate_weighted_mean(
    frame: pl.DataFrame,
    value_column: str,
    *,
    full_weight_column: str = "person_weight",
    replicate_weight_columns: tuple[str, ...] = REPLICATE_WEIGHT_COLUMNS,
) -> SDRUncertainty:
    """Estimate a weighted mean and SDR uncertainty without discarding negative replicates."""
    missing = sorted(
        {full_weight_column, *replicate_weight_columns, value_column}.difference(frame.columns)
    )
    if missing:
        raise ValueError(f"replicate mean is missing columns: {', '.join(missing)}")
    estimate = _weighted_mean(frame, value_column, full_weight_column)
    replicates = [
        _weighted_mean(frame, value_column, replicate) for replicate in replicate_weight_columns
    ]
    return successive_difference_uncertainty(estimate, replicates)


def replicate_weighted_total(
    frame: pl.DataFrame,
    value_column: str | None = None,
    *,
    full_weight_column: str = "person_weight",
    replicate_weight_columns: tuple[str, ...] = REPLICATE_WEIGHT_COLUMNS,
) -> SDRUncertainty:
    """Estimate a population or value total and its SDR uncertainty."""
    required = {full_weight_column, *replicate_weight_columns}
    if value_column is not None:
        required.add(value_column)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"replicate total is missing columns: {', '.join(missing)}")

    def total(weight_column: str) -> float:
        if value_column is None:
            return float(frame.get_column(weight_column).sum())
        return float(frame.select((pl.col(value_column) * pl.col(weight_column)).sum()).item())

    estimate = total(full_weight_column)
    replicates = [total(column) for column in replicate_weight_columns]
    return successive_difference_uncertainty(estimate, replicates)


def weighted_quantile(
    frame: pl.DataFrame,
    quantile: float,
    *,
    value_column: str = "wage_salary_adjusted",
    weight_column: str = "person_weight",
) -> WeightedEstimate:
    """Return the first value whose cumulative weight reaches q times total weight."""
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    clean = (
        frame.select(value_column, weight_column)
        .drop_nulls()
        .filter(pl.col(weight_column) > 0)
        .sort(value_column)
    )
    if clean.is_empty():
        raise ValueError("weighted quantile requires at least one positive-weight observation")
    weighted_n = float(clean.get_column(weight_column).sum())
    threshold = quantile * weighted_n
    cumulative = clean.get_column(weight_column).cum_sum()
    index = next(
        (position for position, total in enumerate(cumulative) if float(total) >= threshold),
        clean.height - 1,
    )
    return WeightedEstimate(
        quantile=quantile,
        value=float(clean.get_column(value_column)[index]),
        unweighted_n=clean.height,
        weighted_n=weighted_n,
    )
