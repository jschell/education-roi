"""Translate resolved scenarios into auditable annual and incremental cash flows."""

from enum import StrEnum
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Self

import yaml
from pydantic import Field, model_validator

from education_roi.cashflow import (
    AnnualCashFlow,
    BranchResult,
    BranchStatus,
    ComputationProvenance,
    DollarMode,
    FinancialResult,
    LoanTerms,
    MoneyBasis,
    ReturnPerspective,
    ScenarioCashFlow,
    build_loan_schedule,
    calculate_financial_result,
    incremental_cash_flow,
)
from education_roi.scenarios.models import ResolvedScenarioGraph, ScenarioDefinition, StrictModel
from education_roi.scenarios.resolution import (
    ResolutionStatus,
    ResolvedConfigurationGraph,
    ResolvedScenario,
)


class ScenarioAnalysisError(ValueError):
    pass


class OutcomeName(StrEnum):
    BASE = "base"
    GRADUATE_ON_TIME = "graduate_on_time"
    GRADUATE_LATE = "graduate_late"
    TRANSFER = "transfer"
    LEAVE_WITHOUT_CREDENTIAL = "leave_without_credential"


class EarningsProfile(StrictModel):
    source: str = Field(min_length=1)
    vintage: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    transformation_ids: tuple[str, ...] = ()
    quantile: float = Field(gt=0, lt=1)
    enrollment_years: int = Field(ge=0, le=20)
    earnings_by_age: dict[int, float]

    @model_validator(mode="after")
    def validate_earnings(self) -> Self:
        if not self.earnings_by_age:
            raise ValueError("earnings profile cannot be empty")
        if any(age < 0 or value < 0 for age, value in self.earnings_by_age.items()):
            raise ValueError("earnings ages and amounts cannot be negative")
        return self


class EarningsFixture(StrictModel):
    profiles: dict[str, dict[OutcomeName, EarningsProfile]]

    @classmethod
    def from_file(cls, path: Path) -> Self:
        try:
            text = path.read_text(encoding="utf-8")
            payload = loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
            return cls.model_validate(payload)
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise ScenarioAnalysisError(f"invalid earnings fixture {path}: {error}") from error


class AnalysisStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ScenarioAnalysis(StrictModel):
    scenario_id: str
    counterfactual_id: str | None
    perspective: ReturnPerspective
    status: AnalysisStatus
    reason: str | None = None
    annual_cash_flow: tuple[dict[str, float | int], ...] = ()
    incremental_cash_flow: tuple[dict[str, float | int], ...] = ()
    result: dict[str, object] | None = None
    analysis_hash: str

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def _values(resolved: ResolvedScenario) -> dict[str, float]:
    missing = [
        item.path for item in resolved.values if item.status is ResolutionStatus.INSUFFICIENT_DATA
    ]
    if missing:
        raise ScenarioAnalysisError("unresolved required values: " + ", ".join(sorted(missing)))
    return {item.path: item.value for item in resolved.values if item.value is not None}


def _basis(scenario: ScenarioDefinition) -> MoneyBasis:
    config = scenario.assumptions.money_basis
    return MoneyBasis(DollarMode(config.mode), config.dollar_year)


def _validate_profile(scenario: ScenarioDefinition, profile: EarningsProfile) -> None:
    if profile.source != scenario.earnings.source or profile.vintage != scenario.earnings.vintage:
        raise ScenarioAnalysisError(
            f"earnings profile returned {profile.source} {profile.vintage}; expected "
            f"{scenario.earnings.source} {scenario.earnings.vintage}"
        )
    if profile.quantile not in scenario.earnings.quantiles:
        raise ScenarioAnalysisError(f"earnings quantile {profile.quantile} was not requested")
    expected = set(range(scenario.assumptions.start_age, scenario.assumptions.terminal_age + 1))
    if set(profile.earnings_by_age) != expected:
        raise ScenarioAnalysisError("earnings profile must cover every age in the scenario horizon")


def _scenario_cash_flow(
    scenario: ScenarioDefinition,
    resolved: ResolvedScenario,
    profile: EarningsProfile,
) -> ScenarioCashFlow:
    _validate_profile(scenario, profile)
    if scenario.assumptions.real_wage_growth <= -1:
        raise ScenarioAnalysisError("real_wage_growth must be greater than -1")
    values = _values(resolved)
    tuition = values["costs.tuition_and_fees"]
    books = values["costs.books_and_supplies"]
    living = values["costs.incremental_living_cost"]
    grants = values["costs.grants_and_scholarships"]
    debt = values["financing.debt_principal"]
    interest = values["financing.annual_interest_rate"]
    fee = values["financing.origination_fee_rate"]
    repayment_years_value = values["financing.repayment_years"]
    if not repayment_years_value.is_integer():
        raise ScenarioAnalysisError("financing.repayment_years must be an integer")
    repayment_years = int(repayment_years_value)
    if debt > 0 and repayment_years <= 0:
        raise ScenarioAnalysisError("positive debt requires positive repayment years")
    financing: dict[int, float] = {}
    if debt > 0:
        schedule = build_loan_schedule(
            LoanTerms(
                name=f"{scenario.id}-loan",
                amount_borrowed=debt,
                annual_interest_rate=interest,
                repayment_years=repayment_years,
                origination_fee_rate=fee,
                enrollment_years=profile.enrollment_years,
            )
        )
        start = scenario.assumptions.start_age + profile.enrollment_years
        financing[scenario.assumptions.start_age] = schedule.terms.origination_fee
        for index, cost in enumerate(schedule.financing_costs_by_year()):
            financing[start + index] = financing.get(start + index, 0) + cost

    annual = []
    for age in range(scenario.assumptions.start_age, scenario.assumptions.terminal_age + 1):
        enrolled = age < scenario.assumptions.start_age + profile.enrollment_years
        annual.append(
            AnnualCashFlow(
                age=age,
                earnings=profile.earnings_by_age[age]
                * (1 + scenario.assumptions.real_wage_growth)
                ** (age - scenario.assumptions.start_age),
                direct_education_cost=tuition + books if enrolled else 0,
                incremental_living_cost=living if enrolled else 0,
                grant_aid=grants if enrolled else 0,
                financing_cost=financing.get(age, 0),
            )
        )
    return ScenarioCashFlow(scenario.id, _basis(scenario), tuple(annual))


def _weighted_scenario(
    scenario: ScenarioDefinition,
    resolved: ResolvedScenario,
    profiles: dict[OutcomeName, EarningsProfile],
    perspective: ReturnPerspective,
) -> tuple[ScenarioCashFlow, tuple[EarningsProfile, ...]]:
    if scenario.education is None:
        profile = profiles.get(OutcomeName.BASE)
        if profile is None:
            raise ScenarioAnalysisError(f"{scenario.id} requires a base earnings profile")
        return _scenario_cash_flow(scenario, resolved, profile), (profile,)
    if perspective is ReturnPerspective.CONDITIONAL_GRADUATE:
        profile = profiles.get(OutcomeName.GRADUATE_ON_TIME)
        if profile is None:
            raise ScenarioAnalysisError(f"{scenario.id} requires graduate_on_time earnings")
        if profile.enrollment_years != scenario.education.expected_duration_years:
            raise ScenarioAnalysisError(
                "graduate_on_time enrollment years must equal expected duration"
            )
        return _scenario_cash_flow(scenario, resolved, profile), (profile,)

    values = _values(resolved)
    probabilities = {
        OutcomeName.GRADUATE_ON_TIME: values["education.completion.graduate_on_time"],
        OutcomeName.GRADUATE_LATE: values["education.completion.graduate_late"],
        OutcomeName.TRANSFER: values["education.completion.transfer"],
        OutcomeName.LEAVE_WITHOUT_CREDENTIAL: values[
            "education.completion.leave_without_credential"
        ],
    }
    branches: list[tuple[float, ScenarioCashFlow, EarningsProfile]] = []
    for outcome, probability in probabilities.items():
        if probability == 0:
            continue
        profile = profiles.get(outcome)
        if profile is None:
            raise ScenarioAnalysisError(
                f"{scenario.id} outcome {outcome.value} has probability {probability} "
                "but no earnings/timing profile"
            )
        if (
            outcome is OutcomeName.GRADUATE_ON_TIME
            and profile.enrollment_years != scenario.education.expected_duration_years
        ):
            raise ScenarioAnalysisError(
                "graduate_on_time enrollment years must equal expected duration"
            )
        branches.append((probability, _scenario_cash_flow(scenario, resolved, profile), profile))
    first = branches[0][1]
    annual_items: list[AnnualCashFlow] = []
    for index, template in enumerate(first.annual):
        items = tuple((probability, branch.annual[index]) for probability, branch, _ in branches)
        annual_items.append(
            AnnualCashFlow(
                age=template.age,
                earnings=sum(probability * item.earnings for probability, item in items),
                direct_education_cost=sum(
                    probability * item.direct_education_cost for probability, item in items
                ),
                incremental_living_cost=sum(
                    probability * item.incremental_living_cost for probability, item in items
                ),
                grant_aid=sum(probability * item.grant_aid for probability, item in items),
                financing_cost=sum(
                    probability * item.financing_cost for probability, item in items
                ),
            )
        )
    annual = tuple(annual_items)
    return ScenarioCashFlow(f"{scenario.id}-enrollment", first.basis, annual), tuple(
        profile for _, _, profile in branches
    )


def _apply_selection_adjustment(
    option: ScenarioCashFlow, counterfactual: ScenarioCashFlow, adjustment: float
) -> ScenarioCashFlow:
    return ScenarioCashFlow(
        option.name,
        option.basis,
        tuple(
            AnnualCashFlow(
                age=item.age,
                earnings=item.earnings - adjustment * (item.earnings - counter.earnings),
                direct_education_cost=item.direct_education_cost,
                incremental_living_cost=item.incremental_living_cost,
                grant_aid=item.grant_aid,
                financing_cost=item.financing_cost,
            )
            for item, counter in zip(option.annual, counterfactual.annual, strict=True)
        ),
    )


def _insufficient(
    scenario_id: str, counterfactual_id: str | None, perspective: ReturnPerspective, reason: str
) -> ScenarioAnalysis:
    payload = {
        "scenario_id": scenario_id,
        "counterfactual_id": counterfactual_id,
        "perspective": perspective.value,
        "status": AnalysisStatus.INSUFFICIENT_DATA.value,
        "reason": reason,
    }
    digest = sha256(dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ScenarioAnalysis(
        scenario_id=scenario_id,
        counterfactual_id=counterfactual_id,
        perspective=perspective,
        status=AnalysisStatus.INSUFFICIENT_DATA,
        reason=reason,
        analysis_hash=digest,
    )


def analyze_scenario(
    source_graph: ResolvedScenarioGraph,
    resolved_graph: ResolvedConfigurationGraph,
    fixture: EarningsFixture,
    scenario_id: str,
    perspective: ReturnPerspective,
) -> ScenarioAnalysis:
    definitions = {item.id: item for item in source_graph.scenarios}
    resolved = {item.id: item for item in resolved_graph.scenarios}
    scenario = definitions.get(scenario_id)
    if scenario is None:
        raise ScenarioAnalysisError(f"unknown scenario {scenario_id}")
    if scenario.counterfactual is None:
        return _insufficient(scenario.id, None, perspective, "scenario has no counterfactual")
    counterfactual = definitions[scenario.counterfactual]
    try:
        option, option_profiles = _weighted_scenario(
            scenario, resolved[scenario.id], fixture.profiles.get(scenario.id, {}), perspective
        )
        baseline, baseline_profiles = _weighted_scenario(
            counterfactual,
            resolved[counterfactual.id],
            fixture.profiles.get(counterfactual.id, {}),
            ReturnPerspective.CONDITIONAL_GRADUATE,
        )
        option = _apply_selection_adjustment(
            option, baseline, scenario.assumptions.selection_adjustment
        )
    except ScenarioAnalysisError as error:
        return _insufficient(scenario.id, counterfactual.id, perspective, str(error))
    incremental = incremental_cash_flow(option, baseline)
    resolved_inputs = (*resolved[scenario.id].values, *resolved[counterfactual.id].values)
    artifacts = tuple(
        sorted(
            {profile.artifact_id for profile in (*option_profiles, *baseline_profiles)}
            | {item.artifact_id for item in resolved_inputs if item.artifact_id is not None}
        )
    )
    transformations = tuple(
        sorted(
            {
                identifier
                for profile in (*option_profiles, *baseline_profiles)
                for identifier in profile.transformation_ids
            }
            | {identifier for item in resolved_inputs for identifier in item.transformation_ids}
        )
    )
    provenance = ComputationProvenance(
        model_name="scenario-analysis",
        model_version="0.1.0",
        dataset_artifact_ids=artifacts,
        transformation_ids=transformations,
        assumptions={
            "resolution_hash": resolved_graph.resolution_hash,
            "selection_adjustment": scenario.assumptions.selection_adjustment,
            "discount_rate": scenario.assumptions.real_discount_rate,
            "perspective": perspective.value,
        },
    )
    branch = BranchResult(
        perspective, BranchStatus.AVAILABLE, incremental, None, provenance.assumptions
    )
    result: FinancialResult = calculate_financial_result(
        branch,
        discount_rate=scenario.assumptions.real_discount_rate,
        lifetime_earnings=option.lifetime_earnings,
        provenance=provenance,
    )
    annual = tuple(
        {
            "age": item.age,
            "earnings": item.earnings,
            "direct_education_cost": item.direct_education_cost,
            "incremental_living_cost": item.incremental_living_cost,
            "grant_aid": item.grant_aid,
            "financing_cost": item.financing_cost,
            "net_amount": item.net_amount,
        }
        for item in option.annual
    )
    incremental_records = tuple(
        {"age": point.age, "amount": point.amount} for point in incremental.points
    )
    payload = {
        "scenario_id": scenario.id,
        "counterfactual_id": counterfactual.id,
        "perspective": perspective.value,
        "status": AnalysisStatus.AVAILABLE.value,
        "reason": None,
        "annual_cash_flow": annual,
        "incremental_cash_flow": incremental_records,
        "result": result.as_dict(),
    }
    digest = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return ScenarioAnalysis(
        scenario_id=scenario.id,
        counterfactual_id=counterfactual.id,
        perspective=perspective,
        status=AnalysisStatus.AVAILABLE,
        annual_cash_flow=annual,
        incremental_cash_flow=incremental_records,
        result=result.as_dict(),
        analysis_hash=digest,
    )
