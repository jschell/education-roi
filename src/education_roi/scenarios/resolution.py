"""Resolve scenario value specifications without hiding missing data or provenance."""

from collections.abc import Mapping
from enum import StrEnum
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Protocol, Self

import yaml
from pydantic import Field, model_validator

from education_roi.scenarios.models import (
    ResolvedScenarioGraph,
    ScenarioDefinition,
    StrictModel,
    ValueSpec,
    ValueStatus,
)


class ScenarioResolutionError(ValueError):
    """A provider result violates the scenario's explicit data contract."""


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ResolutionRequest(StrictModel):
    scenario_id: str
    path: str
    source: str
    vintage: str

    @property
    def key(self) -> str:
        return f"{self.scenario_id}.{self.path}"


class ProviderValue(StrictModel):
    value: float
    source: str = Field(min_length=1)
    vintage: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    transformation_ids: tuple[str, ...] = ()
    source_metadata: tuple[str, ...] = ()


class ValueProvider(Protocol):
    def resolve(self, request: ResolutionRequest) -> ProviderValue | None: ...


class FixtureValueProvider:
    """Explicit deterministic provider for tests; never performs live data access."""

    def __init__(self, values: Mapping[str, ProviderValue]) -> None:
        self._values = dict(values)

    def resolve(self, request: ResolutionRequest) -> ProviderValue | None:
        return self._values.get(request.key)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        try:
            text = path.read_text(encoding="utf-8")
            payload = loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
            if not isinstance(payload, dict) or not isinstance(payload.get("values"), dict):
                raise ValueError("fixture must contain a values mapping")
            values = {
                key: ProviderValue.model_validate(value) for key, value in payload["values"].items()
            }
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise ScenarioResolutionError(f"invalid resolution fixture {path}: {error}") from error
        return cls(values)


class ResolvedValue(StrictModel):
    path: str
    status: ResolutionStatus
    value: float | None = None
    source: str
    vintage: str | None = None
    artifact_id: str | None = None
    transformation_ids: tuple[str, ...] = ()
    source_metadata: tuple[str, ...] = ()
    input_status: ValueStatus
    note: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status is ResolutionStatus.RESOLVED and self.value is None:
            raise ValueError("resolved values require a numeric value")
        if self.status is ResolutionStatus.INSUFFICIENT_DATA and self.value is not None:
            raise ValueError("insufficient values cannot contain a numeric value")
        if (
            self.input_status is ValueStatus.RESOLVE_FROM_DATA
            and self.status is ResolutionStatus.RESOLVED
            and not self.artifact_id
        ):
            raise ValueError("data-resolved values require an artifact ID")
        return self


class DatasetReference(StrictModel):
    dataset: str
    release: str


class ResolvedScenario(StrictModel):
    id: str
    configuration_hash: str
    status: ResolutionStatus
    values: tuple[ResolvedValue, ...]
    dataset_references: tuple[DatasetReference, ...]
    resolution_hash: str

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class ResolvedConfigurationGraph(StrictModel):
    schema_version: str
    source_graph_hash: str
    topological_order: tuple[str, ...]
    status: ResolutionStatus
    scenarios: tuple[ResolvedScenario, ...]
    resolution_hash: str

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def _value_specs(scenario: ScenarioDefinition) -> tuple[tuple[str, ValueSpec], ...]:
    items: list[tuple[str, ValueSpec]] = []
    if scenario.education is not None:
        for name, value in scenario.education.completion:
            items.append((f"education.completion.{name}", value))
    for name, value in scenario.costs:
        items.append((f"costs.{name}", value))
    for name, value in scenario.financing:
        items.append((f"financing.{name}", value))
    return tuple(items)


def _resolve_value(
    scenario: ScenarioDefinition,
    path: str,
    specification: ValueSpec,
    pins: Mapping[str, str],
    provider: ValueProvider,
) -> ResolvedValue:
    if specification.status is ValueStatus.PROVIDED:
        return ResolvedValue(
            path=path,
            status=ResolutionStatus.RESOLVED,
            value=specification.value,
            source=specification.source,
            vintage=specification.vintage,
            input_status=specification.status,
            note=specification.note,
        )
    if specification.status is ValueStatus.INSUFFICIENT_DATA:
        return ResolvedValue(
            path=path,
            status=ResolutionStatus.INSUFFICIENT_DATA,
            source=specification.source,
            vintage=specification.vintage,
            input_status=specification.status,
            note=specification.note or "scenario declares insufficient data",
        )

    vintage = specification.vintage
    assert vintage is not None
    pinned = pins.get(specification.source)
    if pinned is None:
        raise ScenarioResolutionError(
            f"{scenario.id}.{path} requests unpinned dataset {specification.source}"
        )
    if pinned != vintage:
        raise ScenarioResolutionError(
            f"{scenario.id}.{path} requests {specification.source} {vintage}, "
            f"but scenario pins {pinned}"
        )
    request = ResolutionRequest(
        scenario_id=scenario.id, path=path, source=specification.source, vintage=vintage
    )
    result = provider.resolve(request)
    if result is None:
        return ResolvedValue(
            path=path,
            status=ResolutionStatus.INSUFFICIENT_DATA,
            source=specification.source,
            vintage=vintage,
            input_status=specification.status,
            note="provider returned no value for the exact pinned release",
        )
    if result.source != request.source or result.vintage != request.vintage:
        raise ScenarioResolutionError(
            f"provider returned {result.source} {result.vintage} for {request.key}; "
            f"expected {request.source} {request.vintage}"
        )
    return ResolvedValue(
        path=path,
        status=ResolutionStatus.RESOLVED,
        value=result.value,
        source=result.source,
        vintage=result.vintage,
        artifact_id=result.artifact_id,
        transformation_ids=result.transformation_ids,
        source_metadata=result.source_metadata,
        input_status=specification.status,
        note=specification.note,
    )


def resolve_configuration_graph(
    graph: ResolvedScenarioGraph, provider: ValueProvider
) -> ResolvedConfigurationGraph:
    """Resolve counterfactuals first and return an immutable, canonical configuration."""
    resolved_scenarios: list[ResolvedScenario] = []
    for scenario in graph.scenarios:
        pins = {pin.dataset: pin.release for pin in scenario.data.pins}
        earnings_pin = pins.get(scenario.earnings.source)
        if earnings_pin != scenario.earnings.vintage:
            raise ScenarioResolutionError(
                f"{scenario.id}.earnings requests {scenario.earnings.source} "
                f"{scenario.earnings.vintage}, but scenario pins {earnings_pin or 'nothing'}"
            )
        values = tuple(
            _resolve_value(scenario, path, value, pins, provider)
            for path, value in _value_specs(scenario)
        )
        references = tuple(
            DatasetReference(dataset=name, release=release)
            for name, release in sorted(pins.items())
        )
        status = (
            ResolutionStatus.INSUFFICIENT_DATA
            if any(item.status is ResolutionStatus.INSUFFICIENT_DATA for item in values)
            else ResolutionStatus.RESOLVED
        )
        payload = {
            "id": scenario.id,
            "configuration_hash": scenario.configuration_hash,
            "status": status.value,
            "values": [item.model_dump(mode="json") for item in values],
            "dataset_references": [item.model_dump(mode="json") for item in references],
        }
        resolution_hash = sha256(
            dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        resolved_scenarios.append(
            ResolvedScenario(
                id=scenario.id,
                configuration_hash=scenario.configuration_hash,
                status=status,
                values=values,
                dataset_references=references,
                resolution_hash=resolution_hash,
            )
        )

    overall_status = (
        ResolutionStatus.INSUFFICIENT_DATA
        if any(item.status is ResolutionStatus.INSUFFICIENT_DATA for item in resolved_scenarios)
        else ResolutionStatus.RESOLVED
    )
    graph_payload = {
        "schema_version": graph.schema_version,
        "source_graph_hash": graph.graph_hash,
        "topological_order": list(graph.topological_order),
        "status": overall_status.value,
        "scenario_hashes": [
            {"id": item.id, "resolution_hash": item.resolution_hash} for item in resolved_scenarios
        ],
    }
    resolution_hash = sha256(
        dumps(graph_payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return ResolvedConfigurationGraph(
        schema_version=graph.schema_version,
        source_graph_hash=graph.graph_hash,
        topological_order=graph.topological_order,
        status=overall_status,
        scenarios=tuple(resolved_scenarios),
        resolution_hash=resolution_hash,
    )
