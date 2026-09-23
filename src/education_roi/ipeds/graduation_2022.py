"""Release-specific dictionary contract for final/revised GR2022."""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from education_roi.ipeds.dictionary import _xlsx_rows
from education_roi.ipeds.graduation import REQUIRED_GR_COLUMNS, IPEDSGraduationError

GR2022_MEMBER = "gr2022_rv.csv"
GR2022_RELEASE = "2022-23-final"
GR2022_COHORT_YEAR = 2016


def verify_gr2022_dictionary(path: Path) -> None:
    """Check final workbook definitions in the older six-cell frequency layout."""
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["gr2022.xlsx"]:
                raise IPEDSGraduationError("GR2022 dictionary must contain gr2022.xlsx")
            data = archive.read("gr2022.xlsx")
            rows = _xlsx_rows(data)
            final_rows = _xlsx_rows(data, sheet_names=frozenset({"FrequenciesRV"}))
    except (OSError, BadZipFile, KeyError, UnicodeError, ValueError) as error:
        raise IPEDSGraduationError(f"could not read GR2022 dictionary: {error}") from error
    codes = {
        (row[1], row[2]): row[3]
        for row in final_rows
        if len(row) >= 6 and row[0].isdigit() and row[2] in {"2", "8", "12", "16", "18A", "50"}
    }
    variables = {row[1] for row in rows if len(row) >= 7 and row[0].isdigit()}
    if not (
        any("(Final/revised release)" in cell for row in rows for cell in row)
        and any("cohort year 2016 (4-year)" in cell for row in rows for cell in row)
        and "adjusted cohort" in codes.get(("GRTYPE", "8"), "").lower()
        and "bachelor's or equiv degrees total" in codes.get(("GRTYPE", "12"), "").lower()
        and "Adjusted cohort" in codes.get(("CHRTSTAT", "12"), "")
        and "bachelor's or equivalent degrees" in codes.get(("CHRTSTAT", "16"), "")
        and "2016" in codes.get(("COHORT", "2"), "")
        and "2016" in codes.get(("SECTION", "2"), "")
        and "Adjusted cohort" in codes.get(("LINE", "50"), "")
        and "bachelor's or equivalent degrees" in codes.get(("LINE", "18A"), "")
        and (REQUIRED_GR_COLUMNS - {"XGRTOTLT"}).issubset(variables)
        and any(len(row) >= 6 and row[1] == "GRTOTLT" and row[5] == "XGRTOTLT" for row in rows)
    ):
        raise IPEDSGraduationError("GR2022 dictionary does not support final bachelor rows")
