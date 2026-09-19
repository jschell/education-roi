"""Typed annual cash-flow inputs with explicit monetary basis."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class DollarMode(StrEnum):
    """Whether amounts are constant-dollar or nominal values."""

    REAL = "real"
    NOMINAL = "nominal"


@dataclass(frozen=True)
class MoneyBasis:
    """Dollar basis shared by every amount in a cash-flow series."""

    mode: DollarMode
    dollar_year: int | None = None

    def __post_init__(self) -> None:
        if self.mode is DollarMode.REAL and self.dollar_year is None:
            raise ValueError("real-dollar basis requires a dollar_year")
        if self.mode is DollarMode.NOMINAL and self.dollar_year is not None:
            raise ValueError("nominal-dollar basis cannot declare a constant dollar_year")
        if self.dollar_year is not None and self.dollar_year < 1900:
            raise ValueError("dollar_year must be 1900 or later")


@dataclass(frozen=True)
class AnnualCashFlow:
    """Explicit components for one age; costs are stored as positive amounts."""

    age: int
    earnings: float
    direct_education_cost: float
    incremental_living_cost: float
    grant_aid: float
    financing_cost: float

    def __post_init__(self) -> None:
        values = (
            self.earnings,
            self.direct_education_cost,
            self.incremental_living_cost,
            self.grant_aid,
            self.financing_cost,
        )
        if self.age < 0:
            raise ValueError("age cannot be negative")
        if not all(isfinite(value) for value in values):
            raise ValueError("annual cash-flow components must be finite")
        costs = (
            self.direct_education_cost,
            self.incremental_living_cost,
            self.grant_aid,
            self.financing_cost,
        )
        if any(value < 0 for value in costs):
            raise ValueError("cost, aid, and financing components cannot be negative")

    @property
    def net_amount(self) -> float:
        """Return earnings and grant aid less education, living, and financing costs."""
        return (
            self.earnings
            + self.grant_aid
            - self.direct_education_cost
            - self.incremental_living_cost
            - self.financing_cost
        )


@dataclass(frozen=True)
class CashFlowPoint:
    """One end-of-period cash flow indexed by age."""

    age: int
    amount: float

    def __post_init__(self) -> None:
        if self.age < 0:
            raise ValueError("age cannot be negative")
        if not isfinite(self.amount):
            raise ValueError("cash-flow amount must be finite")


@dataclass(frozen=True)
class CashFlowSeries:
    """A consecutive annual series; the first point is period zero for discounting."""

    name: str
    basis: MoneyBasis
    points: tuple[CashFlowPoint, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("cash-flow series name cannot be empty")
        if not self.points:
            raise ValueError("cash-flow series requires at least one point")
        ages = [point.age for point in self.points]
        if ages != list(range(ages[0], ages[0] + len(ages))):
            raise ValueError("cash-flow ages must be unique, ordered, and consecutive")


@dataclass(frozen=True)
class ScenarioCashFlow:
    """Annual components for one education or counterfactual scenario."""

    name: str
    basis: MoneyBasis
    annual: tuple[AnnualCashFlow, ...]

    def __post_init__(self) -> None:
        CashFlowSeries(
            name=self.name,
            basis=self.basis,
            points=tuple(CashFlowPoint(item.age, item.net_amount) for item in self.annual),
        )

    def net_series(self) -> CashFlowSeries:
        """Project the component schedule into annual net cash flows."""
        return CashFlowSeries(
            name=self.name,
            basis=self.basis,
            points=tuple(CashFlowPoint(item.age, item.net_amount) for item in self.annual),
        )

    @property
    def lifetime_earnings(self) -> float:
        """Return undiscounted earnings without conflating them with net value."""
        return sum(item.earnings for item in self.annual)


def incremental_cash_flow(
    option: ScenarioCashFlow, counterfactual: ScenarioCashFlow
) -> CashFlowSeries:
    """Subtract a counterfactual scenario without silently aligning or converting inputs."""
    if option.basis != counterfactual.basis:
        raise ValueError("scenario and counterfactual must use the same money basis")
    option_series = option.net_series()
    counterfactual_series = counterfactual.net_series()
    option_ages = tuple(point.age for point in option_series.points)
    counterfactual_ages = tuple(point.age for point in counterfactual_series.points)
    if option_ages != counterfactual_ages:
        raise ValueError("scenario and counterfactual must cover identical ages")
    return CashFlowSeries(
        name=f"{option.name} vs {counterfactual.name}",
        basis=option.basis,
        points=tuple(
            CashFlowPoint(option_point.age, option_point.amount - counterfactual_point.amount)
            for option_point, counterfactual_point in zip(
                option_series.points, counterfactual_series.points, strict=True
            )
        ),
    )
