"""Pinned IC2023 academic-year living expense observations by housing basis."""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pydantic import Field

from education_roi.ipeds.archive import IPEDSArchiveError, parse_nonnegative_cost, read_charge_rows
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSPublicationStatus, IPEDSRelease
from education_roi.ipeds.dictionary import IPEDSDictionaryError, _xlsx_rows
from education_roi.ipeds.source import IPEDS_CHARGES_DATASET, IPEDS_DICTIONARY_DATASET
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.scenarios.models import StrictModel

EXPENSE_LABELS = {
    "CHG5AY3": "On campus, food and housing 2023-24",
    "CHG6AY3": "On campus, other expenses 2023-24",
    "CHG7AY3": "Off campus (not with family), food and housing 2023-24",
    "CHG8AY3": "Off campus (not with family), other expenses 2023-24",
    "CHG9AY3": "Off campus (with family), other expenses 2023-24",
}


class IPEDSExpenseError(ValueError):
    """The pinned expense observation lacks validated source semantics or lineage."""


class IPEDSExpenseObservation(StrictModel):
    unitid: int = Field(gt=0)
    release_id: str
    publication_status: str
    status: str
    on_campus_food_housing: float | None
    on_campus_other: float | None
    off_campus_food_housing: float | None
    off_campus_other: float | None
    with_family_other: float | None
    source_statuses: dict[str, str | None]
    data_artifact_id: str
    dictionary_artifact_id: str
    source_columns: dict[str, str]
    interpretation: str = (
        "Full-time first-time undergraduate cost-of-attendance estimates by living "
        "arrangement; not net price or incremental living cost."
    )


def _verify_source(
    path: Path, manifest: ArtifactManifest, release: IPEDSRelease, dataset_id: str, url: str
) -> None:
    if (
        manifest.dataset_id != dataset_id
        or manifest.release != release.release_id
        or manifest.publication_status != release.publication_status.value
        or str(manifest.source_url) != url
        or manifest.state not in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
    ):
        raise IPEDSExpenseError("expense source is not validated for the exact catalog release")
    try:
        matching_bytes = sha256_file(path) == (manifest.sha256, manifest.file_size)
    except OSError as error:
        raise IPEDSExpenseError(f"could not read expense source: {error}") from error
    if not matching_bytes:
        raise IPEDSExpenseError("expense source bytes do not match their validated manifest")


def _verify_dictionary(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["ic2023_ay.xlsx"]:
                raise IPEDSExpenseError("expense dictionary requires ic2023_ay.xlsx")
            rows = _xlsx_rows(archive.read("ic2023_ay.xlsx"), sheet_names=frozenset({"Varlist"}))
    except (OSError, BadZipFile, KeyError, IPEDSDictionaryError) as error:
        raise IPEDSExpenseError(f"could not validate expense dictionary: {error}") from error
    selected = [row for row in rows if len(row) >= 7 and row[1].upper() in EXPENSE_LABELS]
    if len(selected) != len(EXPENSE_LABELS) or any(
        row[6] != EXPENSE_LABELS[row[1].upper()]
        or row[5].upper() != "X" + row[1].upper()
        or row[2] != "N"
        for row in selected
    ):
        raise IPEDSExpenseError("dictionary lacks exact 2023-24 expense and status definitions")


def resolve_ic2023_expenses(
    archive: Path,
    dictionary: Path,
    release: IPEDSRelease,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
) -> IPEDSExpenseObservation:
    """Report five separately sourced estimates; never add living costs to a scenario."""
    if unitid <= 0:
        raise IPEDSExpenseError("UNITID must be positive")
    if (
        release.component is not IPEDSComponent.ACADEMIC_YEAR_CHARGES
        or release.release_id != "2023-24-provisional"
        or release.publication_status is not IPEDSPublicationStatus.PROVISIONAL
    ):
        raise IPEDSExpenseError("requires reviewed IC2023_AY provisional catalog entry")
    _verify_source(
        archive, data_manifest, release, IPEDS_CHARGES_DATASET.dataset_id, str(release.data_url)
    )
    _verify_source(
        dictionary,
        dictionary_manifest,
        release,
        IPEDS_DICTIONARY_DATASET.dataset_id,
        str(release.dictionary_url),
    )
    _verify_dictionary(dictionary)
    rows = read_charge_rows(archive)
    required = set(EXPENSE_LABELS) | {"X" + code for code in EXPENSE_LABELS}
    if not rows or not required.issubset(next(iter(rows.values()))):
        raise IPEDSExpenseError("IC2023_AY archive lacks expense or status columns")
    row = rows.get(unitid)
    values: dict[str, float | None] = {}
    statuses: dict[str, str | None] = {}
    for code in EXPENSE_LABELS:
        try:
            values[code] = parse_nonnegative_cost(row[code]) if row else None
        except IPEDSArchiveError as error:
            raise IPEDSExpenseError(f"{code} for UNITID {unitid}: {error}") from error
        statuses[code] = (row["X" + code] or None) if row else None
    return IPEDSExpenseObservation(
        unitid=unitid,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        status="OBSERVED"
        if any(value is not None for value in values.values())
        else "INSUFFICIENT_DATA",
        on_campus_food_housing=values["CHG5AY3"],
        on_campus_other=values["CHG6AY3"],
        off_campus_food_housing=values["CHG7AY3"],
        off_campus_other=values["CHG8AY3"],
        with_family_other=values["CHG9AY3"],
        source_statuses=statuses,
        data_artifact_id=data_manifest.artifact_id,
        dictionary_artifact_id=dictionary_manifest.artifact_id,
        source_columns={
            name: code
            for code, name in (
                ("CHG5AY3", "on_campus_food_housing"),
                ("CHG6AY3", "on_campus_other"),
                ("CHG7AY3", "off_campus_food_housing"),
                ("CHG8AY3", "off_campus_other"),
                ("CHG9AY3", "with_family_other"),
            )
        },
    )
