"""Weighted descriptive statistics with explicit sample support."""

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class WeightedEstimate:
    """A point estimate with its unweighted and weighted sample support."""

    quantile: float
    value: float
    unweighted_n: int
    weighted_n: float


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
