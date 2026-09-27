from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from education_roi.ipeds import IPEDSComponent, IPEDSReleaseCatalog
from education_roi.ipeds.graduation import IPEDSGraduationError
from education_roi.ipeds.graduation_pipeline import _frame

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,GRTYPE,CHRTSTAT,SECTION,COHORT,LINE,XGRTOTLT,GRTOTLT\n"


def test_bulk_table_preserves_unavailable_count_and_source_status(tmp_path: Path) -> None:
    release = next(
        item
        for item in IPEDSReleaseCatalog.from_file(CATALOG).releases
        if item.component is IPEDSComponent.GRADUATION_RATES and item.release_id == "2023-24-final"
    )
    archive = tmp_path / "data.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr(
            "gr2023_RV.csv",
            HEADER
            + "2,8,12,2,2,50,R,0\n"
            + "2,12,16,2,2,18A,Z,0\n"
            + "1,8,12,2,2,50,R,100\n"
            + "1,12,16,2,2,18A,R,-1\n"
            + "3,8,12,2,2,50,R,10\n",
        )
    frame = _frame(archive, release, "data-id", "dictionary-id")
    rows = frame.to_dicts()
    assert [row["unitid"] for row in rows] == [1, 2, 3]
    assert rows[0]["bachelors_awards"] is None
    assert rows[0]["raw_bachelors_awards"] == "-1"
    assert rows[0]["unavailable_reason"] == "blank or negative count"
    assert rows[1]["observed_rate"] is None
    assert rows[1]["unavailable_reason"] == "zero adjusted cohort"
    assert rows[1]["award_status"] == "Z"
    assert rows[2]["unavailable_reason"] == "missing cohort or award row"
    assert all(row["dictionary_artifact_id"] == "dictionary-id" for row in rows)

    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr(
            "gr2023_RV.csv",
            HEADER + "1,8,12,2,2,50,R,10\n1,12,16,2,2,18A,R,11\n",
        )
    with pytest.raises(IPEDSGraduationError, match="exceed cohort"):
        _frame(archive, release, "data-id", "dictionary-id")


def test_two_year_table_keeps_distinct_population_and_missing_awards(tmp_path: Path) -> None:
    release = next(
        item
        for item in IPEDSReleaseCatalog.from_file(CATALOG).releases
        if item.component is IPEDSComponent.GRADUATION_RATES and item.release_id == "2023-24-final"
    )
    archive = tmp_path / "data.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr(
            "gr2023_RV.csv",
            HEADER
            + "2,29,12,4,4,50,R,0\n2,30,13,4,4,29A,Z,0\n"
            + "1,29,12,4,4,50,R,225\n1,30,13,4,4,29A,R,54\n"
            + "3,29,12,4,4,50,R,10\n",
        )
    frame = _frame(archive, release, "data-id", "dictionary-id", two_year=True)
    rows = frame.to_dicts()
    assert [row["unitid"] for row in rows] == [1, 2, 3]
    assert rows[0]["cohort_year"] == 2020
    assert rows[0]["award_outcome"] == "any_award"
    assert rows[0]["any_awards"] == 54
    assert rows[0]["observed_rate"] == pytest.approx(0.24)
    assert rows[0]["award_row_key"] == "COHORT=4;SECTION=4;GRTYPE=30"
    assert "bachelors_awards" not in frame.columns
    assert rows[1]["unavailable_reason"] == "zero adjusted cohort"
    assert rows[1]["award_status"] == "Z"
    assert rows[2]["unavailable_reason"] == "missing cohort or award row"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023_RV.csv", HEADER + "1,29,12,4,4,50,R,10\n1,30,13,4,4,29A,R,11\n")
    with pytest.raises(IPEDSGraduationError, match="exceed cohort"):
        _frame(archive, release, "data-id", "dictionary-id", two_year=True)
