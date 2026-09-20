import json
from pathlib import Path

from typer.testing import CliRunner

from education_roi.cli.app import app

runner = CliRunner()


def write_catalog(path: Path, *, reviewed_at: str, data_url: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "reviewed_at": reviewed_at,
                "releases": [
                    {
                        "release_id": "2023-24-provisional",
                        "collection_year": 2023,
                        "component": "academic-year-charges",
                        "publication_status": "provisional",
                        "data_url": data_url,
                        "dictionary_url": (
                            "https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY_Dict.zip"
                        ),
                        "inventory_url": (
                            "https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_compare_inventory_emits_deterministic_unchanged_result(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.json"
    observed = tmp_path / "observed.json"
    url = "https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip"
    write_catalog(reviewed, reviewed_at="2026-09-20", data_url=url)
    write_catalog(observed, reviewed_at="2026-09-21", data_url=url)

    first = runner.invoke(app, ["ipeds", "compare-inventory", str(reviewed), str(observed)])
    second = runner.invoke(app, ["ipeds", "compare-inventory", str(reviewed), str(observed)])

    assert first.exit_code == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["status"] == "UNCHANGED"


def test_compare_inventory_can_fail_scheduled_check_on_review_required(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.json"
    observed = tmp_path / "observed.json"
    write_catalog(
        reviewed,
        reviewed_at="2026-09-20",
        data_url="https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip",
    )
    write_catalog(
        observed,
        reviewed_at="2026-09-21",
        data_url="https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY-revised.zip",
    )

    result = runner.invoke(
        app,
        [
            "ipeds",
            "compare-inventory",
            str(reviewed),
            str(observed),
            "--fail-on-change",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "REVIEW_REQUIRED"
    assert payload["changes"][0]["change_type"] == "changed"


def test_compare_inventory_rejects_invalid_snapshot(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.json"
    observed = tmp_path / "observed.json"
    reviewed.write_text("{}", encoding="utf-8")
    observed.write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["ipeds", "compare-inventory", str(reviewed), str(observed)])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["status"] == "INVALID"
