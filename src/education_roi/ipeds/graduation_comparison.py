"""Cross-release review of observed IPEDS bachelor's cohort tables."""

from enum import StrEnum
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import Field, ValidationError

from education_roi.ipeds.graduation_pipeline import (
    GR2022_TRANSFORMATION_VERSION,
    GR_TRANSFORMATION_VERSION,
    IPEDSGraduationProcessingManifest,
)
from education_roi.ipeds.identity import (
    InstitutionHistory,
    InstitutionPairingFindingType,
    InstitutionPairingReport,
    InstitutionRelationship,
    pair_unitids,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel

REQUIRED = frozenset(
    {
        "unitid",
        "release_id",
        "publication_status",
        "cohort_year",
        "cohort_scope",
        "award_outcome",
        "normal_time_percent",
        "adjusted_cohort",
        "bachelors_awards",
        "observed_rate",
        "unavailable_reason",
        "cohort_status",
        "award_status",
        "data_artifact_id",
        "dictionary_artifact_id",
        "transformation_version",
    }
)


class IPEDSGraduationComparisonError(ValueError):
    """Tables are invalid, incomparable, or ambiguous."""


class GraduationChangeType(StrEnum):
    INSTITUTION_ADDED = "institution_added"
    INSTITUTION_MISSING = "institution_missing"
    INSTITUTION_CLOSED = "institution_closed"
    INSTITUTION_IDENTITY_CHANGED = "institution_identity_changed"
    AVAILABILITY_CHANGED = "availability_changed"
    RATE_CHANGED = "rate_changed"
    COUNT_CHANGED = "count_changed"
    SOURCE_STATUS_CHANGED = "source_status_changed"


class GraduationChange(StrictModel):
    unitid: int = Field(gt=0)
    current_unitid: int | None = Field(default=None, gt=0)
    field: str
    change_type: GraduationChangeType
    previous_value: float | None = None
    current_value: float | None = None
    previous_status: str | None = None
    current_status: str | None = None
    absolute_change: float | None = None
    review_required: bool
    reason: str


class GraduationComparison(StrictModel):
    previous_release: str
    current_release: str
    previous_cohort_year: int
    current_cohort_year: int
    cohort_scope: str
    award_outcome: str
    normal_time_percent: int
    absolute_rate_threshold: float = Field(gt=0, le=1)
    relative_count_threshold: float = Field(gt=0)
    previous_table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_manifest_sha256: str | None = None
    current_manifest_sha256: str | None = None
    previous_data_artifact_id: str
    current_data_artifact_id: str
    previous_dictionary_artifact_id: str
    current_dictionary_artifact_id: str
    previous_institution_count: int = Field(ge=0)
    current_institution_count: int = Field(ge=0)
    institution_pairing: InstitutionPairingReport
    changes: tuple[GraduationChange, ...]
    review_required: bool
    interpretation: str = "different entry cohorts; observed institution rates are not causal"


def _verify_processing_manifest(path: Path, metadata: dict[str, Any], row_count: int) -> str:
    sidecar = path.with_suffix(".manifest.json")
    try:
        manifest = IPEDSGraduationProcessingManifest.model_validate_json(
            sidecar.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError) as error:
        raise IPEDSGraduationComparisonError(
            f"missing or invalid graduation processing manifest for {path}: {error}"
        ) from error
    expected = {
        "release_id": manifest.release_id,
        "publication_status": manifest.publication_status,
        "cohort_year": manifest.cohort_year,
        "cohort_scope": manifest.cohort_scope,
        "award_outcome": manifest.award_outcome,
        "normal_time_percent": manifest.normal_time_percent,
    }
    if any(metadata[key] != value for key, value in expected.items()):
        raise IPEDSGraduationComparisonError(f"manifest population/release mismatch for {path}")
    if (
        manifest.row_count != row_count
        or manifest.transformation.output_sha256 != sha256_file(path)[0]
        or manifest.transformation.input_artifact_ids
        != (metadata["data_artifact_id"], metadata["dictionary_artifact_id"])
        or manifest.transformation.parameters.get("transformation_version")
        != metadata["transformation_version"]
        or manifest.output_path != path.name
        and not path.as_posix().endswith("/" + manifest.output_path)
    ):
        raise IPEDSGraduationComparisonError(f"processing manifest lineage mismatch for {path}")
    return sha256_file(sidecar)[0]


def _table(path: Path) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    try:
        frame = pl.read_parquet(path)
    except (OSError, pl.exceptions.PolarsError) as error:
        raise IPEDSGraduationComparisonError(
            f"could not read cohort table {path}: {error}"
        ) from error
    missing = REQUIRED.difference(frame.columns)
    if missing:
        raise IPEDSGraduationComparisonError(
            "cohort table is missing: " + ", ".join(sorted(missing))
        )
    if (
        not frame.height
        or frame.get_column("unitid").null_count()
        or (frame.get_column("unitid").n_unique() != frame.height)
    ):
        raise IPEDSGraduationComparisonError("cohort table needs unique nonnull UNITIDs")
    metadata = {}
    for key in (
        "release_id",
        "publication_status",
        "cohort_year",
        "cohort_scope",
        "award_outcome",
        "normal_time_percent",
        "data_artifact_id",
        "dictionary_artifact_id",
        "transformation_version",
    ):
        values = frame.get_column(key).unique().to_list()
        if len(values) != 1 or values[0] is None:
            raise IPEDSGraduationComparisonError(f"cohort table needs one nonnull {key}")
        metadata[key] = values[0]
    allowed_version = (
        GR2022_TRANSFORMATION_VERSION
        if metadata["release_id"] == "2022-23-final"
        else GR_TRANSFORMATION_VERSION
    )
    if metadata["publication_status"] != "final" or (
        metadata["transformation_version"] != allowed_version
    ):
        raise IPEDSGraduationComparisonError(
            "cohort table requires the reviewed final transformation"
        )
    if (
        metadata["cohort_scope"] != "bachelors_seeking_first_time_full_time"
        or metadata["award_outcome"] != "bachelors_degree"
        or metadata["normal_time_percent"] != 150
    ):
        raise IPEDSGraduationComparisonError("cohort table has an unsupported population")
    rows: dict[int, dict[str, Any]] = {}
    for row in frame.to_dicts():
        unitid = row["unitid"]
        if not isinstance(unitid, int) or unitid <= 0:
            raise IPEDSGraduationComparisonError("cohort table has invalid UNITID")
        denominator, numerator, rate = (
            row["adjusted_cohort"],
            row["bachelors_awards"],
            row["observed_rate"],
        )
        valid = (
            isinstance(denominator, int)
            and denominator > 0
            and isinstance(numerator, int)
            and 0 <= numerator <= denominator
        )
        if valid:
            if (
                not isinstance(rate, (float, int))
                or not 0 <= rate <= 1
                or abs(rate - numerator / denominator) > 1e-12
                or row["unavailable_reason"] is not None
            ):
                raise IPEDSGraduationComparisonError(
                    f"inconsistent cohort rate for UNITID {unitid}"
                )
        elif rate is not None or not row["unavailable_reason"]:
            raise IPEDSGraduationComparisonError(f"missing unavailable reason for UNITID {unitid}")
        rows[unitid] = row
    return rows, metadata


def compare_graduation_tables(
    previous_path: Path,
    current_path: Path,
    *,
    absolute_rate_threshold: float = 0.10,
    relative_count_threshold: float = 0.25,
    institution_history: InstitutionHistory | None = None,
    require_manifests: bool = False,
) -> GraduationComparison:
    """Flag cross-cohort changes; never treat an observed rate as a forecast."""
    if not 0 < absolute_rate_threshold <= 1:
        raise ValueError("absolute rate threshold must be in (0, 1]")
    if relative_count_threshold <= 0:
        raise ValueError("relative count threshold must be positive")
    previous, before = _table(previous_path)
    current, after = _table(current_path)
    previous_manifest_hash = None
    current_manifest_hash = None
    if require_manifests:
        previous_manifest_hash = _verify_processing_manifest(previous_path, before, len(previous))
        current_manifest_hash = _verify_processing_manifest(current_path, after, len(current))
    if before["release_id"] == after["release_id"]:
        raise IPEDSGraduationComparisonError("comparison requires distinct releases")
    if str(before["release_id"]) >= str(after["release_id"]) or (
        int(before["cohort_year"]) >= int(after["cohort_year"])
    ):
        raise IPEDSGraduationComparisonError("releases and entry cohorts must advance in order")
    comparable = ("cohort_scope", "award_outcome", "normal_time_percent")
    if any(before[key] != after[key] for key in comparable):
        raise IPEDSGraduationComparisonError("cohort scope, award, and time window must match")
    pairing = pair_unitids(
        tuple(previous),
        tuple(current),
        str(before["release_id"]),
        str(after["release_id"]),
        history=institution_history,
    )
    changes: list[GraduationChange] = []
    for finding in pairing.findings:
        for unitid in (
            finding.target_unitids
            if finding.finding_type is InstitutionPairingFindingType.ADDED
            else finding.source_unitids
        ):
            kind = (
                GraduationChangeType.INSTITUTION_ADDED
                if finding.finding_type is InstitutionPairingFindingType.ADDED
                else GraduationChangeType.INSTITUTION_CLOSED
                if finding.finding_type is InstitutionPairingFindingType.CLOSED
                else GraduationChangeType.INSTITUTION_MISSING
            )
            changes.append(
                GraduationChange(
                    unitid=unitid,
                    current_unitid=unitid
                    if kind is GraduationChangeType.INSTITUTION_ADDED
                    else None,
                    field="*",
                    change_type=kind,
                    review_required=True,
                    reason=finding.reason,
                )
            )
    for pair in pairing.pairings:
        source, target = pair.source_unitid, pair.target_unitid
        prior, latest = previous[source], current[target]
        if source != target or pair.relationship is not InstitutionRelationship.CONTINUING:
            changes.append(
                GraduationChange(
                    unitid=source,
                    current_unitid=target,
                    field="*",
                    change_type=GraduationChangeType.INSTITUTION_IDENTITY_CHANGED,
                    review_required=True,
                    reason="institution identity mapping requires review",
                )
            )
        for field in ("adjusted_cohort", "bachelors_awards", "observed_rate"):
            old, new = prior[field], latest[field]
            if old == new:
                continue
            if old is None or new is None:
                kind = GraduationChangeType.AVAILABILITY_CHANGED
                required = True
                reason = "observed-value availability changed between cohorts"
            elif field == "observed_rate":
                kind = GraduationChangeType.RATE_CHANGED
                required = abs(float(new) - float(old)) >= absolute_rate_threshold
                reason = "absolute observed-rate change in percentage points"
            else:
                kind = GraduationChangeType.COUNT_CHANGED
                required = (
                    old == 0
                    or abs(float(new) - float(old)) / float(old) >= relative_count_threshold
                )
                reason = "relative cohort count change; entry cohorts differ by year"
            changes.append(
                GraduationChange(
                    unitid=source,
                    current_unitid=target,
                    field=field,
                    change_type=kind,
                    previous_value=float(old) if old is not None else None,
                    current_value=float(new) if new is not None else None,
                    absolute_change=float(new) - float(old)
                    if old is not None and new is not None
                    else None,
                    review_required=required,
                    reason=reason,
                )
            )
        for field in ("cohort_status", "award_status", "unavailable_reason"):
            if prior[field] != latest[field]:
                changes.append(
                    GraduationChange(
                        unitid=source,
                        current_unitid=target,
                        field=field,
                        change_type=GraduationChangeType.SOURCE_STATUS_CHANGED,
                        previous_status=str(prior[field]) if prior[field] is not None else None,
                        current_status=str(latest[field]) if latest[field] is not None else None,
                        review_required=True,
                        reason="source status or unavailability changed; inspect original rows",
                    )
                )
    ordered = tuple(sorted(changes, key=lambda x: (x.unitid, x.field, x.change_type.value)))
    return GraduationComparison(
        previous_release=str(before["release_id"]),
        current_release=str(after["release_id"]),
        previous_cohort_year=int(before["cohort_year"]),
        current_cohort_year=int(after["cohort_year"]),
        cohort_scope=str(before["cohort_scope"]),
        award_outcome=str(before["award_outcome"]),
        normal_time_percent=int(before["normal_time_percent"]),
        absolute_rate_threshold=absolute_rate_threshold,
        relative_count_threshold=relative_count_threshold,
        previous_table_sha256=sha256_file(previous_path)[0],
        current_table_sha256=sha256_file(current_path)[0],
        previous_manifest_sha256=previous_manifest_hash,
        current_manifest_sha256=current_manifest_hash,
        previous_data_artifact_id=str(before["data_artifact_id"]),
        current_data_artifact_id=str(after["data_artifact_id"]),
        previous_dictionary_artifact_id=str(before["dictionary_artifact_id"]),
        current_dictionary_artifact_id=str(after["dictionary_artifact_id"]),
        previous_institution_count=len(previous),
        current_institution_count=len(current),
        institution_pairing=pairing,
        changes=ordered,
        review_required=pairing.review_required or any(item.review_required for item in ordered),
    )
