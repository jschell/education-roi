from pathlib import Path

import polars as pl
import pytest

from education_roi.ipeds import (
    InstitutionHistory,
    IPEDSChargeChangeType,
    IPEDSReleaseComparisonError,
    compare_charge_tables,
)


def write_table(path: Path, release: str, rows: list[dict[str, object]]) -> Path:
    records = []
    for row in rows:
        records.append(
            {
                "unitid": row["unitid"],
                "release_id": release,
                "reporting_basis": "academic_year",
                "attendance_basis": "full_time",
                "tuition_in_district": row.get("tuition_in_district"),
                "tuition_in_state": row.get("tuition_in_state"),
                "tuition_out_of_state": row.get("tuition_out_of_state"),
                "books_and_supplies": row.get("books_and_supplies"),
                "status_tuition_in_district": row.get("status_tuition_in_district"),
                "status_tuition_in_state": row.get("status_tuition_in_state"),
                "status_tuition_out_of_state": row.get("status_tuition_out_of_state"),
                "status_books_and_supplies": row.get("status_books_and_supplies"),
            }
        )
    pl.DataFrame(records).write_parquet(path)
    return path


def test_release_comparison_flags_large_availability_identity_and_status_changes(
    tmp_path: Path,
) -> None:
    previous = write_table(
        tmp_path / "previous.parquet",
        "2022-23-final",
        [
            {
                "unitid": 1,
                "tuition_in_state": 10000.0,
                "books_and_supplies": 1000.0,
                "status_tuition_in_state": "R",
            },
            {"unitid": 2, "tuition_in_state": 8000.0},
        ],
    )
    current = write_table(
        tmp_path / "current.parquet",
        "2023-24-final",
        [
            {
                "unitid": 1,
                "tuition_in_state": 14000.0,
                "books_and_supplies": None,
                "status_tuition_in_state": "I",
            },
            {"unitid": 3, "tuition_in_state": 9000.0},
        ],
    )

    report = compare_charge_tables(previous, current, percent_change_threshold=0.25)

    assert report.review_required
    assert report.previous_institution_count == 2
    assert report.current_institution_count == 2
    kinds = {change.change_type for change in report.changes}
    assert kinds == {
        IPEDSChargeChangeType.INSTITUTION_ADDED,
        IPEDSChargeChangeType.INSTITUTION_MISSING,
        IPEDSChargeChangeType.AVAILABILITY_CHANGED,
        IPEDSChargeChangeType.VALUE_CHANGED,
        IPEDSChargeChangeType.SOURCE_STATUS_CHANGED,
    }
    tuition = next(
        change
        for change in report.changes
        if change.unitid == 1 and change.change_type is IPEDSChargeChangeType.VALUE_CHANGED
    )
    assert tuition.percent_change == pytest.approx(0.4)
    assert tuition.review_required


def test_small_value_change_is_recorded_without_forcing_review(tmp_path: Path) -> None:
    previous = write_table(
        tmp_path / "previous.parquet", "2022-23-final", [{"unitid": 1, "tuition_in_state": 10000.0}]
    )
    current = write_table(
        tmp_path / "current.parquet", "2023-24-final", [{"unitid": 1, "tuition_in_state": 11000.0}]
    )
    report = compare_charge_tables(previous, current, percent_change_threshold=0.25)
    assert not report.review_required
    assert len(report.changes) == 1
    assert not report.changes[0].review_required


def test_comparison_rejects_same_release_or_incompatible_basis(tmp_path: Path) -> None:
    previous = write_table(tmp_path / "previous.parquet", "2023-24-final", [{"unitid": 1}])
    same = write_table(tmp_path / "same.parquet", "2023-24-final", [{"unitid": 1}])
    with pytest.raises(IPEDSReleaseComparisonError, match="different releases"):
        compare_charge_tables(previous, same)

    current = write_table(tmp_path / "current.parquet", "2024-25-final", [{"unitid": 1}])
    frame = pl.read_parquet(current).with_columns(pl.lit("part_time").alias("attendance_basis"))
    frame.write_parquet(current)
    with pytest.raises(IPEDSReleaseComparisonError, match="bases must match"):
        compare_charge_tables(previous, current)


def history(entries: list[dict[str, object]]) -> InstitutionHistory:
    return InstitutionHistory.model_validate(
        {
            "history_id": "hd-2022-2023",
            "source_release": "2022-23-final",
            "target_release": "2023-24-final",
            "source_url": "https://nces.ed.gov/ipeds/history.json",
            "source_sha256": "a" * 64,
            "entries": entries,
        }
    )


def test_comparison_follows_unique_unitid_change(tmp_path: Path) -> None:
    previous = write_table(
        tmp_path / "previous.parquet",
        "2022-23-final",
        [{"unitid": 1, "tuition_in_state": 10000.0}],
    )
    current = write_table(
        tmp_path / "current.parquet",
        "2023-24-final",
        [{"unitid": 10, "tuition_in_state": 14000.0}],
    )

    report = compare_charge_tables(
        previous,
        current,
        institution_history=history(
            [
                {
                    "source_unitid": 1,
                    "target_unitid": 10,
                    "relationship": "id_changed",
                    "confidence": "high",
                }
            ]
        ),
    )

    kinds = [change.change_type for change in report.changes]
    assert kinds == [
        IPEDSChargeChangeType.INSTITUTION_IDENTITY_CHANGED,
        IPEDSChargeChangeType.VALUE_CHANGED,
    ]
    assert all(change.unitid == 1 for change in report.changes)
    assert all(change.current_unitid == 10 for change in report.changes)
    assert report.institution_pairing.pairings[0].source_unitid == 1
    assert report.institution_pairing.pairings[0].target_unitid == 10


def test_comparison_does_not_aggregate_ambiguous_split(tmp_path: Path) -> None:
    previous = write_table(
        tmp_path / "previous.parquet",
        "2022-23-final",
        [{"unitid": 1, "tuition_in_state": 10000.0}],
    )
    current = write_table(
        tmp_path / "current.parquet",
        "2023-24-final",
        [
            {"unitid": 10, "tuition_in_state": 6000.0},
            {"unitid": 11, "tuition_in_state": 7000.0},
        ],
    )

    report = compare_charge_tables(
        previous,
        current,
        institution_history=history(
            [
                {
                    "source_unitid": 1,
                    "target_unitid": 10,
                    "relationship": "split",
                    "confidence": "high",
                },
                {
                    "source_unitid": 1,
                    "target_unitid": 11,
                    "relationship": "split",
                    "confidence": "high",
                },
            ]
        ),
    )

    assert not report.institution_pairing.pairings
    assert {change.change_type for change in report.changes} == {
        IPEDSChargeChangeType.INSTITUTION_ADDED,
        IPEDSChargeChangeType.INSTITUTION_MISSING,
    }
    assert not any(
        change.change_type is IPEDSChargeChangeType.VALUE_CHANGED for change in report.changes
    )
