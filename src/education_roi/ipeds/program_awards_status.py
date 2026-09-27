"""Reviewed C2023_A XCTOTALT imputation flag labels from the NCES dictionary."""

from dataclasses import dataclass

LABELS = {
    "A": "Not applicable",
    "B": "Institution left item blank",
    "C": "Analyst corrected reported value",
    "D": "Do not know",
    "G": "Data generated from other data values",
    "H": "Value not derived - data not usable",
    "J": "Logical imputation",
    "K": "Ratio adjustment",
    "L": "Imputed using the Group Median procedure",
    "N": "Imputed using Nearest Neighbor procedure",
    "P": "Imputed using Carry Forward procedure",
    "R": "Reported",
    "Z": "Implied zero",
}


@dataclass(frozen=True)
class AwardSourceStatus:
    label: str | None
    review_required: bool


def interpret_award_status(
    code: str | None, release_id: str = "2023-24-final"
) -> AwardSourceStatus:
    """Flag every nonreported or unknown source cell for human interpretation."""
    if code is None:
        return AwardSourceStatus(None, False)
    label = LABELS.get(code)
    if release_id == "2022-23-final" and code == "Z":
        label = "Implied zero;"
    return AwardSourceStatus(label, code != "R")
