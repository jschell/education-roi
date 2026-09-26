"""Verify processed EF2023A enrollment and resolve one institution/cohort."""

import json
from pathlib import Path

import polars as pl
from pydantic import Field, ValidationError

from education_roi.ipeds.enrollment import COHORTS, ENROLLMENT_DATA, EnrollmentCohort
from education_roi.ipeds.enrollment_pipeline import (
    COLUMNS,
    KEYS,
    VERSION,
    IPEDSEnrollmentProcessingManifest,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel

STORED_COLUMNS = (
    "unitid",
    "efalevel",
    "line",
    "section",
    "lstudy",
    "enrollment_count",
    "fall_year",
    *(
        column
        for column in COLUMNS
        if column
        not in {"unitid", "efalevel", "line", "section", "lstudy", "enrollment_count", "fall_year"}
    ),
)


class IPEDSEnrollmentTableError(ValueError):
    """Invalid enrollment table, source cells, or manifest lineage."""


class EnrollmentEvidence(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    cohort: EnrollmentCohort
    population: str
    efalevel: int
    line: int
    section: int
    lstudy: int
    enrollment_count: int | None
    raw_enrollment_count: str | None
    source_status: str | None
    unavailable_reason: str | None
    fall_year: int
    release_id: str
    publication_status: str
    data_artifact_id: str
    dictionary_artifact_id: str
    transformation_version: str
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation: str = (
        "Observed fall enrollment in one exact institution and cohort, not admissions, "
        "completion, or transfer-out probability; reviewed categories overlap."
    )


def resolve_enrollment_evidence(
    path: Path, unitid: int, cohort: EnrollmentCohort
) -> EnrollmentEvidence:
    """Validate every table row and lineage before selecting one exact cohort."""
    if unitid <= 0:
        raise ValueError("UNITID must be positive")
    if not isinstance(cohort, EnrollmentCohort):
        raise ValueError("requires an explicit enrollment cohort")
    sidecar = path.with_suffix(".manifest.json")
    try:
        manifest = IPEDSEnrollmentProcessingManifest.model_validate_json(
            sidecar.read_text(encoding="utf-8")
        )
        table_hash = sha256_file(path)[0]
        manifest_hash = sha256_file(sidecar)[0]
        if table_hash != manifest.transformation.output_sha256:
            raise IPEDSEnrollmentTableError("enrollment table hash differs from manifest")
        frame = pl.read_parquet(path)
    except (OSError, UnicodeError, ValidationError, pl.exceptions.PolarsError) as error:
        raise IPEDSEnrollmentTableError(f"could not verify enrollment table: {error}") from error
    parameters = manifest.transformation.parameters
    path_parts = Path(manifest.output_path).parts
    definitions = json.dumps(
        {item.value: values for item, values in COHORTS.items()}, sort_keys=True
    )
    if (
        manifest.release_id != "2023-24-final"
        or manifest.publication_status != "final"
        or manifest.fall_year != 2023
        or manifest.key_columns != KEYS
        or parameters.get("data_member") != "ef2023a_rv.csv"
        or parameters.get("fall_year") != 2023
        or parameters.get("cohort_definitions") != definitions
        or parameters.get("transformation_version") != VERSION
        or len(path_parts) != 6
        or path_parts[0] != ENROLLMENT_DATA.dataset_id
        or path_parts[1] != manifest.release_id
        or any(
            len(component) != 64 or any(char not in "0123456789abcdef" for char in component)
            for component in path_parts[2:4]
        )
        or path_parts[4:] != (VERSION, "enrollment.parquet")
        or manifest.transformation.transformation_id
        != (f"{VERSION}:{manifest.release_id}:{path_parts[2]}:{path_parts[3]}:{table_hash}")
        or not (
            manifest.output_path == path.name
            or path.as_posix().endswith("/" + manifest.output_path)
        )
    ):
        raise IPEDSEnrollmentTableError("unsupported enrollment release, definitions or path")
    if (
        not frame.height
        or frame.height != manifest.row_count
        or tuple(frame.columns) != STORED_COLUMNS
        or manifest.columns != STORED_COLUMNS
        or len(manifest.transformation.input_artifact_ids) != 2
    ):
        raise IPEDSEnrollmentTableError("enrollment table schema, count or lineage differs")
    data_id, dictionary_id = manifest.transformation.input_artifact_ids
    levels = {int(values[0]): (item, *values[1:]) for item, values in COHORTS.items()}
    previous_key = (0, 0)
    target = (unitid, int(COHORTS[cohort][0]))
    selected = None
    for row in frame.iter_rows(named=True):
        key = (row["unitid"], row["efalevel"])
        if (
            any(not isinstance(item, int) or isinstance(item, bool) for item in key)
            or key[0] <= 0
            or key <= previous_key
            or key[1] not in levels
        ):
            raise IPEDSEnrollmentTableError("enrollment keys are invalid, duplicated or unordered")
        previous_key = key
        item, line, section, study, label = levels[key[1]]
        if (
            row["cohort"] != item.value
            or row["population"] != label
            or (row["line"], row["section"], row["lstudy"]) != (int(line), int(section), int(study))
            or row["fall_year"] != manifest.fall_year
            or row["release_id"] != manifest.release_id
            or row["publication_status"] != manifest.publication_status
            or row["data_artifact_id"] != data_id
            or row["dictionary_artifact_id"] != dictionary_id
            or row["transformation_version"] != VERSION
            or not isinstance(row["raw_enrollment_count"], str)
            or not isinstance(row["source_status"], str)
        ):
            raise IPEDSEnrollmentTableError("enrollment row definitions or lineage differ")
        raw = row["raw_enrollment_count"]
        try:
            parsed = int(raw) if raw else None
        except ValueError as error:
            raise IPEDSEnrollmentTableError("invalid raw enrollment count") from error
        expected = parsed if parsed is not None and parsed >= 0 else None
        reason = None if expected is not None else "missing or negative source count"
        if (
            row["enrollment_count"] != expected
            or row["unavailable_reason"] != reason
            or (
                row["enrollment_count"] is not None
                and (
                    not isinstance(row["enrollment_count"], int)
                    or isinstance(row["enrollment_count"], bool)
                )
            )
        ):
            raise IPEDSEnrollmentTableError("enrollment source cell or availability differs")
        if key == target:
            selected = row
    level, line, section, study, label = COHORTS[cohort]
    count = selected["enrollment_count"] if selected else None
    return EnrollmentEvidence(
        status="OBSERVED" if count is not None else "INSUFFICIENT_DATA",
        unitid=unitid,
        cohort=cohort,
        population=label,
        efalevel=int(level),
        line=int(line),
        section=int(section),
        lstudy=int(study),
        enrollment_count=count,
        raw_enrollment_count=selected["raw_enrollment_count"] if selected else None,
        source_status=selected["source_status"] if selected else None,
        unavailable_reason=(
            selected["unavailable_reason"] if selected else "exact enrollment cohort absent"
        ),
        fall_year=manifest.fall_year,
        release_id=manifest.release_id,
        publication_status=manifest.publication_status,
        data_artifact_id=data_id,
        dictionary_artifact_id=dictionary_id,
        transformation_version=VERSION,
        table_sha256=table_hash,
        manifest_sha256=manifest_hash,
    )
