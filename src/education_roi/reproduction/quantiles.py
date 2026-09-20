"""Quantile-profile contracts and distributional IRR calculations."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from json import dumps
from math import exp, isfinite

from education_roi.cashflow import CashFlowSeries, IRRResult, internal_rate_of_return

DECILES = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)
RANK_INVARIANCE_WARNING = (
    "Observed earnings-distribution position; not an individual probability. "
    "Cross-state comparison assumes rank invariance."
)


@dataclass(frozen=True, order=True)
class QuantileDefinition:
    """A supported earnings decile with its required interpretation label."""

    quantile: float

    def __post_init__(self) -> None:
        if self.quantile not in DECILES:
            raise ValueError("quantile must be one of the nine earnings deciles")

    @property
    def label(self) -> str:
        return f"P{round(self.quantile * 100)}"

    @property
    def is_median(self) -> bool:
        return self.quantile == 0.50

    def as_dict(self) -> dict[str, object]:
        return {
            "quantile": self.quantile,
            "label": self.label,
            "is_median": self.is_median,
            "rank_invariance_assumption": True,
            "interpretation": RANK_INVARIANCE_WARNING,
        }


class SolverStatus(StrEnum):
    CONVERGED = "CONVERGED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class QuantileSolverMetadata:
    """Auditable convergence record supplied by a quantile-regression implementation."""

    algorithm: str
    implementation: str
    implementation_version: str
    status: SolverStatus
    iterations: int
    tolerance: float
    objective_value: float | None
    message: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (self.algorithm, self.implementation, self.implementation_version)
        ):
            raise ValueError("solver identity fields cannot be empty")
        if self.iterations < 0:
            raise ValueError("solver iterations cannot be negative")
        if not isfinite(self.tolerance) or self.tolerance <= 0:
            raise ValueError("solver tolerance must be finite and positive")
        if self.objective_value is not None and not isfinite(self.objective_value):
            raise ValueError("solver objective must be finite when supplied")

    def as_dict(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "implementation": self.implementation,
            "implementation_version": self.implementation_version,
            "status": self.status.value,
            "iterations": self.iterations,
            "tolerance": self.tolerance,
            "objective_value": self.objective_value,
            "message": self.message,
        }


@dataclass(frozen=True)
class QuantileEarningsCoefficients:
    """Standardized quadratic log-earnings coefficients at one decile."""

    group: str
    definition: QuantileDefinition
    standardized_log_intercept: float
    age: float
    age_squared: float
    coefficient_source: str

    def __post_init__(self) -> None:
        if not self.group.strip() or not self.coefficient_source.strip():
            raise ValueError("coefficient group and source cannot be empty")
        if not all(
            isfinite(value)
            for value in (self.standardized_log_intercept, self.age, self.age_squared)
        ):
            raise ValueError("quantile earnings coefficients must be finite")

    def as_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "definition": self.definition.as_dict(),
            "standardized_log_intercept": self.standardized_log_intercept,
            "age": self.age,
            "age_squared": self.age_squared,
            "coefficient_source": self.coefficient_source,
        }

    @property
    def coefficient_hash(self) -> str:
        encoded = dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class QuantileEarningsPoint:
    age: int
    earnings: float


@dataclass(frozen=True)
class QuantileEarningsProfile:
    """A converged, unrounded age-earnings profile at one distributional position."""

    group: str
    definition: QuantileDefinition
    points: tuple[QuantileEarningsPoint, ...]
    coefficient_hash: str
    solver: QuantileSolverMetadata

    def __post_init__(self) -> None:
        if self.solver.status is not SolverStatus.CONVERGED:
            raise ValueError("an earnings profile requires a converged solver")
        if not self.points:
            raise ValueError("quantile earnings profile cannot be empty")
        ages = tuple(point.age for point in self.points)
        if ages != tuple(range(ages[0], ages[0] + len(ages))):
            raise ValueError("profile ages must be ordered and consecutive")
        if not all(isfinite(point.earnings) and point.earnings >= 0 for point in self.points):
            raise ValueError("profile earnings must be finite and nonnegative")

    def earnings_at(self, age: int) -> float:
        for point in self.points:
            if point.age == age:
                return point.earnings
        raise ValueError(f"age {age} is outside the quantile earnings profile")

    def as_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "definition": self.definition.as_dict(),
            "coefficient_hash": self.coefficient_hash,
            "solver": self.solver.as_dict(),
            "points": [{"age": point.age, "earnings": point.earnings} for point in self.points],
        }


@dataclass(frozen=True)
class QuantileProfileFit:
    """A fit result that preserves solver failure rather than inventing a profile."""

    definition: QuantileDefinition
    solver: QuantileSolverMetadata
    profile: QuantileEarningsProfile | None

    def __post_init__(self) -> None:
        if (self.solver.status is SolverStatus.CONVERGED) != (self.profile is not None):
            raise ValueError("converged fits require a profile and failed fits forbid one")
        if self.profile is not None and (
            self.profile.definition != self.definition or self.profile.solver != self.solver
        ):
            raise ValueError("fit definition and solver must match the profile")

    def as_dict(self) -> dict[str, object]:
        return {
            "definition": self.definition.as_dict(),
            "solver": self.solver.as_dict(),
            "profile": None if self.profile is None else self.profile.as_dict(),
        }


def build_quantile_earnings_profile(
    coefficients: QuantileEarningsCoefficients,
    solver: QuantileSolverMetadata,
    *,
    minimum_age: int = 18,
    maximum_age: int = 65,
) -> QuantileProfileFit:
    """Evaluate a converged quadratic log profile without claiming to fit coefficients."""
    if minimum_age < 0 or minimum_age > maximum_age:
        raise ValueError("profile age bounds are invalid")
    if solver.status is SolverStatus.FAILED:
        return QuantileProfileFit(coefficients.definition, solver, None)
    points = tuple(
        QuantileEarningsPoint(
            age,
            exp(
                coefficients.standardized_log_intercept
                + coefficients.age * age
                + coefficients.age_squared * age**2
            ),
        )
        for age in range(minimum_age, maximum_age + 1)
    )
    profile = QuantileEarningsProfile(
        coefficients.group,
        coefficients.definition,
        points,
        coefficients.coefficient_hash,
        solver,
    )
    return QuantileProfileFit(coefficients.definition, solver, profile)


@dataclass(frozen=True)
class ProfilePointComparison:
    age: int
    calculated: float
    reference: float
    absolute_difference: float
    relative_difference: float | None
    passed: bool


@dataclass(frozen=True)
class ProfileValidationReport:
    """Comparison with values produced by a named independent implementation."""

    group: str
    definition: QuantileDefinition
    coefficient_hash: str
    reference_implementation: str
    absolute_tolerance: float
    relative_tolerance: float
    comparisons: tuple[ProfilePointComparison, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.comparisons)

    def as_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "definition": self.definition.as_dict(),
            "coefficient_hash": self.coefficient_hash,
            "reference_implementation": self.reference_implementation,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "passed": self.passed,
            "comparisons": [
                {
                    "age": item.age,
                    "calculated": item.calculated,
                    "reference": item.reference,
                    "absolute_difference": item.absolute_difference,
                    "relative_difference": item.relative_difference,
                    "passed": item.passed,
                }
                for item in self.comparisons
            ],
        }


def validate_profile_against_reference(
    profile: QuantileEarningsProfile,
    reference: Mapping[int, float],
    *,
    reference_implementation: str,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> ProfileValidationReport:
    """Validate every profile age against an independently generated fixed fixture."""
    if not reference_implementation.strip():
        raise ValueError("reference implementation cannot be empty")
    if any(not isfinite(value) or value < 0 for value in (absolute_tolerance, relative_tolerance)):
        raise ValueError("profile tolerances must be finite and nonnegative")
    profile_ages = tuple(point.age for point in profile.points)
    if tuple(sorted(reference)) != profile_ages:
        raise ValueError("reference ages must exactly match the profile")
    comparisons = []
    for point in profile.points:
        reference_value = reference[point.age]
        if not isfinite(reference_value) or reference_value < 0:
            raise ValueError("reference earnings must be finite and nonnegative")
        absolute = abs(point.earnings - reference_value)
        relative = None if reference_value == 0 else absolute / abs(reference_value)
        passed = absolute <= absolute_tolerance and (
            reference_value == 0 or (relative is not None and relative <= relative_tolerance)
        )
        comparisons.append(
            ProfilePointComparison(
                point.age, point.earnings, reference_value, absolute, relative, passed
            )
        )
    return ProfileValidationReport(
        profile.group,
        profile.definition,
        profile.coefficient_hash,
        reference_implementation,
        absolute_tolerance,
        relative_tolerance,
        tuple(comparisons),
    )


@dataclass(frozen=True)
class QuantileCashFlow:
    """Incremental cash flow associated with equivalent distributional positions."""

    definition: QuantileDefinition
    series: CashFlowSeries
    option_profile_hash: str
    counterfactual_profile_hash: str

    def __post_init__(self) -> None:
        if not self.option_profile_hash.strip() or not self.counterfactual_profile_hash.strip():
            raise ValueError("quantile cash flows require both profile hashes")


@dataclass(frozen=True)
class QuantileIRRResult:
    definition: QuantileDefinition
    internal_rate_of_return: IRRResult
    cash_flow: CashFlowSeries
    cash_flow_hash: str
    option_profile_hash: str
    counterfactual_profile_hash: str

    def as_dict(self) -> dict[str, object]:
        result = self.internal_rate_of_return
        return {
            "definition": self.definition.as_dict(),
            "irr": {
                "status": result.status.value,
                "roots": list(result.roots),
                "lower_rate": result.lower_rate,
                "upper_rate": result.upper_rate,
            },
            "cash_flow": {
                "name": self.cash_flow.name,
                "basis": {
                    "mode": self.cash_flow.basis.mode.value,
                    "dollar_year": self.cash_flow.basis.dollar_year,
                },
                "points": [
                    {"age": point.age, "amount": point.amount} for point in self.cash_flow.points
                ],
            },
            "cash_flow_hash": self.cash_flow_hash,
            "option_profile_hash": self.option_profile_hash,
            "counterfactual_profile_hash": self.counterfactual_profile_hash,
        }


def _cash_flow_hash(series: CashFlowSeries) -> str:
    payload = {
        "name": series.name,
        "basis": {
            "mode": series.basis.mode.value,
            "dollar_year": series.basis.dollar_year,
        },
        "points": [{"age": point.age, "amount": point.amount} for point in series.points],
    }
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def calculate_quantile_irrs(
    cash_flows: Sequence[QuantileCashFlow],
) -> tuple[QuantileIRRResult, ...]:
    """Calculate median and nonmedian IRRs without treating deciles as probabilities."""
    if not cash_flows:
        raise ValueError("at least one quantile cash flow is required")
    quantiles = [item.definition.quantile for item in cash_flows]
    if len(quantiles) != len(set(quantiles)):
        raise ValueError("quantile cash-flow definitions must be unique")
    return tuple(
        QuantileIRRResult(
            item.definition,
            internal_rate_of_return(item.series),
            item.series,
            _cash_flow_hash(item.series),
            item.option_profile_hash,
            item.counterfactual_profile_hash,
        )
        for item in sorted(cash_flows, key=lambda value: value.definition.quantile)
    )
