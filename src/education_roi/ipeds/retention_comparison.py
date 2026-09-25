"""Review observed retention across distinct, verified institutional entry cohorts."""

from enum import StrEnum
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import Field

from education_roi.ipeds.identity import (
    InstitutionHistory,
    InstitutionPairingFindingType,
    InstitutionPairingReport,
    InstitutionRelationship,
    pair_unitids,
)
from education_roi.ipeds.retention_evidence import (
    IPEDSRetentionTableError,
    RetentionEvidence,
    resolve_retention_evidence,
)
from education_roi.scenarios.models import StrictModel


class IPEDSRetentionComparisonError(ValueError):
    """Retention tables are invalid or have incompatible cohorts."""


class RetentionChangeType(StrEnum):
    INSTITUTION_ADDED = "institution_added"
    INSTITUTION_MISSING = "institution_missing"
    IDENTITY_CHANGED = "identity_changed"
    AVAILABILITY_CHANGED = "availability_changed"
    PERCENT_CHANGED = "percent_changed"
    COUNT_CHANGED = "count_changed"
    SOURCE_STATUS_CHANGED = "source_status_changed"


class RetentionChange(StrictModel):
    unitid: int = Field(gt=0)
    current_unitid: int | None = Field(default=None, gt=0)
    field: str
    change_type: RetentionChangeType
    previous_value: int | None = None
    current_value: int | None = None
    previous_status: str | None = None
    current_status: str | None = None
    review_required: bool
    reason: str


class RetentionComparison(StrictModel):
    previous_release: str
    current_release: str
    previous_entry_cohort_year: int
    current_entry_cohort_year: int
    population: str
    absolute_percent_threshold: int = Field(gt=0, le=100)
    relative_count_threshold: float = Field(gt=0)
    previous_table_sha256: str
    current_table_sha256: str
    previous_manifest_sha256: str
    current_manifest_sha256: str
    previous_data_artifact_id: str
    current_data_artifact_id: str
    previous_dictionary_artifact_id: str
    current_dictionary_artifact_id: str
    previous_institution_count: int
    current_institution_count: int
    institution_pairing: InstitutionPairingReport
    changes: tuple[RetentionChange, ...]
    review_required: bool
    interpretation: str = (
        "Different entry cohorts; separately reported retention percentages are historical "
        "institution observations, not causal effects or individual completion probabilities."
    )


def _verified_rows(path: Path) -> tuple[dict[int, dict[str, Any]], RetentionEvidence]:
    # The evidence reader checks the full table, raw cells, lineage, and sidecar before lookup.
    try:
        evidence = resolve_retention_evidence(path, 1)
        frame = pl.read_parquet(path)
    except (IPEDSRetentionTableError, OSError, pl.exceptions.PolarsError) as error:
        raise IPEDSRetentionComparisonError(f"invalid retention input {path}: {error}") from error
    return {row["unitid"]: row for row in frame.to_dicts()}, evidence


def compare_retention_tables(
    previous_path: Path,
    current_path: Path,
    *,
    absolute_percent_threshold: int = 10,
    relative_count_threshold: float = 0.25,
    institution_history: InstitutionHistory | None = None,
) -> RetentionComparison:
    """Compare observed source fields, routing identity and coverage to manual review."""
    if not 0 < absolute_percent_threshold <= 100:
        raise ValueError("absolute percent threshold must be in (0, 100]")
    if relative_count_threshold <= 0:
        raise ValueError("relative count threshold must be positive")
    previous, before = _verified_rows(previous_path)
    current, after = _verified_rows(current_path)
    if (
        before.release_id != "2022-23-final"
        or after.release_id != "2023-24-final"
        or before.entry_cohort_year != 2021
        or after.entry_cohort_year != 2022
        or before.observation_year != 2022
        or after.observation_year != 2023
        or before.population != after.population
    ):
        raise IPEDSRetentionComparisonError("requires ordered, compatible reviewed cohorts")
    pairing = pair_unitids(
        tuple(previous),
        tuple(current),
        before.release_id,
        after.release_id,
        history=institution_history,
    )
    changes: list[RetentionChange] = []
    for finding in pairing.findings:
        added = finding.finding_type is InstitutionPairingFindingType.ADDED
        for unitid in finding.target_unitids if added else finding.source_unitids:
            changes.append(
                RetentionChange(
                    unitid=unitid,
                    current_unitid=unitid if added else None,
                    field="*",
                    change_type=(
                        RetentionChangeType.INSTITUTION_ADDED
                        if added
                        else RetentionChangeType.INSTITUTION_MISSING
                    ),
                    review_required=True,
                    reason=finding.reason,
                )
            )
    for pair in pairing.pairings:
        source, target = pair.source_unitid, pair.target_unitid
        prior, latest = previous[source], current[target]
        if source != target or pair.relationship is not InstitutionRelationship.CONTINUING:
            changes.append(
                RetentionChange(
                    unitid=source,
                    current_unitid=target,
                    field="*",
                    change_type=RetentionChangeType.IDENTITY_CHANGED,
                    review_required=True,
                    reason="institution identity mapping requires review",
                )
            )
        for field in ("adjusted_cohort", "enrolled_next_fall", "reported_retention_percent"):
            old, new = prior[field], latest[field]
            if old == new:
                continue
            if old is None or new is None:
                kind = RetentionChangeType.AVAILABILITY_CHANGED
                review = True
                reason = "observed-value availability changed between cohorts"
            elif field == "reported_retention_percent":
                kind = RetentionChangeType.PERCENT_CHANGED
                review = abs(int(new) - int(old)) >= absolute_percent_threshold
                reason = "absolute change in reported percentage points"
            else:
                kind = RetentionChangeType.COUNT_CHANGED
                review = (
                    int(old) == 0 or abs(int(new) - int(old)) / int(old) >= relative_count_threshold
                )
                reason = "relative count change; entry cohorts differ by year"
            changes.append(
                RetentionChange(
                    unitid=source,
                    current_unitid=target,
                    field=field,
                    change_type=kind,
                    previous_value=int(old) if old is not None else None,
                    current_value=int(new) if new is not None else None,
                    review_required=review,
                    reason=reason,
                )
            )
        for field in ("cohort_status", "enrolled_status", "percent_status", "unavailable_reason"):
            if prior[field] != latest[field]:
                changes.append(
                    RetentionChange(
                        unitid=source,
                        current_unitid=target,
                        field=field,
                        change_type=RetentionChangeType.SOURCE_STATUS_CHANGED,
                        previous_status=str(prior[field]) if prior[field] is not None else None,
                        current_status=str(latest[field]) if latest[field] is not None else None,
                        review_required=True,
                        reason="source status or availability changed; inspect original rows",
                    )
                )
    ordered = tuple(sorted(changes, key=lambda x: (x.unitid, x.field, x.change_type.value)))
    return RetentionComparison(
        previous_release=before.release_id,
        current_release=after.release_id,
        previous_entry_cohort_year=before.entry_cohort_year,
        current_entry_cohort_year=after.entry_cohort_year,
        population=before.population,
        absolute_percent_threshold=absolute_percent_threshold,
        relative_count_threshold=relative_count_threshold,
        previous_table_sha256=before.table_sha256,
        current_table_sha256=after.table_sha256,
        previous_manifest_sha256=before.manifest_sha256,
        current_manifest_sha256=after.manifest_sha256,
        previous_data_artifact_id=before.data_artifact_id,
        current_data_artifact_id=after.data_artifact_id,
        previous_dictionary_artifact_id=before.dictionary_artifact_id,
        current_dictionary_artifact_id=after.dictionary_artifact_id,
        previous_institution_count=len(previous),
        current_institution_count=len(current),
        institution_pairing=pairing,
        changes=ordered,
        review_required=pairing.review_required
        or any(change.review_required for change in ordered),
    )
