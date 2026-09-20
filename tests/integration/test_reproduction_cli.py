import json
import subprocess
import sys
from pathlib import Path

import pytest

from education_roi.reproduction.bundle import verify_reproduction_bundle


def _run_fixture(results_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "education_roi.cli.app",
            "reproduce",
            "synthetic-run",
            "--results-root",
            str(results_root),
            "--run-id",
            "clean-room-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.integration
def test_clean_process_reproduction_is_deterministic_and_verifiable(tmp_path: Path) -> None:
    first = _run_fixture(tmp_path / "first")
    second = _run_fixture(tmp_path / "second")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_output = json.loads(first.stdout)
    second_output = json.loads(second.stdout)
    assert first_output["warning"] == "SYNTHETIC FIXTURE; NOT A PAPER REPRODUCTION"
    assert first_output["certification_status"] == "PROVISIONAL"
    assert second_output["fixture_version"] == first_output["fixture_version"]

    first_path = Path(first_output["bundle_path"])
    second_path = Path(second_output["bundle_path"])
    verify_reproduction_bundle(first_path)
    verify_reproduction_bundle(second_path)
    assert {item.name: item.read_bytes() for item in first_path.iterdir()} == {
        item.name: item.read_bytes() for item in second_path.iterdir()
    }

    report = json.loads((first_path / "report.json").read_text())
    assert report["certification_status"] == "PROVISIONAL"
    assert report["blockers"][0].startswith("SYNTHETIC FIXTURE")
    cost_analysis = json.loads((first_path / "cost-analysis.json").read_text())
    assert cost_analysis == report["cost_analysis"]
    assert [item["case"] for item in cost_analysis] == [
        "LOW",
        "BASE",
        "HIGH",
        "UNAVAILABLE",
    ]
    base = next(item for item in cost_analysis if item["case"] == "BASE")
    assert base["selection"]["estimate"]["actual_level"] == "INSTITUTION"
    unavailable = next(item for item in cost_analysis if item["case"] == "UNAVAILABLE")
    assert unavailable["status"] == "INSUFFICIENT_DATA"
    assert unavailable["estimate"] is None

    comparisons = {
        item["target_id"]: item
        for item in json.loads((first_path / "comparisons.json").read_text())
    }
    assert comparisons["synthetic-public-cost:base"]["status"] == "PASS"
    assert comparisons["synthetic-public-cost:base"]["cost_irr_delta_from_base"] == 0
    assert comparisons["synthetic-public-cost:base"]["cost_npv_delta_from_base"] == 0
    assert comparisons["synthetic-public-cost:low"]["cost_irr_delta_from_base"] > 0
    assert comparisons["synthetic-public-cost:high"]["cost_irr_delta_from_base"] < 0
    assert comparisons["synthetic-missing-cost:unavailable"]["status"] == "REVIEW"
