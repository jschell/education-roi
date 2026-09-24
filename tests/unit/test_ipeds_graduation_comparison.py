"""Review across distinct bachelor’s entry cohorts with explicit limitations."""

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.ipeds.graduation_comparison import (
    GraduationChangeType,
    IPEDSGraduationComparisonError,
    compare_graduation_tables,
)
from education_roi.ipeds.graduation_evidence import (
    GraduationEvidenceStatus,
    resolve_graduation_evidence,
)
from education_roi.ipeds.graduation_pipeline import GR_TRANSFORMATION_VERSION
from education_roi.provenance.integrity import sha256_file


def table(path: Path, release: str, cohort_year: int, rows: list[dict[str, object]]) -> Path:
    records = []
    for row in rows:
        denominator = row.get("adjusted_cohort")
        numerator = row.get("bachelors_awards")
        rate = (
            numerator / denominator
            if isinstance(denominator, int) and denominator > 0 and isinstance(numerator, int)
            else None
        )
        records.append(
            {
                "unitid": row["unitid"],
                "release_id": release,
                "publication_status": "final",
                "cohort_year": cohort_year,
                "cohort_scope": "bachelors_seeking_first_time_full_time",
                "award_outcome": "bachelors_degree",
                "normal_time_percent": 150,
                "adjusted_cohort": denominator,
                "bachelors_awards": numerator,
                "observed_rate": rate,
                "unavailable_reason": None if rate is not None else "missing count",
                "cohort_status": row.get("cohort_status", "R"),
                "award_status": row.get("award_status", "R"),
                "data_artifact_id": "data:" + release,
                "dictionary_artifact_id": "dictionary:" + release,
                "transformation_version": GR_TRANSFORMATION_VERSION,
            }
        )
    pl.DataFrame(records).write_parquet(path)
    return path


def manifest(path: Path, *, release: str, year: int) -> Path:
    frame = pl.read_parquet(path)
    payload = {
        "transformation": {
            "transformation_id": "synthetic-fixture",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "software_version": "test",
            "output_sha256": sha256_file(path)[0],
            "input_artifact_ids": ["data:" + release, "dictionary:" + release],
            "parameters": {"transformation_version": GR_TRANSFORMATION_VERSION},
        },
        "release_id": release,
        "publication_status": "final",
        "cohort_year": year,
        "cohort_scope": "bachelors_seeking_first_time_full_time",
        "award_outcome": "bachelors_degree",
        "normal_time_percent": 150,
        "row_count": frame.height,
        "columns": frame.columns,
        "output_path": path.name,
    }
    sidecar = path.with_suffix(".manifest.json")
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return sidecar


def test_comparison_verifies_both_input_manifests_and_detects_tampering(tmp_path: Path) -> None:
    before = table(
        tmp_path / "before.parquet",
        "2023-24-final",
        2017,
        [{"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 60}],
    )
    after = table(
        tmp_path / "after.parquet",
        "2024-25-final",
        2018,
        [{"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 70}],
    )
    prior_manifest = manifest(before, release="2023-24-final", year=2017)
    later_manifest = manifest(after, release="2024-25-final", year=2018)
    report = compare_graduation_tables(before, after, require_manifests=True)
    assert report.previous_manifest_sha256 == sha256_file(prior_manifest)[0]
    assert report.current_manifest_sha256 == sha256_file(later_manifest)[0]
    altered = pl.read_parquet(after).with_columns(pl.lit("Z").alias("award_status"))
    altered.write_parquet(after)
    with pytest.raises(IPEDSGraduationComparisonError, match="lineage mismatch"):
        compare_graduation_tables(before, after, require_manifests=True)
    manifest(after, release="2024-25-final", year=2018)
    payload = json.loads(later_manifest.read_text(encoding="utf-8"))
    payload["cohort_year"] = 2019
    later_manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(IPEDSGraduationComparisonError, match="population/release mismatch"):
        compare_graduation_tables(before, after, require_manifests=True)


def test_processed_graduation_observation_is_verified_and_does_not_infer_probability(
    tmp_path: Path,
) -> None:
    path = table(
        tmp_path / "cohort.parquet",
        "2023-24-final",
        2017,
        [
            {"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 70},
            {"unitid": 2, "adjusted_cohort": 0, "bachelors_awards": 0},
        ],
    )
    sidecar = manifest(path, release="2023-24-final", year=2017)
    observed = resolve_graduation_evidence(path, 1)
    assert observed.status is GraduationEvidenceStatus.OBSERVED
    assert observed.observed_rate == pytest.approx(0.7)
    assert observed.manifest_sha256 == sha256_file(sidecar)[0]
    assert "not a program-specific or individual" in observed.interpretation
    unavailable = resolve_graduation_evidence(path, 2)
    assert unavailable.status is GraduationEvidenceStatus.INSUFFICIENT_DATA
    assert unavailable.observed_rate is None
    absent = resolve_graduation_evidence(path, 999)
    assert absent.status is GraduationEvidenceStatus.INSUFFICIENT_DATA
    assert absent.adjusted_cohort is None
    cli = CliRunner().invoke(app, ["ipeds", "resolve-graduation-table", str(path), "1"])
    assert cli.exit_code == 0
    assert json.loads(cli.stdout)["status"] == "OBSERVED"
    sidecar.unlink()
    with pytest.raises(IPEDSGraduationComparisonError, match="processing manifest"):
        resolve_graduation_evidence(path, 1)


def test_cohort_comparison_flags_changes_and_keeps_distinct_years(tmp_path: Path) -> None:
    previous = table(
        tmp_path / "old.parquet",
        "2023-24-final",
        2017,
        [
            {"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 60},
            {"unitid": 2, "adjusted_cohort": 100, "bachelors_awards": 70},
            {"unitid": 3, "adjusted_cohort": 10, "bachelors_awards": 5},
        ],
    )
    current = table(
        tmp_path / "new.parquet",
        "2024-25-final",
        2018,
        [
            {"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 75},
            {"unitid": 2, "adjusted_cohort": 100, "bachelors_awards": 72, "award_status": "Z"},
            {"unitid": 4, "adjusted_cohort": 10, "bachelors_awards": 5},
        ],
    )
    report = compare_graduation_tables(previous, current, absolute_rate_threshold=0.10)
    assert report.review_required
    assert report.previous_table_sha256 == sha256_file(previous)[0]
    assert report.current_table_sha256 == sha256_file(current)[0]
    assert report.previous_data_artifact_id == "data:2023-24-final"
    assert (report.previous_cohort_year, report.current_cohort_year) == (2017, 2018)
    large = next(c for c in report.changes if c.unitid == 1 and c.field == "observed_rate")
    assert large.change_type is GraduationChangeType.RATE_CHANGED
    assert large.review_required and large.absolute_change == pytest.approx(0.15)
    small = next(c for c in report.changes if c.unitid == 2 and c.field == "observed_rate")
    assert not small.review_required
    assert any(c.field == "award_status" and c.review_required for c in report.changes)
    assert {c.change_type for c in report.changes} >= {
        GraduationChangeType.INSTITUTION_ADDED,
        GraduationChangeType.INSTITUTION_MISSING,
    }
    assert (
        report.model_dump_json()
        == compare_graduation_tables(
            previous, current, absolute_rate_threshold=0.10
        ).model_dump_json()
    )


def test_large_count_shift_requires_review_even_when_rate_is_unchanged(tmp_path: Path) -> None:
    previous = table(
        tmp_path / "old.parquet",
        "2023-24-final",
        2017,
        [{"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 50}],
    )
    current = table(
        tmp_path / "new.parquet",
        "2024-25-final",
        2018,
        [{"unitid": 1, "adjusted_cohort": 150, "bachelors_awards": 75}],
    )
    report = compare_graduation_tables(previous, current)
    assert report.review_required
    assert all(
        item.review_required
        for item in report.changes
        if item.change_type is GraduationChangeType.COUNT_CHANGED
    )


def test_comparison_rejects_same_release_and_inconsistent_rate(tmp_path: Path) -> None:
    previous = table(
        tmp_path / "old.parquet",
        "2023-24-final",
        2017,
        [{"unitid": 1, "adjusted_cohort": 10, "bachelors_awards": 6}],
    )
    current = table(
        tmp_path / "new.parquet",
        "2023-24-final",
        2018,
        [{"unitid": 1, "adjusted_cohort": 10, "bachelors_awards": 7}],
    )
    with pytest.raises(IPEDSGraduationComparisonError, match="distinct releases"):
        compare_graduation_tables(previous, current)
    frame = pl.read_parquet(current).with_columns(
        pl.lit("2024-25-final").alias("release_id"), pl.lit(1.5).alias("observed_rate")
    )
    frame.write_parquet(current)
    with pytest.raises(IPEDSGraduationComparisonError, match="inconsistent cohort rate"):
        compare_graduation_tables(previous, current)


def test_compare_graduation_cli_exposes_review_and_invalid_states(tmp_path: Path) -> None:
    previous = table(
        tmp_path / "previous.parquet",
        "2023-24-final",
        2017,
        [{"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 60}],
    )
    current = table(
        tmp_path / "current.parquet",
        "2024-25-final",
        2018,
        [{"unitid": 1, "adjusted_cohort": 100, "bachelors_awards": 80}],
    )
    cli = CliRunner()
    args = [
        "ipeds",
        "compare-graduation",
        str(previous),
        str(current),
        "--fail-on-review",
        "--allow-unverified-inputs",
    ]
    report = cli.invoke(app, args)
    assert report.exit_code == 1
    payload = json.loads(report.stdout)
    assert payload["status"] == "REVIEW_REQUIRED"
    assert payload["history_source_status"] == "NOT_APPLICABLE"
    assert payload["input_provenance_status"] == "UNVERIFIED"
    assert payload["changes"][0]["reason"]

    invalid = cli.invoke(app, [*args, "--threshold", "2"])
    assert invalid.exit_code == 2
    assert json.loads(invalid.stdout)["status"] == "INVALID"

    missing = cli.invoke(app, ["ipeds", "compare-graduation", str(previous), str(current)])
    assert missing.exit_code == 2
    assert "processing manifest" in json.loads(missing.stdout)["error"]
