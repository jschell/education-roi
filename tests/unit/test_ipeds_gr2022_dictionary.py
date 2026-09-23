from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from education_roi.ipeds.graduation import IPEDSGraduationError
from education_roi.ipeds.graduation_2022 import verify_gr2022_dictionary


def test_legacy_dictionary_requires_2016_final_bachelors_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / "GR2022_Dict.zip"
    with ZipFile(workbook, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gr2022.xlsx", b"synthetic dictionary")
    rows = [
        ["(Final/revised release)"],
        ["cohort year 2016 (4-year)"],
        *[
            ["1", name, "N", "2", "Cont", "XGRTOTLT" if name == "GRTOTLT" else "", name]
            for name in ("UNITID", "GRTYPE", "CHRTSTAT", "SECTION", "COHORT", "LINE", "GRTOTLT")
        ],
        ["1", "GRTYPE", "8", "Bachelor's subcohort adjusted cohort", "1", "1"],
        ["1", "GRTYPE", "12", "Completers of bachelor's or equiv degrees total", "1", "1"],
        ["1", "CHRTSTAT", "12", "Adjusted cohort", "1", "1"],
        ["1", "CHRTSTAT", "16", "Completers of bachelor's or equivalent degrees", "1", "1"],
        ["1", "COHORT", "2", "Bachelor's or equiv 2016", "1", "1"],
        ["1", "SECTION", "2", "Bachelor's or equiv 2016", "1", "1"],
        ["1", "LINE", "50", "Adjusted cohort", "1", "1"],
        ["1", "LINE", "18A", "Completers of bachelor's or equivalent degrees", "1", "1"],
    ]
    monkeypatch.setattr(
        "education_roi.ipeds.graduation_2022._xlsx_rows", lambda data, **kwargs: rows
    )
    verify_gr2022_dictionary(workbook)
    rows[-1][3] = "Other award"
    with pytest.raises(IPEDSGraduationError, match="does not support"):
        verify_gr2022_dictionary(workbook)
