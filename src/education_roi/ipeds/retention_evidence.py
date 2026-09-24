"""Verified lookup of historical first-year retention in a processed table."""

from pathlib import Path

import polars as pl
from pydantic import Field, ValidationError

from education_roi.ipeds.retention_pipeline import (
    POPULATION,
    VERSION,
    IPEDSRetentionProcessingManifest,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel


class IPEDSRetentionTableError(ValueError):
    """Invalid table, lineage, or retained source evidence."""


class RetentionEvidence(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    release_id: str
    publication_status: str
    entry_cohort_year: int
    observation_year: int
    population: str
    adjusted_cohort: int | None
    enrolled_next_fall: int | None
    reported_retention_percent: int | None
    unavailable_reason: str | None
    raw_adjusted_cohort: str | None
    raw_enrolled_next_fall: str | None
    raw_reported_retention_percent: str | None
    cohort_status: str | None
    enrolled_status: str | None
    percent_status: str | None
    data_artifact_id: str
    dictionary_artifact_id: str
    transformation_version: str
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation: str = (
        "Observed first-year institutional retention. The separately reported percentage "
        "may be rounded and include completers; it is not a bachelor's completion "
        "probability or an individual forecast."
    )


def resolve_retention_evidence(path: Path, unitid: int) -> RetentionEvidence:
    """Verify the entire table's cohort contract and immutable manifest before lookup."""
    if unitid <= 0:
        raise ValueError("UNITID must be positive")
    sidecar = path.with_suffix(".manifest.json")
    try:
        manifest = IPEDSRetentionProcessingManifest.model_validate_json(
            sidecar.read_text(encoding="utf-8")
        )
        table_sha256 = sha256_file(path)[0]
        manifest_sha256 = sha256_file(sidecar)[0]
        if manifest.transformation.output_sha256 != table_sha256:
            raise IPEDSRetentionTableError("retention table hash differs from manifest")
        frame = pl.read_parquet(path)
    except (OSError, UnicodeError, ValidationError, pl.exceptions.PolarsError) as error:
        raise IPEDSRetentionTableError(f"could not verify retention table: {error}") from error
    expected = (
        manifest.release_id == "2023-24-final"
        and manifest.publication_status == "final"
        and manifest.entry_cohort_year == 2022
        and manifest.observation_year == 2023
        and manifest.population == POPULATION
        and manifest.transformation.parameters.get("data_member") == "ef2023d_rv.csv"
        and manifest.transformation.parameters.get("transformation_version") == VERSION
        and manifest.transformation.parameters.get("entry_cohort_year") == 2022
        and manifest.transformation.parameters.get("observation_year") == 2023
        and manifest.transformation.parameters.get("population") == POPULATION
        and (
            manifest.output_path == path.name
            or path.as_posix().endswith("/" + manifest.output_path)
        )
    )
    if not expected:
        raise IPEDSRetentionTableError("unsupported retention release, population or path")
    if (
        frame.height != manifest.row_count
        or not frame.height
        or tuple(frame.columns) != manifest.columns
        or frame.get_column("unitid").null_count()
        or frame.get_column("unitid").n_unique() != frame.height
        or len(manifest.transformation.input_artifact_ids) != 2
    ):
        raise IPEDSRetentionTableError("retention table schema, count or UNITIDs differ")
    data_id, dictionary_id = manifest.transformation.input_artifact_ids
    for row in frame.iter_rows(named=True):
        if (
            not isinstance(row["unitid"], int)
            or row["unitid"] <= 0
            or row["release_id"] != manifest.release_id
            or row["publication_status"] != manifest.publication_status
            or row["entry_cohort_year"] != manifest.entry_cohort_year
            or row["observation_year"] != manifest.observation_year
            or row["population"] != manifest.population
            or row["transformation_version"] != VERSION
            or row["data_artifact_id"] != data_id
            or row["dictionary_artifact_id"] != dictionary_id
        ):
            raise IPEDSRetentionTableError("retention row identity or source lineage differs")
        cohort, enrolled, percent = (
            row["adjusted_cohort"],
            row["enrolled_next_fall"],
            row["reported_retention_percent"],
        )
        reason = (
            "missing or negative source cell"
            if cohort is None or enrolled is None or percent is None
            else "zero adjusted cohort"
            if cohort == 0
            else None
        )
        if (
            cohort is not None
            and (not isinstance(cohort, int) or cohort < 0)
            or enrolled is not None
            and (not isinstance(enrolled, int) or enrolled < 0)
            or percent is not None
            and (not isinstance(percent, int) or not 0 <= percent <= 100)
            or cohort is not None
            and enrolled is not None
            and enrolled > cohort
            or row["unavailable_reason"] != reason
        ):
            raise IPEDSRetentionTableError("retention count or availability differs")
        for parsed, raw in (
            (cohort, row["raw_adjusted_cohort"]),
            (enrolled, row["raw_enrolled_next_fall"]),
            (percent, row["raw_reported_retention_percent"]),
        ):
            try:
                value = int(raw) if raw else None
            except (TypeError, ValueError) as error:
                raise IPEDSRetentionTableError("invalid retention source cell") from error
            if (
                not isinstance(raw, str)
                or (value if value is not None and value >= 0 else None) != parsed
            ):
                raise IPEDSRetentionTableError("retention source cell differs from parsed value")
    selected = frame.filter(pl.col("unitid") == unitid).to_dicts()
    result_row = selected[0] if selected else None
    return RetentionEvidence(
        status="OBSERVED"
        if result_row and result_row["unavailable_reason"] is None
        else "INSUFFICIENT_DATA",
        unitid=unitid,
        release_id=manifest.release_id,
        publication_status=manifest.publication_status,
        entry_cohort_year=manifest.entry_cohort_year,
        observation_year=manifest.observation_year,
        population=manifest.population,
        adjusted_cohort=result_row["adjusted_cohort"] if result_row else None,
        enrolled_next_fall=result_row["enrolled_next_fall"] if result_row else None,
        reported_retention_percent=result_row["reported_retention_percent"] if result_row else None,
        unavailable_reason=(
            result_row["unavailable_reason"]
            if result_row
            else "institution absent from exact retention table"
        ),
        raw_adjusted_cohort=result_row["raw_adjusted_cohort"] if result_row else None,
        raw_enrolled_next_fall=result_row["raw_enrolled_next_fall"] if result_row else None,
        raw_reported_retention_percent=result_row["raw_reported_retention_percent"]
        if result_row
        else None,
        cohort_status=result_row["cohort_status"] if result_row else None,
        enrolled_status=result_row["enrolled_status"] if result_row else None,
        percent_status=result_row["percent_status"] if result_row else None,
        data_artifact_id=data_id,
        dictionary_artifact_id=dictionary_id,
        transformation_version=VERSION,
        table_sha256=table_sha256,
        manifest_sha256=manifest_sha256,
    )
