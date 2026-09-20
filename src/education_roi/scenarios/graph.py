"""Deterministic scenario-reference resolution and compatibility checks."""

from hashlib import sha256
from json import dumps

from education_roi.scenarios.models import ResolvedScenarioGraph, ScenarioDocument


class ScenarioGraphError(ValueError):
    pass


def resolve_scenario_graph(
    documents: tuple[ScenarioDocument, ...],
) -> ResolvedScenarioGraph:
    if not documents:
        raise ScenarioGraphError("at least one scenario document is required")
    if len({item.schema_version for item in documents}) != 1:
        raise ScenarioGraphError("scenario documents must use the same schema version")
    by_id = {item.scenario.id: item.scenario for item in documents}
    if len(by_id) != len(documents):
        raise ScenarioGraphError("scenario IDs must be unique")
    for scenario in by_id.values():
        for reference in scenario.references():
            if reference not in by_id:
                raise ScenarioGraphError(
                    f"scenario {scenario.id} references missing scenario {reference}"
                )
            referenced = by_id[reference]
            if scenario.assumptions.money_basis != referenced.assumptions.money_basis:
                raise ScenarioGraphError(
                    f"scenario {scenario.id} and reference {reference} "
                    "have incompatible money bases"
                )

    state: dict[str, str] = {}
    order: list[str] = []
    trail: list[str] = []

    def visit(scenario_id: str) -> None:
        if state.get(scenario_id) == "done":
            return
        if state.get(scenario_id) == "visiting":
            start = trail.index(scenario_id)
            cycle = " -> ".join((*trail[start:], scenario_id))
            raise ScenarioGraphError(f"cyclic scenario reference: {cycle}")
        state[scenario_id] = "visiting"
        trail.append(scenario_id)
        for reference in sorted(by_id[scenario_id].references()):
            visit(reference)
        trail.pop()
        state[scenario_id] = "done"
        order.append(scenario_id)

    for scenario_id in sorted(by_id):
        visit(scenario_id)
    ordered = tuple(by_id[item] for item in order)
    payload = {
        "schema_version": documents[0].schema_version,
        "topological_order": order,
        "scenario_hashes": [
            {"id": item.id, "configuration_hash": item.configuration_hash} for item in ordered
        ],
    }
    graph_hash = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return ResolvedScenarioGraph(documents[0].schema_version, tuple(order), ordered, graph_hash)
