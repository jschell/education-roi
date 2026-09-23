import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.ipeds import IPEDS_CHARGES_DATASET
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ApprovalState
from education_roi.provenance.store import ArtifactStore, Registry

runner = CliRunner()
PROJECT_ROOT = Path(__file__).parents[2]


def register_charges(root: Path) -> None:
    source = root / "charges.zip"
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "IC2023_AY.csv",
            "UNITID,CHG1AY3,CHG2AY3,CHG3AY3,CHG4AY3\n236948,8000,12000,30000,900\n",
        )
    registry = Registry(root / "data/manifests/registry.sqlite")
    registry.add_dataset(IPEDS_CHARGES_DATASET)
    manifest = ArtifactStore(root / "data/raw", registry).register(
        source,
        IPEDS_CHARGES_DATASET,
        release="2023-24-provisional",
        source_url="https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip",
        final_url="https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip",
        publication_status="provisional",
        schema_version="ipeds-ic-ay-v1",
    )
    registry.transition(manifest.artifact_id, ApprovalState.VALIDATED, "CLI fixture")


def test_build_charges_requires_nonfinal_opt_in_and_writes_lineage(tmp_path: Path) -> None:
    register_charges(tmp_path)
    catalog = PROJECT_ROOT / "data/manifests/ipeds-release-catalog.json"
    arguments = [
        "ipeds",
        "build-charges",
        "--catalog",
        str(catalog),
        "--release-id",
        "2023-24-provisional",
        "--root",
        str(tmp_path),
    ]
    refused = runner.invoke(app, arguments)
    assert refused.exit_code == 2
    assert json.loads(refused.stdout)["status"] == "INVALID"

    built = runner.invoke(app, [*arguments, "--allow-nonfinal"])
    assert built.exit_code == 0, built.stdout
    payload = json.loads(built.stdout)
    assert payload["status"] == "WRITTEN"
    assert Path(payload["parquet_path"]).is_file()
    assert Path(payload["manifest_path"]).is_file()
    assert payload["manifest"]["publication_status"] == "provisional"


def table(path: Path, release: str, value: float, unitid: int = 236948) -> Path:
    pl.DataFrame(
        {
            "unitid": [unitid],
            "release_id": [release],
            "reporting_basis": ["academic_year"],
            "attendance_basis": ["full_time"],
            "tuition_in_district": [None],
            "tuition_in_state": [value],
            "tuition_out_of_state": [None],
            "books_and_supplies": [None],
            "status_tuition_in_district": [None],
            "status_tuition_in_state": [None],
            "status_tuition_out_of_state": [None],
            "status_books_and_supplies": [None],
        },
        schema_overrides={
            "tuition_in_district": pl.Float64,
            "tuition_out_of_state": pl.Float64,
            "books_and_supplies": pl.Float64,
            "status_tuition_in_district": pl.String,
            "status_tuition_in_state": pl.String,
            "status_tuition_out_of_state": pl.String,
            "status_books_and_supplies": pl.String,
        },
    ).write_parquet(path)
    return path


def test_compare_charges_supports_scheduled_review_failure(tmp_path: Path) -> None:
    previous = table(tmp_path / "previous.parquet", "2022-23-final", 10000)
    current = table(tmp_path / "current.parquet", "2023-24-final", 14000)
    result = runner.invoke(
        app,
        [
            "ipeds",
            "compare-charges",
            str(previous),
            str(current),
            "--fail-on-review",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "REVIEW_REQUIRED"
    assert payload["history_source_status"] == "NOT_APPLICABLE"
    assert payload["changes"][0]["percent_change"] == 0.4


def test_compare_charges_accepts_directional_history_file(tmp_path: Path) -> None:
    previous = table(tmp_path / "previous.parquet", "2022-23-final", 10000, unitid=1)
    current = table(tmp_path / "current.parquet", "2023-24-final", 14000, unitid=10)
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "history_id": "nces-2022-2023",
                "source_release": "2022-23-final",
                "target_release": "2023-24-final",
                "source_url": "https://nces.ed.gov/ipeds/history.json",
                "source_sha256": "a" * 64,
                "entries": [
                    {
                        "source_unitid": 1,
                        "target_unitid": 10,
                        "relationship": "id_changed",
                        "confidence": "high",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["ipeds", "compare-charges", str(previous), str(current), "--history", str(history)],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "REVIEW_REQUIRED"
    assert payload["history_source_status"] == "UNVERIFIED"
    assert payload["institution_pairing"]["history_id"] == "nces-2022-2023"
    assert payload["institution_pairing"]["history_sha256"] == "a" * 64
    assert {item["change_type"] for item in payload["changes"]} == {
        "institution_identity_changed",
        "value_changed",
    }
    assert all(item["current_unitid"] == 10 for item in payload["changes"])

    invalid = runner.invoke(
        app,
        ["ipeds", "compare-charges", str(current), str(previous), "--history", str(history)],
    )
    assert invalid.exit_code == 2
    assert json.loads(invalid.stdout)["status"] == "INVALID"

    history.write_text("not JSON", encoding="utf-8")
    malformed = runner.invoke(
        app,
        ["ipeds", "compare-charges", str(previous), str(current), "--history", str(history)],
    )
    assert malformed.exit_code == 2
    assert json.loads(malformed.stdout)["status"] == "INVALID"


def test_compare_charges_verifies_history_source_bytes(tmp_path: Path) -> None:
    previous = table(tmp_path / "previous.parquet", "2022-23-final", 10000, unitid=1)
    current = table(tmp_path / "current.parquet", "2023-24-final", 14000, unitid=10)
    source = tmp_path / "source.csv"
    source.write_text("source,target\n1,10\n", encoding="utf-8")
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "history_id": "nces-2022-2023",
                "source_release": "2022-23-final",
                "target_release": "2023-24-final",
                "source_url": "https://nces.ed.gov/ipeds/history.csv",
                "source_sha256": sha256_file(source)[0],
                "entries": [
                    {
                        "source_unitid": 1,
                        "target_unitid": 10,
                        "relationship": "id_changed",
                        "confidence": "high",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = [
        "ipeds",
        "compare-charges",
        str(previous),
        str(current),
        "--history",
        str(history),
        "--history-source",
        str(source),
    ]
    verified = runner.invoke(app, args)
    assert verified.exit_code == 0, verified.stdout
    assert json.loads(verified.stdout)["history_source_status"] == "HASH_VERIFIED"

    source.write_text("source,target\n1,11\n", encoding="utf-8")
    mismatch = runner.invoke(app, args)
    assert mismatch.exit_code == 2
    assert json.loads(mismatch.stdout)["status"] == "INVALID"
    assert "SHA-256" in json.loads(mismatch.stdout)["error"]

    no_history = runner.invoke(
        app,
        ["ipeds", "compare-charges", str(previous), str(current), "--history-source", str(source)],
    )
    assert no_history.exit_code == 2
    assert json.loads(no_history.stdout)["status"] == "INVALID"
