"""Deterministic cross-release review for normalized IPEDS charge tables."""

from enum import StrEnum
from pathlib import Path

import polars as pl
from pydantic import Field

from education_roi.ipeds.identity import (
    InstitutionHistory,
    InstitutionPairingFindingType,
    InstitutionPairingReport,
    InstitutionRelationship,
    pair_unitids,
)
from education_roi.scenarios.models import StrictModel

CHARGE_FIELDS = (
    "tuition_in_district",
    "tuition_in_state",
    "tuition_out_of_state",
    "books_and_supplies",
)
STATUS_FIELDS = {field: f"status_{field}" for field in CHARGE_FIELDS}
REQUIRED_COLUMNS = frozenset(
    {
        "unitid",
        "release_id",
        "reporting_basis",
        "attendance_basis",
        *CHARGE_FIELDS,
        *STATUS_FIELDS.values(),
    }
)


class IPEDSReleaseComparisonError(ValueError):
    """Normalized charge tables cannot be compared without ambiguity."""


class IPEDSChargeChangeType(StrEnum):
    INSTITUTION_ADDED = "institution_added"
    INSTITUTION_MISSING = "institution_missing"
    INSTITUTION_CLOSED = "institution_closed"
    INSTITUTION_IDENTITY_CHANGED = "institution_identity_changed"
    AVAILABILITY_CHANGED = "availability_changed"
    VALUE_CHANGED = "value_changed"
    SOURCE_STATUS_CHANGED = "source_status_changed"


class IPEDSChargeChange(StrictModel):
    unitid: int = Field(gt=0)
    current_unitid: int | None = Field(default=None, gt=0)
    field: str
    change_type: IPEDSChargeChangeType
    previous_value: float | None = None
    current_value: float | None = None
    previous_source_status: str | None = None
    current_source_status: str | None = None
    absolute_change: float | None = None
    percent_change: float | None = None
    review_required: bool
    reason: str


class IPEDSChargeComparison(StrictModel):
    previous_release: str
    current_release: str
    reporting_basis: str
    attendance_basis: str
    percent_change_threshold: float = Field(gt=0)
    previous_institution_count: int = Field(ge=0)
    current_institution_count: int = Field(ge=0)
    institution_pairing: InstitutionPairingReport
    changes: tuple[IPEDSChargeChange, ...]
    review_required: bool


def _table(path: Path) -> tuple[pl.DataFrame, str, str, str]:
    try:
        frame = pl.read_parquet(path)
    except (OSError, pl.exceptions.PolarsError) as error:
        raise IPEDSReleaseComparisonError(
            f"could not read normalized charge table {path}: {error}"
        ) from error
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise IPEDSReleaseComparisonError(
            "normalized charge table is missing columns: " + ", ".join(missing)
        )
    if frame.get_column("unitid").n_unique() != frame.height:
        raise IPEDSReleaseComparisonError("normalized charge table contains duplicate UNITIDs")

    def unique(column: str) -> str:
        values = frame.get_column(column).drop_nulls().unique().to_list()
        if len(values) != 1:
            raise IPEDSReleaseComparisonError(f"normalized charge table must have one {column}")
        return str(values[0])

    return frame, unique("release_id"), unique("reporting_basis"), unique("attendance_basis")


def compare_charge_tables(
    previous_path: Path,
    current_path: Path,
    *,
    percent_change_threshold: float = 0.25,
    institution_history: InstitutionHistory | None = None,
) -> IPEDSChargeComparison:
    """Compare exact normalized releases and flag changes requiring review."""
    if percent_change_threshold <= 0:
        raise ValueError("percent change threshold must be positive")
    previous, previous_release, previous_basis, previous_attendance = _table(previous_path)
    current, current_release, current_basis, current_attendance = _table(current_path)
    if previous_release == current_release:
        raise IPEDSReleaseComparisonError("cross-release comparison requires different releases")
    if (previous_basis, previous_attendance) != (current_basis, current_attendance):
        raise IPEDSReleaseComparisonError("reporting and attendance bases must match")

    previous_rows = {int(row["unitid"]): row for row in previous.to_dicts()}
    current_rows = {int(row["unitid"]): row for row in current.to_dicts()}
    pairing = pair_unitids(
        tuple(previous_rows),
        tuple(current_rows),
        previous_release,
        current_release,
        history=institution_history,
    )
    changes: list[IPEDSChargeChange] = []
    for finding in pairing.findings:
        if finding.finding_type is InstitutionPairingFindingType.ADDED:
            for target_unitid in finding.target_unitids:
                changes.append(
                    IPEDSChargeChange(
                        unitid=target_unitid,
                        current_unitid=target_unitid,
                        field="*",
                        change_type=IPEDSChargeChangeType.INSTITUTION_ADDED,
                        review_required=True,
                        reason=finding.reason,
                    )
                )
            continue
        change_type = (
            IPEDSChargeChangeType.INSTITUTION_CLOSED
            if finding.finding_type is InstitutionPairingFindingType.CLOSED
            else IPEDSChargeChangeType.INSTITUTION_MISSING
        )
        current_unitid = finding.target_unitids[0] if len(finding.target_unitids) == 1 else None
        for source_unitid in finding.source_unitids:
            changes.append(
                IPEDSChargeChange(
                    unitid=source_unitid,
                    current_unitid=current_unitid,
                    field="*",
                    change_type=change_type,
                    review_required=True,
                    reason=finding.reason,
                )
            )

    for institution_pair in pairing.pairings:
        unitid = institution_pair.source_unitid
        current_unitid = institution_pair.target_unitid
        prior = previous_rows[unitid]
        latest = current_rows[current_unitid]
        if (
            unitid != current_unitid
            or institution_pair.relationship is not InstitutionRelationship.CONTINUING
        ):
            changes.append(
                IPEDSChargeChange(
                    unitid=unitid,
                    current_unitid=current_unitid,
                    field="*",
                    change_type=IPEDSChargeChangeType.INSTITUTION_IDENTITY_CHANGED,
                    review_required=True,
                    reason=(
                        "authoritative history pairs the source institution with a different "
                        f"target identity ({institution_pair.relationship.value})"
                    ),
                )
            )
        for field in CHARGE_FIELDS:
            previous_value = prior[field]
            current_value = latest[field]
            if previous_value != current_value:
                if previous_value is None or current_value is None:
                    changes.append(
                        IPEDSChargeChange(
                            unitid=unitid,
                            current_unitid=current_unitid,
                            field=field,
                            change_type=IPEDSChargeChangeType.AVAILABILITY_CHANGED,
                            previous_value=previous_value,
                            current_value=current_value,
                            review_required=True,
                            reason="reported-value availability changed between releases",
                        )
                    )
                else:
                    absolute = float(current_value) - float(previous_value)
                    percent = absolute / float(previous_value) if previous_value != 0 else None
                    requires_review = percent is None or abs(percent) >= percent_change_threshold
                    changes.append(
                        IPEDSChargeChange(
                            unitid=unitid,
                            current_unitid=current_unitid,
                            field=field,
                            change_type=IPEDSChargeChangeType.VALUE_CHANGED,
                            previous_value=previous_value,
                            current_value=current_value,
                            absolute_change=absolute,
                            percent_change=percent,
                            review_required=requires_review,
                            reason=(
                                "change meets manual-review threshold"
                                if requires_review
                                else "change is below manual-review threshold"
                            ),
                        )
                    )
            status_field = STATUS_FIELDS[field]
            if prior[status_field] != latest[status_field]:
                changes.append(
                    IPEDSChargeChange(
                        unitid=unitid,
                        current_unitid=current_unitid,
                        field=field,
                        change_type=IPEDSChargeChangeType.SOURCE_STATUS_CHANGED,
                        previous_source_status=prior[status_field],
                        current_source_status=latest[status_field],
                        review_required=True,
                        reason="raw source-status cell changed; semantics are not inferred",
                    )
                )

    ordered = tuple(
        sorted(changes, key=lambda item: (item.unitid, item.field, item.change_type.value))
    )
    return IPEDSChargeComparison(
        previous_release=previous_release,
        current_release=current_release,
        reporting_basis=previous_basis,
        attendance_basis=previous_attendance,
        percent_change_threshold=percent_change_threshold,
        previous_institution_count=previous.height,
        current_institution_count=current.height,
        institution_pairing=pairing,
        changes=ordered,
        review_required=(
            pairing.review_required or any(change.review_required for change in ordered)
        ),
    )
