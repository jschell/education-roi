"""Review across distinct bachelor’s entry cohorts with explicit limitations."""

import json
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
    args = ["ipeds", "compare-graduation", str(previous), str(current), "--fail-on-review"]
    report = cli.invoke(app, args)
    assert report.exit_code == 1
    payload = json.loads(report.stdout)
    assert payload["status"] == "REVIEW_REQUIRED"
    assert payload["history_source_status"] == "NOT_APPLICABLE"
    assert payload["changes"][0]["reason"]

    invalid = cli.invoke(app, [*args, "--threshold", "2"])
    assert invalid.exit_code == 2
    assert json.loads(invalid.stdout)["status"] == "INVALID"
