"""Education-cost schedules and earnings-level selection adjustments."""

from dataclasses import dataclass
from math import isfinite

from education_roi.cashflow.models import AnnualCashFlow, MoneyBasis, ScenarioCashFlow


@dataclass(frozen=True)
class EducationCostInput:
    """Observed annual education expenses before model attribution choices."""

    age: int
    tuition: float
    fees: float
    books: float
    other_nontuition: float
    living_cost: float
    counterfactual_living_cost: float
    grant_aid: float
    student_earnings: float
    loan_proceeds: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.tuition,
            self.fees,
            self.books,
            self.other_nontuition,
            self.living_cost,
            self.counterfactual_living_cost,
            self.grant_aid,
            self.student_earnings,
            self.loan_proceeds,
        )
        if self.age < 0:
            raise ValueError("age cannot be negative")
        if not all(isfinite(value) and value >= 0 for value in values):
            raise ValueError("education-cost inputs must be finite and nonnegative")
        if self.living_cost < self.counterfactual_living_cost:
            raise ValueError("living cost cannot be below counterfactual living cost")


@dataclass(frozen=True)
class CostAssumptions:
    """Explicit assumptions used to construct education-period cash flows."""

    nontuition_attribution: float
    selection_adjustment: float

    def __post_init__(self) -> None:
        for name, value in (
            ("nontuition_attribution", self.nontuition_attribution),
            ("selection_adjustment", self.selection_adjustment),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")

    def as_dict(self) -> dict[str, float]:
        """Return JSON-compatible model assumptions."""
        return {
            "nontuition_attribution": self.nontuition_attribution,
            "selection_adjustment": self.selection_adjustment,
        }


@dataclass(frozen=True)
class EducationCostResult:
    """Calculated schedule together with its machine-readable assumptions."""

    scenario: ScenarioCashFlow
    assumptions: dict[str, object]


def build_education_cost_schedule(
    name: str,
    basis: MoneyBasis,
    years: tuple[EducationCostInput, ...],
    assumptions: CostAssumptions,
    graduate_earnings: tuple[float, ...] = (),
) -> EducationCostResult:
    """Construct enrollment and post-graduation flows without treating loans as aid."""
    if not years:
        raise ValueError("education schedule requires at least one year")
    ages = tuple(year.age for year in years)
    if ages != tuple(range(ages[0], ages[0] + len(ages))):
        raise ValueError("education schedule ages must be unique, ordered, and consecutive")

    if not all(isfinite(value) and value >= 0 for value in graduate_earnings):
        raise ValueError("graduate earnings must be finite and nonnegative")
    enrollment_annual = tuple(
        AnnualCashFlow(
            age=year.age,
            earnings=year.student_earnings,
            direct_education_cost=(
                year.tuition
                + year.fees
                + year.books
                + assumptions.nontuition_attribution * year.other_nontuition
            ),
            incremental_living_cost=year.living_cost - year.counterfactual_living_cost,
            grant_aid=year.grant_aid,
            financing_cost=0.0,
        )
        for year in years
    )
    first_graduate_age = ages[-1] + 1
    graduate_annual = tuple(
        AnnualCashFlow(
            age=first_graduate_age + offset,
            earnings=earnings,
            direct_education_cost=0.0,
            incremental_living_cost=0.0,
            grant_aid=0.0,
            financing_cost=0.0,
        )
        for offset, earnings in enumerate(graduate_earnings)
    )
    return EducationCostResult(
        scenario=ScenarioCashFlow(name, basis, enrollment_annual + graduate_annual),
        assumptions={
            **assumptions.as_dict(),
            "enrollment_years": len(years),
            "enrollment_ages": list(ages),
            "loans_treated_as_aid": False,
        },
    )


def selection_adjusted_earnings(
    option_earnings: float, counterfactual_earnings: float, selection_adjustment: float
) -> float:
    """Move the counterfactual toward option earnings by the selected share of their gap."""
    values = (option_earnings, counterfactual_earnings, selection_adjustment)
    if not all(isfinite(value) for value in values):
        raise ValueError("selection inputs must be finite")
    if not 0 <= selection_adjustment <= 1:
        raise ValueError("selection_adjustment must be between 0 and 1")
    return counterfactual_earnings + selection_adjustment * (
        option_earnings - counterfactual_earnings
    )


def selection_adjusted_foregone_earnings(
    observed_counterfactual_earnings: float,
    earnings_premium: float,
    selection_adjustment: float,
) -> float:
    """Apply the selected share of an estimated premium to enrollment opportunity cost."""
    values = (observed_counterfactual_earnings, earnings_premium, selection_adjustment)
    if not all(isfinite(value) for value in values):
        raise ValueError("selection inputs must be finite")
    if observed_counterfactual_earnings < 0 or earnings_premium < 0:
        raise ValueError("earnings and earnings_premium cannot be negative")
    if not 0 <= selection_adjustment <= 1:
        raise ValueError("selection_adjustment must be between 0 and 1")
    return observed_counterfactual_earnings * (1 + earnings_premium * selection_adjustment)
