import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from education_roi.ipeds import (
    CIPCrosswalk,
    CIPCrosswalkError,
    CIPMappingConfidence,
    CIPRelationship,
    cip_official,
    resolve_cip,
)

OFFICIAL_CROSSWALK = (
    Path(__file__).resolve().parents[2] / "data/crosswalks/nces-cip-2010-to-2020.json"
)


def crosswalk() -> CIPCrosswalk:
    return CIPCrosswalk.model_validate(
        {
            "crosswalk_id": "cip-2010-to-2020-test",
            "source_version": "2010",
            "target_version": "2020",
            "source_url": "https://nces.ed.gov/ipeds/cipcode/crosswalk.aspx",
            "source_sha256": "a" * 64,
            "mappings": [
                {
                    "source_code": "11.0101",
                    "target_code": "11.0101",
                    "relationship": "exact",
                    "confidence": "high",
                },
                {
                    "source_code": "11.9999",
                    "target_code": "11.9998",
                    "relationship": "split",
                    "confidence": "medium",
                },
                {
                    "source_code": "11.9999",
                    "target_code": "11.9999",
                    "relationship": "split",
                    "confidence": "medium",
                },
            ],
        }
    )


def test_same_version_resolution_is_explicit_identity() -> None:
    result = resolve_cip("11.0101", "2020", "2020")
    assert result.target_code == "11.0101"
    assert result.relationship is CIPRelationship.EXACT
    assert result.confidence is CIPMappingConfidence.HIGH
    assert result.crosswalk_id is None
    assert not result.review_required


def test_cross_version_resolution_requires_matching_pinned_crosswalk() -> None:
    with pytest.raises(CIPCrosswalkError, match="requires an explicit crosswalk"):
        resolve_cip("11.0101", "2010", "2020")
    with pytest.raises(CIPCrosswalkError, match="direction"):
        resolve_cip("11.0101", "2020", "2010", crosswalk=crosswalk())
    with pytest.raises(CIPCrosswalkError, match="no mapping"):
        resolve_cip("52.0101", "2010", "2020", crosswalk=crosswalk())


def test_many_to_many_mapping_requires_explicit_target_and_retains_review_state() -> None:
    with pytest.raises(CIPCrosswalkError, match="ambiguous"):
        resolve_cip("11.9999", "2010", "2020", crosswalk=crosswalk())
    result = resolve_cip(
        "11.9999",
        "2010",
        "2020",
        crosswalk=crosswalk(),
        target_code="11.9998",
    )
    assert result.target_code == "11.9998"
    assert result.crosswalk_id == "cip-2010-to-2020-test"
    assert result.crosswalk_sha256 == "a" * 64
    assert result.review_required


def test_crosswalk_file_is_strict_versioned_and_official(tmp_path: Path) -> None:
    payload = crosswalk().model_dump(mode="json")
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert CIPCrosswalk.from_file(path) == crosswalk()

    with pytest.raises(ValidationError, match="official NCES"):
        CIPCrosswalk.model_validate({**payload, "source_url": "https://example.com/cip.json"})
    with pytest.raises(ValidationError, match="versions must differ"):
        CIPCrosswalk.model_validate({**payload, "target_version": "2010"})
    with pytest.raises(ValidationError, match="duplicate"):
        CIPCrosswalk.model_validate(
            {**payload, "mappings": [payload["mappings"][0], payload["mappings"][0]]}
        )


def test_reviewed_nces_mapping_preserves_exact_moved_and_deleted_codes() -> None:
    official = CIPCrosswalk.from_file(OFFICIAL_CROSSWALK)
    assert official.source_sha256 == cip_official.SOURCE_SHA256
    assert len(official.mappings) == 2143
    exact = resolve_cip("11.0101", "2010", "2020", crosswalk=official)
    assert exact.target_code == "11.0101"
    assert not exact.review_required
    moved = resolve_cip("43.0116", "2010", "2020", crosswalk=official)
    assert moved.target_code == "43.0403"
    assert moved.review_required
    with pytest.raises(CIPCrosswalkError, match="no mapping"):
        resolve_cip("60.0406", "2010", "2020", crosswalk=official)


def test_official_import_rejects_unreviewed_source(tmp_path: Path) -> None:
    source = tmp_path / "altered.csv"
    source.write_text(",".join(cip_official.COLUMNS) + "\n", encoding="utf-8")
    with pytest.raises(CIPCrosswalkError, match="SHA-256"):
        cip_official.import_official_cip_crosswalk(source)
