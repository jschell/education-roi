"""Versioned, unresolved scenario definitions with explicit data states."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from json import dumps
from math import isclose
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ScenarioKind(StrEnum):
    WORKFORCE = "workforce"
    EDUCATION = "education"


class Credential(StrEnum):
    CERTIFICATE = "certificate"
    APPRENTICESHIP = "apprenticeship"
    ASSOCIATE = "associate"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    DOCTORATE = "doctorate"


class ValueStatus(StrEnum):
    PROVIDED = "PROVIDED"
    RESOLVE_FROM_DATA = "RESOLVE_FROM_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ValueSpec(StrictModel):
    """A value is supplied, delegated to a named dataset, or explicitly unavailable."""

    status: ValueStatus
    value: float | None = None
    source: str = Field(min_length=1)
    vintage: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.status is ValueStatus.PROVIDED:
            if self.value is None:
                raise ValueError("PROVIDED values require an explicit value, including zero")
        elif self.value is not None:
            raise ValueError("unresolved or insufficient values cannot contain a numeric value")
        if self.status is ValueStatus.RESOLVE_FROM_DATA and not self.vintage:
            raise ValueError("RESOLVE_FROM_DATA values require a pinned vintage")
        return self


class MoneyBasisConfig(StrictModel):
    mode: Literal["real", "nominal"]
    dollar_year: int | None = Field(default=None, ge=1900)

    @model_validator(mode="after")
    def validate_basis(self) -> Self:
        if self.mode == "real" and self.dollar_year is None:
            raise ValueError("real money basis requires dollar_year")
        if self.mode == "nominal" and self.dollar_year is not None:
            raise ValueError("nominal money basis cannot declare dollar_year")
        return self


class InstitutionConfig(StrictModel):
    unitid: int = Field(gt=0)
    name: str | None = None


class ProgramConfig(StrictModel):
    cip: str = Field(pattern=r"^\d{2}(?:\.\d{2,4})?$")
    cip_version: str = Field(min_length=1)
    name: str | None = None


class CompletionConfig(StrictModel):
    graduate_on_time: ValueSpec
    graduate_late: ValueSpec
    transfer: ValueSpec
    leave_without_credential: ValueSpec

    @model_validator(mode="after")
    def validate_probabilities(self) -> Self:
        values = (
            self.graduate_on_time,
            self.graduate_late,
            self.transfer,
            self.leave_without_credential,
        )
        provided = [item.value for item in values if item.status is ValueStatus.PROVIDED]
        if any(value is None or not 0 <= value <= 1 for value in provided):
            raise ValueError("provided completion probabilities must be between zero and one")
        if len(provided) == len(values):
            total = sum(value for value in provided if value is not None)
            if not isclose(total, 1.0, abs_tol=1e-9):
                raise ValueError("provided completion probabilities must sum to one")
        return self


class EducationConfig(StrictModel):
    credential: Credential
    expected_duration_years: float = Field(gt=0, le=12)
    institution: InstitutionConfig | None = None
    program: ProgramConfig | None = None
    completion: CompletionConfig

    @model_validator(mode="after")
    def validate_duration(self) -> Self:
        bounds = {
            Credential.CERTIFICATE: (0.25, 4),
            Credential.APPRENTICESHIP: (1, 8),
            Credential.ASSOCIATE: (1, 4),
            Credential.BACHELORS: (2, 8),
            Credential.MASTERS: (1, 5),
            Credential.DOCTORATE: (2, 12),
        }
        lower, upper = bounds[self.credential]
        if not lower <= self.expected_duration_years <= upper:
            raise ValueError(
                f"{self.credential.value} duration must be between {lower} and {upper} years"
            )
        return self


class WorkforceConfig(StrictModel):
    entry_age: int = Field(ge=14, le=80)
    occupation_soc: str | None = Field(default=None, pattern=r"^\d{2}-\d{4}$")
    soc_version: str | None = None

    @model_validator(mode="after")
    def validate_soc(self) -> Self:
        if (self.occupation_soc is None) != (self.soc_version is None):
            raise ValueError("SOC code and version must be supplied together")
        return self


class CostConfig(StrictModel):
    tuition_and_fees: ValueSpec
    books_and_supplies: ValueSpec
    incremental_living_cost: ValueSpec
    grants_and_scholarships: ValueSpec

    @model_validator(mode="after")
    def validate_costs(self) -> Self:
        values = (
            self.tuition_and_fees,
            self.books_and_supplies,
            self.incremental_living_cost,
            self.grants_and_scholarships,
        )
        if any(
            item.status is ValueStatus.PROVIDED and item.value is not None and item.value < 0
            for item in values
        ):
            raise ValueError("provided cost values cannot be negative")
        return self


class FinancingConfig(StrictModel):
    family_contribution: ValueSpec
    student_contribution: ValueSpec
    debt_principal: ValueSpec
    annual_interest_rate: ValueSpec
    origination_fee_rate: ValueSpec
    repayment_years: ValueSpec

    @model_validator(mode="after")
    def validate_financing(self) -> Self:
        values = (
            self.family_contribution,
            self.student_contribution,
            self.debt_principal,
            self.annual_interest_rate,
            self.origination_fee_rate,
            self.repayment_years,
        )
        if any(
            item.status is ValueStatus.PROVIDED and item.value is not None and item.value < 0
            for item in values
        ):
            raise ValueError("provided financing values cannot be negative")
        return self


class EarningsConfig(StrictModel):
    source: str = Field(min_length=1)
    vintage: str = Field(min_length=1)
    quantiles: tuple[float, ...]
    geography: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_quantiles(self) -> Self:
        if not self.quantiles:
            raise ValueError("at least one earnings quantile is required")
        if self.quantiles != tuple(sorted(set(self.quantiles))):
            raise ValueError("earnings quantiles must be unique and ordered")
        if any(not 0 < value < 1 for value in self.quantiles):
            raise ValueError("earnings quantiles must be between zero and one")
        return self


class GraduateSchoolMode(StrEnum):
    NONE = "none"
    OPTIONAL = "optional"
    MANDATORY = "mandatory"


class GraduateSchoolConfig(StrictModel):
    mode: GraduateSchoolMode
    scenario: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if self.mode is GraduateSchoolMode.NONE and self.scenario is not None:
            raise ValueError("graduate-school mode none cannot reference a scenario")
        if self.mode is not GraduateSchoolMode.NONE and self.scenario is None:
            raise ValueError("optional or mandatory graduate school requires a scenario reference")
        return self


class AssumptionConfig(StrictModel):
    money_basis: MoneyBasisConfig
    selection_adjustment: float = Field(ge=0, le=1)
    real_discount_rate: float = Field(gt=-1)
    real_wage_growth: float
    start_age: int = Field(ge=0)
    terminal_age: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_horizon(self) -> Self:
        if self.terminal_age <= self.start_age:
            raise ValueError("terminal_age must be greater than start_age")
        return self


class DatasetSelectionPolicy(StrEnum):
    PINNED = "pinned"
    LATEST_VALIDATED_FINAL = "latest_validated_final"


class DatasetPin(StrictModel):
    dataset: str = Field(min_length=1)
    release: str = Field(min_length=1)


class DataPolicyConfig(StrictModel):
    policy: DatasetSelectionPolicy
    pins: tuple[DatasetPin, ...] = ()

    @model_validator(mode="after")
    def validate_pins(self) -> Self:
        if self.policy is DatasetSelectionPolicy.PINNED and not self.pins:
            raise ValueError("pinned data policy requires at least one dataset pin")
        names = tuple(item.dataset for item in self.pins)
        if len(names) != len(set(names)):
            raise ValueError("dataset pins must be unique")
        return self


class ScenarioDefinition(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    kind: ScenarioKind
    education: EducationConfig | None = None
    workforce: WorkforceConfig | None = None
    costs: CostConfig
    financing: FinancingConfig
    earnings: EarningsConfig
    counterfactual: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    graduate_school: GraduateSchoolConfig
    assumptions: AssumptionConfig
    data: DataPolicyConfig

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        if self.kind is ScenarioKind.EDUCATION:
            if self.education is None or self.workforce is not None:
                raise ValueError("education scenario requires education and forbids workforce")
            if self.counterfactual is None:
                raise ValueError("education scenario requires an explicit counterfactual")
        elif self.workforce is None or self.education is not None:
            raise ValueError("workforce scenario requires workforce and forbids education")
        return self

    def references(self) -> tuple[str, ...]:
        values = [self.counterfactual]
        values.append(self.graduate_school.scenario)
        return tuple(value for value in values if value is not None)

    @property
    def configuration_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=False)
        return sha256(
            dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


class ScenarioDocument(StrictModel):
    schema_version: Literal["1.0"]
    scenario: ScenarioDefinition


@dataclass(frozen=True)
class ResolvedScenarioGraph:
    schema_version: str
    topological_order: tuple[str, ...]
    scenarios: tuple[ScenarioDefinition, ...]
    graph_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "topological_order": list(self.topological_order),
            "graph_hash": self.graph_hash,
            "scenarios": [
                {"id": item.id, "configuration_hash": item.configuration_hash}
                for item in self.scenarios
            ],
        }
