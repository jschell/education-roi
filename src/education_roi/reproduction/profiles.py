"""Deterministic age-earnings profiles for Zhang Equations 2–4."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from json import dumps
from math import exp, isfinite


class CovariateSlopeSpecification(StrEnum):
    GROUP_SPECIFIC = "group_specific"
    COMMON = "common"


@dataclass(frozen=True)
class EarningsCoefficients:
    group: str
    standardized_log_intercept: float
    age: float
    age_squared: float
    covariate_slope_specification: CovariateSlopeSpecification
    standardized_covariates: dict[str, float]
    coefficient_source: str

    def __post_init__(self) -> None:
        if not self.group.strip() or not self.coefficient_source.strip():
            raise ValueError("group and coefficient source cannot be empty")
        values = (self.standardized_log_intercept, self.age, self.age_squared)
        if not all(isfinite(value) for value in values):
            raise ValueError("earnings coefficients must be finite")
        if not self.standardized_covariates or not all(
            key.strip() and isfinite(value) for key, value in self.standardized_covariates.items()
        ):
            raise ValueError("standardized covariates must be named and finite")

    def as_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "standardized_log_intercept": self.standardized_log_intercept,
            "age": self.age,
            "age_squared": self.age_squared,
            "covariate_slope_specification": self.covariate_slope_specification.value,
            "standardized_covariates": self.standardized_covariates,
            "coefficient_source": self.coefficient_source,
        }


@dataclass(frozen=True)
class EarningsPoint:
    age: int
    earnings: float


@dataclass(frozen=True)
class EarningsProfile:
    group: str
    points: tuple[EarningsPoint, ...]
    coefficient_hash: str
    coefficients: EarningsCoefficients

    def earnings_at(self, age: int) -> float:
        for point in self.points:
            if point.age == age:
                return point.earnings
        raise ValueError(f"age {age} is outside the earnings profile")


def build_age_earnings_profile(
    coefficients: EarningsCoefficients, *, minimum_age: int = 18, maximum_age: int = 65
) -> EarningsProfile:
    """Evaluate exp(intercept + beta_age*age + beta_age2*age²) without rounding."""
    if minimum_age < 0 or minimum_age > maximum_age:
        raise ValueError("profile age bounds are invalid")
    points = tuple(
        EarningsPoint(
            age,
            exp(
                coefficients.standardized_log_intercept
                + coefficients.age * age
                + coefficients.age_squared * age**2
            ),
        )
        for age in range(minimum_age, maximum_age + 1)
    )
    encoded = dumps(coefficients.as_dict(), sort_keys=True, separators=(",", ":")).encode()
    return EarningsProfile(coefficients.group, points, sha256(encoded).hexdigest(), coefficients)
