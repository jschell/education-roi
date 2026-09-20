import json
from hashlib import sha256
from pathlib import Path

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.reproduction.bundle import (
    ARTIFACT_NAMES,
    BundleIntegrityError,
    verify_reproduction_bundle,
    write_reproduction_bundle,
)
from education_roi.reproduction.reporting import ReproductionReport, provisional_reproduction_report

runner = CliRunner()


def report() -> ReproductionReport:
    return provisional_reproduction_report(
        configuration_hash="configuration-sha256",
        dataset_hashes=("dataset-sha256",),
        sample_flow=({"step": "input", "unweighted_n": 10, "weighted_n": 100.0},),
        profiles=(),
        profile_validations=(),
        cash_flows=(),
        comparisons=(
            {
                "target_id": "table-3-men",
                "status": "REVIEW",
                "published_value": 0.0906,
                "reproduced_value": None,
                "absolute_difference": None,
            },
        ),
        blockers=("authoritative ACS inputs unavailable",),
        ambiguity_notes=("covariate slope interpretation unresolved",),
    )


def test_bundle_is_complete_verifiable_and_byte_deterministic(tmp_path: Path) -> None:
    first = write_reproduction_bundle(report(), results_root=tmp_path / "one", run_id="run-001")
    second = write_reproduction_bundle(report(), results_root=tmp_path / "two", run_id="run-001")

    expected = {*ARTIFACT_NAMES, "manifest.json"}
    assert {item.name for item in first.path.iterdir()} == expected
    assert first.certification_status == "PROVISIONAL"
    assert verify_reproduction_bundle(first.path) == first
    assert {name: (first.path / name).read_bytes() for name in expected} == {
        name: (second.path / name).read_bytes() for name in expected
    }

    manifest = json.loads((first.path / "manifest.json").read_text())
    assert manifest["run_id"] == "run-001"
    assert manifest["configuration_hash"] == "configuration-sha256"
    assert [item["path"] for item in manifest["artifacts"]] == list(ARTIFACT_NAMES)


def test_bundle_refuses_overwrite_and_unsafe_run_ids(tmp_path: Path) -> None:
    write_reproduction_bundle(report(), results_root=tmp_path, run_id="run-001")
    with pytest.raises(FileExistsError, match="already exists"):
        write_reproduction_bundle(report(), results_root=tmp_path, run_id="run-001")
    for run_id in ("", "../escape", "nested/run", " spaced "):
        with pytest.raises(ValueError, match="path-safe"):
            write_reproduction_bundle(report(), results_root=tmp_path, run_id=run_id)


def test_bundle_detects_tampering_and_cli_fails_nonzero(tmp_path: Path) -> None:
    bundle = write_reproduction_bundle(report(), results_root=tmp_path, run_id="run-001")
    valid = runner.invoke(app, ["reproduce", "verify-bundle", str(bundle.path)])
    assert valid.exit_code == 0
    assert json.loads(valid.stdout) == {
        "certification_status": "PROVISIONAL",
        "files_checked": len(ARTIFACT_NAMES),
        "run_id": "run-001",
        "status": "VALID",
    }

    (bundle.path / "report.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match="integrity mismatch"):
        verify_reproduction_bundle(bundle.path)
    invalid = runner.invoke(app, ["reproduce", "verify-bundle", str(bundle.path)])
    assert invalid.exit_code == 1
    assert json.loads(invalid.stdout)["status"] == "INVALID"


def test_bundle_rejects_noncanonical_json_and_split_report_drift(tmp_path: Path) -> None:
    bundle = write_reproduction_bundle(report(), results_root=tmp_path, run_id="run-001")
    manifest_path = bundle.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match="not canonical"):
        verify_reproduction_bundle(bundle.path)

    drifted = write_reproduction_bundle(report(), results_root=tmp_path, run_id="run-002")
    section = drifted.path / "sample-flow.json"
    section.write_bytes(b"[]")
    manifest_path = drifted.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for artifact in manifest["artifacts"]:
        if artifact["path"] == section.name:
            artifact["sha256"] = sha256(section.read_bytes()).hexdigest()
            artifact["file_size"] = section.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    with pytest.raises(BundleIntegrityError, match="does not match report"):
        verify_reproduction_bundle(drifted.path)
