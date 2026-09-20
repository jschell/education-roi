import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.ipeds import IPEDS_CHARGES_DATASET
from education_roi.provenance.models import ApprovalState
from education_roi.provenance.store import ArtifactStore, Registry

runner = CliRunner()
EXAMPLES = Path(__file__).parents[2] / "scenarios" / "examples"


def make_ipeds_zip(path: Path, body: str) -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("IC2023_AY.csv", body)
    return path


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
    vintage: 2023-24-provisional
    artifact_id: ipeds-sha256
    transformation_ids: [select-unitid]
  example-bachelors.costs.books_and_supplies:
    value: 900
    source: ipeds
    vintage: 2023-24-provisional
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


@pytest.mark.integration
def test_scenario_resolve_ipeds_uses_validated_registry_artifact(tmp_path: Path) -> None:
    source = make_ipeds_zip(
        tmp_path / "charges.zip",
        "UNITID,CHG2AY3,CHG4AY3,XCHG2AY3,XCHG4AY3\n236948,12000,900,R,I\n",
    )
    registry = Registry(tmp_path / "data/manifests/registry.sqlite")
    registry.add_dataset(IPEDS_CHARGES_DATASET)
    manifest = ArtifactStore(tmp_path / "data/raw", registry).register(
        source,
        IPEDS_CHARGES_DATASET,
        release="2023-24-provisional",
        source_url="https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip",
        final_url="https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip",
        publication_status="provisional",
        schema_version="ipeds-ic-ay-v1",
    )
    registry.transition(manifest.artifact_id, ApprovalState.VALIDATED, "integration fixture")

    result = runner.invoke(
        app,
        [
            "scenario",
            "resolve-ipeds",
            str(EXAMPLES / "example-bachelors.yaml"),
            str(EXAMPLES / "workforce-high-school.yaml"),
            "--root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    bachelors = payload["scenarios"][1]
    tuition = next(item for item in bachelors["values"] if item["path"] == "costs.tuition_and_fees")
    books = next(item for item in bachelors["values"] if item["path"] == "costs.books_and_supplies")
    grants = next(
        item for item in bachelors["values"] if item["path"] == "costs.grants_and_scholarships"
    )
    assert tuition["value"] == 12000
    assert tuition["artifact_id"] == manifest.artifact_id
    assert tuition["source_metadata"] == ["XCHG2AY3=R"]
    assert books["value"] == 900
    assert grants["status"] == "INSUFFICIENT_DATA"


@pytest.mark.integration
def test_scenario_resolve_ipeds_requires_existing_registry(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "scenario",
            "resolve-ipeds",
            str(EXAMPLES / "example-bachelors.yaml"),
            str(EXAMPLES / "workforce-high-school.yaml"),
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "INVALID"
    assert not (tmp_path / "data/manifests/registry.sqlite").exists()


@pytest.mark.integration
def test_scenario_analyze_cli_is_deterministic_for_complete_fixtures(tmp_path: Path) -> None:
    workforce = EXAMPLES / "workforce-high-school.yaml"
    bachelors = tmp_path / "bachelors.yaml"
    text = (EXAMPLES / "example-bachelors.yaml").read_text(encoding="utf-8")
    text = text.replace(
        "annual_interest_rate: {status: INSUFFICIENT_DATA, source: federal-student-aid}",
        "annual_interest_rate: {status: PROVIDED, value: 0.05, source: test-assumption}",
    ).replace(
        "origination_fee_rate: {status: INSUFFICIENT_DATA, source: federal-student-aid}",
        "origination_fee_rate: {status: PROVIDED, value: 0.01, source: test-assumption}",
    )
    bachelors.write_text(text, encoding="utf-8")
    values = tmp_path / "values.yaml"
    values.write_text(
        yaml.safe_dump(
            {
                "values": {
                    "example-bachelors.costs.tuition_and_fees": {
                        "value": 12000,
                        "source": "ipeds",
                        "vintage": "2023-24-provisional",
                        "artifact_id": "ipeds-sha",
                    },
                    "example-bachelors.costs.books_and_supplies": {
                        "value": 1000,
                        "source": "ipeds",
                        "vintage": "2023-24-provisional",
                        "artifact_id": "ipeds-sha",
                    },
                    "example-bachelors.costs.grants_and_scholarships": {
                        "value": 4000,
                        "source": "college-scorecard",
                        "vintage": "2024-10",
                        "artifact_id": "scorecard-sha",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    ages = list(range(18, 66))
    baseline = {age: 30000 + 1000 * (age - 18) for age in ages}
    graduate = {age: 0 if age < 22 else 70000 + 2000 * (age - 22) for age in ages}
    earnings = tmp_path / "earnings.yaml"
    earnings.write_text(
        yaml.safe_dump(
            {
                "profiles": {
                    "workforce-high-school": {
                        "base": {
                            "source": "acs-pums",
                            "vintage": "2024-5yr",
                            "artifact_id": "acs-workforce-sha",
                            "transformation_ids": ["wa-hs-p50"],
                            "quantile": 0.5,
                            "enrollment_years": 0,
                            "earnings_by_age": baseline,
                        }
                    },
                    "example-bachelors": {
                        "graduate_on_time": {
                            "source": "acs-pums",
                            "vintage": "2024-5yr",
                            "artifact_id": "acs-degree-sha",
                            "transformation_ids": ["wa-cs-p50"],
                            "quantile": 0.5,
                            "enrollment_years": 4,
                            "earnings_by_age": graduate,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    arguments = [
        "scenario",
        "analyze",
        str(bachelors),
        str(workforce),
        "--scenario-id",
        "example-bachelors",
        "--fixture-values",
        str(values),
        "--earnings-fixture",
        str(earnings),
    ]
    first = runner.invoke(app, arguments)
    second = runner.invoke(app, arguments)
    assert first.exit_code == 0, first.stdout
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["status"] == "AVAILABLE"
    assert payload["perspective"] == "conditional_graduate"
    assert payload["result"]["status"] == "AVAILABLE"
    assert len(payload["annual_cash_flow"]) == 48
    assert len(payload["analysis_hash"]) == 64
