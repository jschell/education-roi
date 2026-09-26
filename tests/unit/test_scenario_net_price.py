"""Scenario net-price evidence is contextual and population gated."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.ipeds.net_price import NetPriceBasis
from education_roi.ipeds.net_price_evidence import NetPriceEvidence
from education_roi.scenarios import (
    AttendanceBasis,
    DatasetPin,
    ScenarioDefinition,
    TuitionResidency,
    load_scenario_file,
)
from education_roi.scenarios.net_price_context import (
    ScenarioNetPriceContextError,
    review_scenario_net_price,
)

EXAMPLES = Path(__file__).parents[2] / "scenarios/examples"


def scenario_with_pin() -> ScenarioDefinition:
    original = load_scenario_file(EXAMPLES / "example-bachelors.yaml").scenario
    policy = original.data.model_copy(
        update={
            "pins": (
                *original.data.pins,
                DatasetPin(dataset="ipeds-net-price", release="2023-24-final"),
            ),
        }
    )
    return original.model_copy(update={"data": policy})


def observation() -> NetPriceEvidence:
    return NetPriceEvidence(
        status="OBSERVED",
        unitid=236948,
        basis=NetPriceBasis.PUBLIC_GRANT,
        source_field="NPIST2",
        average_net_price=11023,
        raw_average_net_price="11023",
        source_status="R",
        reason=None,
        release_id="2023-24-final",
        publication_status="final",
        aid_year="2022-23",
        data_artifact_id="data-id",
        dictionary_artifact_id="dictionary-id",
        transformation_version="ipeds-sfa2223-net-price-v1",
        table_sha256="a" * 64,
        manifest_sha256="b" * 64,
    )


def test_context_requires_matching_population_and_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = scenario_with_pin()
    calls = []

    def lookup(path: Path, unitid: int, basis: NetPriceBasis) -> NetPriceEvidence:
        calls.append((path, unitid, basis))
        return observation()

    monkeypatch.setattr(
        "education_roi.scenarios.net_price_context.resolve_net_price_evidence", lookup
    )
    table = tmp_path / "table.parquet"
    context = review_scenario_net_price(scenario, table, NetPriceBasis.PUBLIC_GRANT)
    assert calls == [(table, 236948, NetPriceBasis.PUBLIC_GRANT)]
    assert context.cash_flow_use == "CONTEXT_ONLY"
    assert context.configuration_hash == scenario.configuration_hash
    assert context.evidence.average_net_price == 11023
    assert scenario.costs.tuition_and_fees.status.value == "RESOLVE_FROM_DATA"
    assert scenario.costs.grants_and_scholarships.status.value == "RESOLVE_FROM_DATA"

    with pytest.raises(ScenarioNetPriceContextError, match="pin"):
        review_scenario_net_price(
            load_scenario_file(EXAMPLES / "example-bachelors.yaml").scenario,
            table,
            NetPriceBasis.PUBLIC_GRANT,
        )
    assert scenario.education is not None and scenario.education.institution is not None
    out_of_state = scenario.education.institution.model_copy(
        update={"tuition_residency": TuitionResidency.OUT_OF_STATE}
    )
    education = scenario.education.model_copy(update={"institution": out_of_state})
    with pytest.raises(ScenarioNetPriceContextError, match="in-state"):
        review_scenario_net_price(
            scenario.model_copy(update={"education": education}), table, NetPriceBasis.PUBLIC_GRANT
        )
    part_time = scenario.education.institution.model_copy(
        update={"attendance_basis": AttendanceBasis.PART_TIME}
    )
    education = scenario.education.model_copy(update={"institution": part_time})
    with pytest.raises(ScenarioNetPriceContextError, match="full-time"):
        review_scenario_net_price(
            scenario.model_copy(update={"education": education}), table, NetPriceBasis.OTHER_GRANT
        )
    assert len(calls) == 1


def test_cli_returns_context_without_cost_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "education_roi.scenarios.net_price_context.resolve_net_price_evidence",
        lambda path, unitid, basis: observation(),
    )
    scenario = scenario_with_pin()
    original = load_scenario_file(EXAMPLES / "example-bachelors.yaml")
    scenario_file = tmp_path / "education.json"
    scenario_file.write_text(original.model_copy(update={"scenario": scenario}).model_dump_json())
    table = tmp_path / "table.parquet"
    table.write_bytes(b"fixture")
    cli = CliRunner().invoke(
        app,
        [
            "scenario",
            "review-net-price",
            str(EXAMPLES / "workforce-high-school.yaml"),
            str(scenario_file),
            "--scenario-id",
            "example-bachelors",
            "--table",
            str(table),
            "--basis",
            "public_in_state_grant",
        ],
    )
    assert cli.exit_code == 0, cli.stdout
    result = json.loads(cli.stdout)
    assert result["cash_flow_use"] == "CONTEXT_ONLY"
    assert result["evidence"]["average_net_price"] == 11023
    assert result["institution_unitid"] == 236948
