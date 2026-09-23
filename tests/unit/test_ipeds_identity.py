import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from education_roi.ipeds import (
    InstitutionHistory,
    InstitutionHistoryError,
    InstitutionPairingFindingType,
    InstitutionRelationship,
    InstitutionResolutionStatus,
    pair_unitids,
    resolve_unitid,
)


def history() -> InstitutionHistory:
    return InstitutionHistory.model_validate(
        {
            "history_id": "ipeds-2022-to-2023-test",
            "source_release": "2022-23-final",
            "target_release": "2023-24-final",
            "source_url": "https://nces.ed.gov/ipeds/datacenter/InstitutionByName.aspx",
            "source_sha256": "b" * 64,
            "entries": [
                {
                    "source_unitid": 100001,
                    "target_unitid": 100001,
                    "relationship": "continuing",
                    "confidence": "high",
                },
                {
                    "source_unitid": 100002,
                    "target_unitid": 200001,
                    "relationship": "split",
                    "confidence": "medium",
                },
                {
                    "source_unitid": 100002,
                    "target_unitid": 200002,
                    "relationship": "split",
                    "confidence": "medium",
                },
                {
                    "source_unitid": 100003,
                    "relationship": "closed",
                    "confidence": "high",
                },
            ],
        }
    )


def test_same_release_resolution_is_explicit_identity() -> None:
    result = resolve_unitid(100001, "2023-24-final", "2023-24-final")
    assert result.target_unitid == 100001
    assert result.relationship is InstitutionRelationship.CONTINUING
    assert result.status is InstitutionResolutionStatus.ACTIVE
    assert not result.review_required


def test_cross_release_resolution_requires_matching_directional_history() -> None:
    with pytest.raises(InstitutionHistoryError, match="requires explicit history"):
        resolve_unitid(100001, "2022-23-final", "2023-24-final")
    with pytest.raises(InstitutionHistoryError, match="direction"):
        resolve_unitid(
            100001,
            "2023-24-final",
            "2022-23-final",
            history=history(),
        )
    with pytest.raises(InstitutionHistoryError, match="no entry"):
        resolve_unitid(999999, "2022-23-final", "2023-24-final", history=history())


def test_split_requires_target_selection_and_preserves_review_state() -> None:
    with pytest.raises(InstitutionHistoryError, match="ambiguous"):
        resolve_unitid(100002, "2022-23-final", "2023-24-final", history=history())
    result = resolve_unitid(
        100002,
        "2022-23-final",
        "2023-24-final",
        history=history(),
        target_unitid=200001,
    )
    assert result.target_unitid == 200001
    assert result.relationship is InstitutionRelationship.SPLIT
    assert result.history_id == "ipeds-2022-to-2023-test"
    assert result.history_sha256 == "b" * 64
    assert result.review_required


def test_closure_is_explicit_and_never_inferred_from_absence() -> None:
    result = resolve_unitid(100003, "2022-23-final", "2023-24-final", history=history())
    assert result.target_unitid is None
    assert result.status is InstitutionResolutionStatus.CLOSED
    assert result.review_required


def test_history_file_is_strict_versioned_and_official(tmp_path: Path) -> None:
    payload = history().model_dump(mode="json")
    path = tmp_path / "history.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert InstitutionHistory.from_file(path) == history()

    with pytest.raises(ValidationError, match="official NCES"):
        InstitutionHistory.model_validate(
            {**payload, "source_url": "https://example.com/history.json"}
        )
    with pytest.raises(ValidationError, match="releases must differ"):
        InstitutionHistory.model_validate({**payload, "target_release": "2022-23-final"})
    closed = payload["entries"][3]
    with pytest.raises(ValidationError, match="cannot have a target"):
        InstitutionHistory.model_validate(
            {**payload, "entries": [{**closed, "target_unitid": 200003}]}
        )


def test_pairing_reports_splits_closures_additions_and_missing_history() -> None:
    report = pair_unitids(
        (100001, 100002, 100003, 100004),
        (100001, 200001, 200002, 300001),
        "2022-23-final",
        "2023-24-final",
        history=history(),
    )
    assert [(item.source_unitid, item.target_unitid) for item in report.pairings] == [
        (100001, 100001)
    ]
    kinds = {finding.finding_type for finding in report.findings}
    assert kinds == {
        InstitutionPairingFindingType.ADDED,
        InstitutionPairingFindingType.AMBIGUOUS_HISTORY,
        InstitutionPairingFindingType.CLOSED,
        InstitutionPairingFindingType.MISSING_HISTORY,
    }
    assert report.history_id == "ipeds-2022-to-2023-test"
    assert report.review_required


def test_pairing_accepts_unique_id_change_but_keeps_it_review_required() -> None:
    source = history().model_dump(mode="json")
    source["entries"] = [
        {
            "source_unitid": 100010,
            "target_unitid": 200010,
            "relationship": "id_changed",
            "confidence": "high",
        }
    ]
    report = pair_unitids(
        (100010,),
        (200010,),
        "2022-23-final",
        "2023-24-final",
        history=InstitutionHistory.model_validate(source),
    )
    assert len(report.pairings) == 1
    assert report.pairings[0].relationship is InstitutionRelationship.ID_CHANGED
    assert report.pairings[0].review_required
    assert report.findings == ()
    assert report.review_required


def test_pairing_refuses_many_to_one_aggregation() -> None:
    source = history().model_dump(mode="json")
    source["entries"] = [
        {
            "source_unitid": unitid,
            "target_unitid": 200020,
            "relationship": "merged",
            "confidence": "high",
        }
        for unitid in (100020, 100021)
    ]
    report = pair_unitids(
        (100020, 100021),
        (200020,),
        "2022-23-final",
        "2023-24-final",
        history=InstitutionHistory.model_validate(source),
    )
    assert report.pairings == ()
    assert any(
        finding.finding_type is InstitutionPairingFindingType.TARGET_COLLISION
        for finding in report.findings
    )
