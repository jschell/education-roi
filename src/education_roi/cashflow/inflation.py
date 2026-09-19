"""Explicit, provenance-bearing constant-dollar conversions."""

from dataclasses import dataclass
from math import isfinite

from education_roi.cashflow.models import DollarMode, MoneyBasis


@dataclass(frozen=True)
class CPIConversion:
    """One CPI transformation between two annual constant-dollar bases."""

    series: str
    source_year: int
    target_year: int
    source_index: float
    target_index: float

    def __post_init__(self) -> None:
        if not self.series.strip():
            raise ValueError("CPI series cannot be empty")
        if self.source_year < 1900 or self.target_year < 1900:
            raise ValueError("CPI years must be 1900 or later")
        if not all(
            isfinite(value) and value > 0 for value in (self.source_index, self.target_index)
        ):
            raise ValueError("CPI indexes must be finite and positive")

    @property
    def factor(self) -> float:
        """Return the target-index/source-index conversion factor."""
        return self.target_index / self.source_index

    @property
    def source_basis(self) -> MoneyBasis:
        return MoneyBasis(DollarMode.REAL, self.source_year)

    @property
    def target_basis(self) -> MoneyBasis:
        return MoneyBasis(DollarMode.REAL, self.target_year)

    def convert(self, amount: float, basis: MoneyBasis) -> float:
        """Convert an amount only when its declared basis exactly matches the source."""
        if not isfinite(amount):
            raise ValueError("amount must be finite")
        if basis.mode is DollarMode.NOMINAL:
            raise ValueError("nominal amounts require a dated nominal-to-real transformation")
        if basis != self.source_basis:
            raise ValueError("amount dollar year does not match CPI source year")
        return amount * self.factor

    def as_assumption(self) -> dict[str, str | int | float]:
        """Return a JSON-compatible record of the exact transformation."""
        return {
            "name": "cpi_conversion",
            "series": self.series,
            "source_year": self.source_year,
            "target_year": self.target_year,
            "source_index": self.source_index,
            "target_index": self.target_index,
            "factor": self.factor,
        }
