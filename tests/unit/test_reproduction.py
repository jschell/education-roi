import json

import polars as pl
import pytest

from education_roi.acs.crosswalk import CrosswalkStatus
from education_roi.reproduction import (
    ReproductionStatus,
    ReproductionTarget,
    compare_target,
    published_zhang_configuration,
    zhang_sample_flow,
)


def row(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "SERIALNO": "1",
        "SPORDER": 1,
        "ADJINC": 1_000_000,
        "PWGTP": 10,
        "AGEP": 30,
        "SCH": 1,
        "SCHL": 21,
        "WAGP": 50_000,
        "FOD1P": "1101",
        "NATIVITY": 1,
    }
    value.update(overrides)
    return value


def test_published_configuration_is_deterministic_and_predeclared() -> None:
    first = published_zhang_configuration()
    second = published_zhang_configuration()
    assert first.acs_vintages == tuple(range(2009, 2022))
    assert first.college_ages == (18, 19, 20, 21)
    assert first.nontuition_attribution == 0.5
    assert first.selection_adjustment == 0.25
    assert first.configuration_hash == second.configuration_hash
    assert len(first.configuration_hash) == 64
    assert json.loads(json.dumps(first.as_dict())) == first.as_dict()


def test_sample_flow_records_every_restriction_and_matches_final_sample() -> None:
    frame = pl.DataFrame(
        [
            row(SERIALNO="included"),
            row(SERIALNO="old", AGEP=66),
            row(SERIALNO="foreign", NATIVITY=2),
            row(SERIALNO="enrolled", SCH=2),
            row(SERIALNO="advanced", SCHL=22),
            row(SERIALNO="zero-wage", WAGP=0),
            row(SERIALNO="zero-weight", PWGTP=0),
            row(SERIALNO="bad-adjustment", ADJINC=0),
            row(SERIALNO="missing-major", FOD1P=None),
            row(SERIALNO="high-school", SCHL=16, FOD1P=None, PWGTP=20),
        ]
    )
    result = zhang_sample_flow(frame)
    assert [record.step for record in result.records] == [
        "input",
        "age",
        "nativity",
        "enrollment",
        "education",
        "earnings",
        "weight",
        "income_adjustment",
        "major",
    ]
    assert [record.unweighted_n for record in result.records] == [10, 9, 8, 7, 6, 5, 4, 3, 2]
    assert result.records[-1].weighted_n == 30
    assert result.final_frame.get_column("SERIALNO").to_list() == ["included", "high-school"]


def test_aggregate_target_passes_or_fails_predeclared_tolerance() -> None:
    target = ReproductionTarget("overall-women-irr", "Table 3", 0.0988, 0.001)
    passed = compare_target(
        target,
        0.0992,
        configuration_hash="a" * 64,
        dataset_hashes=("b" * 64,),
        crosswalk_status=CrosswalkStatus.PROVISIONAL,
    )
    failed = compare_target(
        target,
        0.101,
        configuration_hash="a" * 64,
        dataset_hashes=("b" * 64,),
        crosswalk_status=CrosswalkStatus.PROVISIONAL,
    )
    assert passed.status is ReproductionStatus.PASS
    assert passed.absolute_difference == pytest.approx(0.0004)
    assert failed.status is ReproductionStatus.FAIL


def test_major_target_is_blocked_by_provisional_crosswalk() -> None:
    target = ReproductionTarget(
        "engineering-irr", "Table 4", 0.13, 0.001, requires_verified_crosswalk=True
    )
    result = compare_target(
        target,
        0.13,
        configuration_hash="a" * 64,
        dataset_hashes=("b" * 64,),
        crosswalk_status=CrosswalkStatus.PROVISIONAL,
        ambiguity_notes=("Table A1 supplement unavailable",),
    )
    assert result.status is ReproductionStatus.BLOCKED
    assert result.reproduced_value is None
    assert result.ambiguity_notes == ("Table A1 supplement unavailable",)


def test_missing_reproduced_value_requires_review() -> None:
    target = ReproductionTarget("overall-men-irr", "Table 3", 0.0906, 0.001)
    result = compare_target(
        target,
        None,
        configuration_hash="a" * 64,
        dataset_hashes=("b" * 64,),
        crosswalk_status=CrosswalkStatus.PROVISIONAL,
    )
    assert result.status is ReproductionStatus.REVIEW
    assert json.loads(json.dumps(result.as_dict()))["status"] == "REVIEW"
