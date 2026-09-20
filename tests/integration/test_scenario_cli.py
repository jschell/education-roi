import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app

runner = CliRunner()
EXAMPLES = Path(__file__).parents[2] / "scenarios" / "examples"


@pytest.mark.integration
def test_scenario_cli_validates_graph_and_emits_stable_hash() -> None:
    arguments = [
        "scenario",
        "validate",
        str(EXAMPLES / "example-bachelors.yaml"),
        str(EXAMPLES / "workforce-high-school.yaml"),
    ]
    first = runner.invoke(app, arguments)
    reversed_arguments = arguments[:2] + list(reversed(arguments[2:]))
    second = runner.invoke(app, reversed_arguments)
    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload == second_payload
    assert first_payload["status"] == "VALID"
    assert first_payload["topological_order"] == [
        "workforce-high-school",
        "example-bachelors",
    ]
    assert len(first_payload["graph_hash"]) == 64


@pytest.mark.integration
def test_scenario_schema_command_emits_formal_schema() -> None:
    result = runner.invoke(app, ["scenario", "schema"])
    assert result.exit_code == 0, result.stdout
    schema = json.loads(result.stdout)
    assert schema["properties"]["schema_version"]["const"] == "1.0"


@pytest.mark.integration
def test_scenario_resolve_cli_emits_provenance_complete_configuration(tmp_path: Path) -> None:
    fixture = tmp_path / "values.yaml"
    fixture.write_text(
        """values:
  example-bachelors.costs.tuition_and_fees:
    value: 12000
    source: ipeds
    vintage: 2023-24-final
    artifact_id: ipeds-sha256
    transformation_ids: [select-unitid]
  example-bachelors.costs.books_and_supplies:
    value: 900
    source: ipeds
    vintage: 2023-24-final
    artifact_id: ipeds-sha256
  example-bachelors.costs.grants_and_scholarships:
    value: 5000
    source: college-scorecard
    vintage: 2024-10
    artifact_id: scorecard-sha256
""",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "scenario",
            "resolve",
            str(EXAMPLES / "example-bachelors.yaml"),
            str(EXAMPLES / "workforce-high-school.yaml"),
            "--fixture-values",
            str(fixture),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "INSUFFICIENT_DATA"
    assert payload["topological_order"] == ["workforce-high-school", "example-bachelors"]
    assert len(payload["resolution_hash"]) == 64
    tuition = next(
        item
        for item in payload["scenarios"][1]["values"]
        if item["path"] == "costs.tuition_and_fees"
    )
    assert tuition["artifact_id"] == "ipeds-sha256"
