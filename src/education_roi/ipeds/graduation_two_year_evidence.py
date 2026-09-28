"""Verify every row of a processed GR2023 two-year cohort table."""

from pathlib import Path

import polars as pl
from pydantic import Field, ValidationError

from education_roi.ipeds.graduation_comparison import (
    IPEDSGraduationComparisonError,
    _verify_processing_manifest,
)
from education_roi.ipeds.graduation_pipeline import (
    GR2023_TWO_YEAR_TRANSFORMATION_VERSION,
    IPEDSGraduationProcessingManifest,
    _count,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel

COHORT_SCOPE = "all_degree_or_certificate_seeking_first_time_full_time_two_year"
COLUMNS = (
    "unitid",
    "release_id",
    "publication_status",
    "cohort_year",
    "cohort_scope",
    "award_outcome",
    "normal_time_percent",
    "adjusted_cohort",
    "any_awards",
    "observed_rate",
    "unavailable_reason",
    "raw_adjusted_cohort",
    "raw_any_awards",
    "cohort_status",
    "award_status",
    "cohort_row_key",
    "award_row_key",
    "data_artifact_id",
    "dictionary_artifact_id",
    "transformation_version",
)


class TwoYearGraduationEvidence(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    release_id: str
    publication_status: str
    cohort_year: int
    cohort_scope: str
    award_outcome: str
    normal_time_percent: int
    adjusted_cohort: int | None
    any_awards: int | None
    observed_rate: float | None
    unavailable_reason: str | None
    raw_adjusted_cohort: str | None
    raw_any_awards: str | None
    cohort_status: str | None
    award_status: str | None
    data_artifact_id: str
    dictionary_artifact_id: str
    transformation_version: str
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation: str = (
        "Historical 2020 two-year entrant cohort, any award within 150% of normal time. "
        "Not an associate-degree rate or an individual completion probability."
    )


def resolve_two_year_graduation_evidence(path: Path, unitid: int) -> TwoYearGraduationEvidence:
    """Read one UNITID after checking the full table, sidecar, and source cells."""
    if unitid <= 0:
        raise ValueError("UNITID must be positive")
    sidecar = path.with_suffix(".manifest.json")
    try:
        manifest = IPEDSGraduationProcessingManifest.model_validate_json(
            sidecar.read_text(encoding="utf-8")
        )
        table_hash = sha256_file(path)[0]
        frame = pl.read_parquet(path)
    except (OSError, UnicodeError, ValidationError, pl.exceptions.PolarsError) as error:
        raise IPEDSGraduationComparisonError(f"could not verify two-year table: {error}") from error
    if not frame.height or tuple(frame.columns) != COLUMNS or tuple(manifest.columns) != COLUMNS:
        raise IPEDSGraduationComparisonError("two-year cohort table schema or rows differ")
    metadata = {
        name: frame[name][0]
        for name in (
            "release_id",
            "publication_status",
            "cohort_year",
            "cohort_scope",
            "award_outcome",
            "normal_time_percent",
            "data_artifact_id",
            "dictionary_artifact_id",
            "transformation_version",
        )
    }
    manifest_hash = _verify_processing_manifest(path, metadata, frame.height)
    if (
        table_hash != sha256_file(path)[0]
        or manifest.release_id != "2023-24-final"
        or manifest.publication_status != "final"
        or manifest.cohort_year != 2020
        or manifest.cohort_scope != COHORT_SCOPE
        or manifest.award_outcome != "any_award"
        or manifest.normal_time_percent != 150
        or manifest.transformation.parameters.get("data_member") != "gr2023_RV.csv"
        or manifest.transformation.parameters.get("cohort_year") != 2020
        or manifest.transformation.parameters.get("cohort_scope") != COHORT_SCOPE
        or manifest.transformation.parameters.get("award_outcome") != "any_award"
        or manifest.transformation.parameters.get("normal_time_percent") != 150
        or metadata["transformation_version"] != GR2023_TWO_YEAR_TRANSFORMATION_VERSION
        or path.name != "two-year-any-award.parquet"
    ):
        raise IPEDSGraduationComparisonError("unsupported two-year cohort definition or lineage")
    selected = None
    previous_unitid = 0
    for row in frame.iter_rows(named=True):
        current = row["unitid"]
        if not isinstance(current, int) or current <= previous_unitid:
            raise IPEDSGraduationComparisonError("two-year UNITIDs must be positive and ordered")
        previous_unitid = current
        if any(row[name] != metadata[name] for name in metadata):
            raise IPEDSGraduationComparisonError("two-year row definition or lineage differs")
        if row["cohort_row_key"] != "COHORT=4;SECTION=4;GRTYPE=29":
            raise IPEDSGraduationComparisonError("two-year cohort row key differs")
        if row["award_row_key"] not in (None, "COHORT=4;SECTION=4;GRTYPE=30"):
            raise IPEDSGraduationComparisonError("two-year award row key differs")
        if row["award_row_key"] is None and (
            row["raw_any_awards"] is not None or row["award_status"] is not None
        ):
            raise IPEDSGraduationComparisonError("two-year absent award has source cells")
        if any(
            value is not None and not isinstance(value, str)
            for value in (
                row["raw_adjusted_cohort"],
                row["raw_any_awards"],
                row["cohort_status"],
                row["award_status"],
            )
        ):
            raise IPEDSGraduationComparisonError("two-year source cells are malformed")
        try:
            denominator = _count(row["raw_adjusted_cohort"])
            numerator = _count(row["raw_any_awards"])
        except ValueError as error:
            raise IPEDSGraduationComparisonError(str(error)) from error
        if row["adjusted_cohort"] != denominator or row["any_awards"] != numerator:
            raise IPEDSGraduationComparisonError("two-year parsed counts differ from source cells")
        if denominator is not None and numerator is not None and numerator > denominator:
            raise IPEDSGraduationComparisonError("two-year awards exceed adjusted cohort")
        reason = (
            "missing cohort or award row"
            if row["award_row_key"] is None
            else "blank or negative count"
            if denominator is None or numerator is None
            else "zero adjusted cohort"
            if denominator == 0
            else None
        )
        rate = (
            numerator / denominator
            if reason is None and numerator is not None and denominator is not None
            else None
        )
        if row["unavailable_reason"] != reason or (
            (rate is None and row["observed_rate"] is not None)
            or (
                rate is not None
                and (
                    not isinstance(row["observed_rate"], (float, int))
                    or abs(row["observed_rate"] - rate) > 1e-12
                )
            )
        ):
            raise IPEDSGraduationComparisonError("two-year rate or availability differs")
        if current == unitid:
            selected = row
    return TwoYearGraduationEvidence(
        status="OBSERVED"
        if selected and selected["observed_rate"] is not None
        else "INSUFFICIENT_DATA",
        unitid=unitid,
        release_id=manifest.release_id,
        publication_status=manifest.publication_status,
        cohort_year=2020,
        cohort_scope=COHORT_SCOPE,
        award_outcome="any_award",
        normal_time_percent=150,
        adjusted_cohort=selected["adjusted_cohort"] if selected else None,
        any_awards=selected["any_awards"] if selected else None,
        observed_rate=selected["observed_rate"] if selected else None,
        unavailable_reason=(
            selected["unavailable_reason"]
            if selected
            else "institution absent from the exact two-year cohort table"
        ),
        raw_adjusted_cohort=selected["raw_adjusted_cohort"] if selected else None,
        raw_any_awards=selected["raw_any_awards"] if selected else None,
        cohort_status=selected["cohort_status"] if selected else None,
        award_status=selected["award_status"] if selected else None,
        data_artifact_id=str(metadata["data_artifact_id"]),
        dictionary_artifact_id=str(metadata["dictionary_artifact_id"]),
        transformation_version=GR2023_TWO_YEAR_TRANSFORMATION_VERSION,
        table_sha256=table_hash,
        manifest_sha256=manifest_hash,
    )
