"""Public education-cost substitutes with explicit precision and provenance."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from education_roi.cashflow import (
    CashFlowPoint,
    CashFlowSeries,
    DollarMode,
    IRRResult,
    internal_rate_of_return,
    net_present_value,
)


class CostLevel(StrEnum):
    SCENARIO = "SCENARIO"
    INSTITUTION_PROGRAM = "INSTITUTION_PROGRAM"
    INSTITUTION = "INSTITUTION"
    SECTOR_INCOME = "SECTOR_INCOME"
    SECTOR_CREDENTIAL = "SECTOR_CREDENTIAL"
    NATIONAL_CREDENTIAL = "NATIONAL_CREDENTIAL"


FALLBACK_ORDER = tuple(CostLevel)


class CostEvidence(StrEnum):
    EXACT_PUBLISHED_INPUT = "EXACT_PUBLISHED_INPUT"
    DIRECT = "DIRECT"
    PUBLIC_SUBSTITUTE = "PUBLIC_SUBSTITUTE"
    MODELED_ASSUMPTION = "MODELED_ASSUMPTION"


class CostSelectionStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class CostCase(StrEnum):
    LOW = "LOW"
    BASE = "BASE"
    HIGH = "HIGH"


@dataclass(frozen=True)
class CostComponents:
    """Total program costs; every component is required and zero must be explicit."""

    tuition_and_fees: float
    books_and_supplies: float
    incremental_living_cost: float
    grants_and_scholarships: float

    def __post_init__(self) -> None:
        values = (
            self.tuition_and_fees,
            self.books_and_supplies,
            self.incremental_living_cost,
            self.grants_and_scholarships,
        )
        if not all(isfinite(value) and value >= 0 for value in values):
            raise ValueError("cost components must be finite and nonnegative")

    @property
    def net_cost(self) -> float:
        return (
            self.tuition_and_fees
            + self.books_and_supplies
            + self.incremental_living_cost
            - self.grants_and_scholarships
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "tuition_and_fees": self.tuition_and_fees,
            "books_and_supplies": self.books_and_supplies,
            "incremental_living_cost": self.incremental_living_cost,
            "grants_and_scholarships": self.grants_and_scholarships,
            "net_cost": self.net_cost,
        }


@dataclass(frozen=True)
class CostProvenance:
    source: str
    publisher: str
    vintage: str
    dataset_hash: str
    source_url: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.source,
                self.publisher,
                self.vintage,
                self.dataset_hash,
                self.source_url,
            )
        ):
            raise ValueError("cost provenance fields cannot be empty")
        if not self.source_url.startswith("https://"):
            raise ValueError("cost provenance requires an HTTPS source URL")

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "publisher": self.publisher,
            "vintage": self.vintage,
            "dataset_hash": self.dataset_hash,
            "source_url": self.source_url,
        }


@dataclass(frozen=True)
class EducationCostEstimate:
    estimate_id: str
    requested_level: CostLevel
    actual_level: CostLevel
    evidence: CostEvidence
    dollar_year: int
    components: CostComponents
    provenance: CostProvenance
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.estimate_id.strip():
            raise ValueError("cost estimate ID cannot be empty")
        if self.dollar_year < 1900:
            raise ValueError("cost estimate dollar_year must be 1900 or later")
        if any(not item.strip() for item in self.assumptions):
            raise ValueError("cost assumptions cannot contain empty entries")
        is_exact_level = self.requested_level is self.actual_level
        if (
            self.evidence in {CostEvidence.DIRECT, CostEvidence.EXACT_PUBLISHED_INPUT}
            and not is_exact_level
        ):
            raise ValueError("direct or exact evidence cannot use a broader aggregation level")
        if not is_exact_level and self.evidence is not CostEvidence.PUBLIC_SUBSTITUTE:
            raise ValueError("fallback estimates must be labeled PUBLIC_SUBSTITUTE")

    @property
    def exact_input_eligible(self) -> bool:
        return self.evidence is CostEvidence.EXACT_PUBLISHED_INPUT

    def as_dict(self) -> dict[str, object]:
        return {
            "estimate_id": self.estimate_id,
            "requested_level": self.requested_level.value,
            "actual_level": self.actual_level.value,
            "evidence": self.evidence.value,
            "dollar_year": self.dollar_year,
            "components": self.components.as_dict(),
            "provenance": self.provenance.as_dict(),
            "assumptions": list(self.assumptions),
            "exact_input_eligible": self.exact_input_eligible,
        }


@dataclass(frozen=True)
class CostSelection:
    requested_level: CostLevel
    status: CostSelectionStatus
    estimate: EducationCostEstimate | None
    attempted_levels: tuple[CostLevel, ...]

    def __post_init__(self) -> None:
        if not self.attempted_levels:
            raise ValueError("cost selection must retain attempted levels")
        if (self.status is CostSelectionStatus.AVAILABLE) != (self.estimate is not None):
            raise ValueError("available cost selection requires an estimate")
        if self.estimate is not None and self.estimate.requested_level is not self.requested_level:
            raise ValueError("selected estimate requested level does not match the request")

    def as_dict(self) -> dict[str, object]:
        return {
            "requested_level": self.requested_level.value,
            "status": self.status.value,
            "attempted_levels": [item.value for item in self.attempted_levels],
            "estimate": None if self.estimate is None else self.estimate.as_dict(),
        }


def select_cost_estimate(
    requested_level: CostLevel, candidates: tuple[EducationCostEstimate, ...]
) -> CostSelection:
    """Select the narrowest available level, independently of caller ordering."""
    start = FALLBACK_ORDER.index(requested_level)
    attempted = FALLBACK_ORDER[start:]
    by_level: dict[CostLevel, list[EducationCostEstimate]] = {}
    for candidate in candidates:
        if candidate.requested_level is not requested_level:
            raise ValueError("all candidates must describe the requested aggregation level")
        if candidate.actual_level not in attempted:
            raise ValueError("candidate is more precise than the requested aggregation level")
        by_level.setdefault(candidate.actual_level, []).append(candidate)
    for level in attempted:
        matches = by_level.get(level, [])
        if len(matches) > 1:
            raise ValueError(f"ambiguous cost candidates at level {level.value}")
        if matches:
            return CostSelection(
                requested_level, CostSelectionStatus.AVAILABLE, matches[0], attempted
            )
    return CostSelection(requested_level, CostSelectionStatus.INSUFFICIENT_DATA, None, attempted)


@dataclass(frozen=True)
class CostSensitivitySet:
    low: EducationCostEstimate
    base: EducationCostEstimate
    high: EducationCostEstimate

    def __post_init__(self) -> None:
        estimates = (self.low, self.base, self.high)
        if len({item.requested_level for item in estimates}) != 1:
            raise ValueError("cost sensitivity cases must share a requested level")
        if len({item.dollar_year for item in estimates}) != 1:
            raise ValueError("cost sensitivity cases must share a dollar year")
        costs = tuple(item.components.net_cost for item in estimates)
        if costs != tuple(sorted(costs)):
            raise ValueError("cost sensitivity cases must satisfy low <= base <= high")

    def cases(self) -> tuple[tuple[CostCase, EducationCostEstimate], ...]:
        return (
            (CostCase.LOW, self.low),
            (CostCase.BASE, self.base),
            (CostCase.HIGH, self.high),
        )


@dataclass(frozen=True)
class CostSensitivityResult:
    case: CostCase
    estimate: EducationCostEstimate
    education_ages: tuple[int, ...]
    discount_rate: float
    net_present_value: float
    internal_rate_of_return: IRRResult

    def as_dict(self) -> dict[str, object]:
        return {
            "case": self.case.value,
            "estimate": self.estimate.as_dict(),
            "education_ages": list(self.education_ages),
            "discount_rate": self.discount_rate,
            "net_present_value": self.net_present_value,
            "internal_rate_of_return": {
                "status": self.internal_rate_of_return.status.value,
                "roots": list(self.internal_rate_of_return.roots),
                "lower_rate": self.internal_rate_of_return.lower_rate,
                "upper_rate": self.internal_rate_of_return.upper_rate,
            },
            "exact_input_eligible": self.estimate.exact_input_eligible,
        }


def evaluate_cost_sensitivity(
    base_incremental_cash_flow: CashFlowSeries,
    sensitivity: CostSensitivitySet,
    *,
    education_ages: tuple[int, ...],
    discount_rate: float,
) -> tuple[CostSensitivityResult, ...]:
    """Subtract total cost evenly across named enrollment ages and recalculate NPV and IRR."""
    if not education_ages or education_ages != tuple(sorted(set(education_ages))):
        raise ValueError("education ages must be nonempty, unique, and ordered")
    available_ages = {point.age for point in base_incremental_cash_flow.points}
    if any(age not in available_ages for age in education_ages):
        raise ValueError("education ages must be contained in the cash-flow series")
    if base_incremental_cash_flow.basis.mode is not DollarMode.REAL:
        raise ValueError("cost sensitivity currently requires a real-dollar cash flow")
    results = []
    for case, estimate in sensitivity.cases():
        if estimate.dollar_year != base_incremental_cash_flow.basis.dollar_year:
            raise ValueError("cost estimate and cash flow must use the same dollar year")
        annual_cost = estimate.components.net_cost / len(education_ages)
        series = CashFlowSeries(
            f"{base_incremental_cash_flow.name}; {case.value} cost",
            base_incremental_cash_flow.basis,
            tuple(
                CashFlowPoint(
                    point.age,
                    point.amount - annual_cost if point.age in education_ages else point.amount,
                )
                for point in base_incremental_cash_flow.points
            ),
        )
        results.append(
            CostSensitivityResult(
                case,
                estimate,
                education_ages,
                discount_rate,
                net_present_value(series, discount_rate),
                internal_rate_of_return(series),
            )
        )
    return tuple(results)
