"""Immutable analytical tables for reviewed final revised retention releases."""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from education_roi import __version__
from education_roi.ipeds.catalog import IPEDSRelease
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict, _publish_immutable
from education_roi.ipeds.retention import (
    RELEASE_SPECS,
    RETENTION_DATA,
    RETENTION_DICTIONARY,
    IPEDSRetentionError,
    _count,
    _percent,
    _require_release,
    _verify_manifest,
    read_retention_rows,
    verify_retention_dictionary,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

VERSION = "ipeds-ef2023d-retention-v1"
POPULATION = "first_time_full_time_degree_or_certificate_seeking_undergraduate"


class IPEDSRetentionProcessingManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    publication_status: str
    entry_cohort_year: int
    observation_year: int
    population: str
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ProcessedIPEDSRetention:
    parquet_path: Path
    manifest_path: Path
    manifest: IPEDSRetentionProcessingManifest


def transform_retention_archive(
    archive: Path,
    dictionary: Path,
    output_root: Path,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    release: IPEDSRelease,
) -> ProcessedIPEDSRetention:
    """Keep reported percent and enrolled count distinct, including source status cells."""
    _require_release(release)
    _, _, _, entry_year, observation_year, _ = RELEASE_SPECS[release.release_id]
    version = f"ipeds-ef{release.collection_year}d-retention-v1"
    _verify_manifest(
        archive, data_manifest, release, RETENTION_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        RETENTION_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_retention_dictionary(dictionary, release.release_id)
    records = []
    for unitid, row in sorted(read_retention_rows(archive, release.data_member or "").items()):
        cohort = _count(row["RRFTCTA"])
        enrolled = _count(row["RET_NMF"])
        percent = _percent(row["RET_PCF"])
        if cohort is not None and enrolled is not None and enrolled > cohort:
            raise IPEDSRetentionError(f"enrolled count exceeds adjusted cohort for UNITID {unitid}")
        if cohort is None or enrolled is None or percent is None:
            reason = "missing or negative source cell"
        elif cohort == 0:
            reason = "zero adjusted cohort"
        else:
            reason = None
        records.append(
            {
                "unitid": unitid,
                "release_id": release.release_id,
                "publication_status": release.publication_status.value,
                "entry_cohort_year": entry_year,
                "observation_year": observation_year,
                "population": POPULATION,
                "adjusted_cohort": cohort,
                "enrolled_next_fall": enrolled,
                "reported_retention_percent": percent,
                "unavailable_reason": reason,
                "raw_adjusted_cohort": row["RRFTCTA"],
                "raw_enrolled_next_fall": row["RET_NMF"],
                "raw_reported_retention_percent": row["RET_PCF"],
                "cohort_status": row["XRRFTCTA"],
                "enrolled_status": row["XRET_NMF"],
                "percent_status": row["XRET_PCF"],
                "data_artifact_id": data_manifest.artifact_id,
                "dictionary_artifact_id": dictionary_manifest.artifact_id,
                "transformation_version": version,
            }
        )
    schema = {
        "unitid": pl.Int64,
        "release_id": pl.String,
        "publication_status": pl.String,
        "entry_cohort_year": pl.Int32,
        "observation_year": pl.Int32,
        "population": pl.String,
        "adjusted_cohort": pl.Int64,
        "enrolled_next_fall": pl.Int64,
        "reported_retention_percent": pl.Int64,
        "unavailable_reason": pl.String,
        "raw_adjusted_cohort": pl.String,
        "raw_enrolled_next_fall": pl.String,
        "raw_reported_retention_percent": pl.String,
        "cohort_status": pl.String,
        "enrolled_status": pl.String,
        "percent_status": pl.String,
        "data_artifact_id": pl.String,
        "dictionary_artifact_id": pl.String,
        "transformation_version": pl.String,
    }
    frame = pl.DataFrame(records, schema=schema)
    relative = (
        Path(RETENTION_DATA.dataset_id)
        / release.release_id
        / data_manifest.sha256
        / dictionary_manifest.sha256
        / version
        / "retention.parquet"
    )
    destination = output_root / relative
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="ipeds-ret-", suffix=".partial", dir=output_root)
    os.close(descriptor)
    temporary = Path(name)
    try:
        frame.write_parquet(temporary, compression="zstd", statistics=True, row_group_size=100_000)
        _publish_immutable(temporary, destination)
        output_hash, _ = sha256_file(destination)
    finally:
        temporary.unlink(missing_ok=True)
    parameters: dict[str, str | int | float | bool | None] = {
        "data_member": release.data_member,
        "entry_cohort_year": entry_year,
        "observation_year": observation_year,
        "population": POPULATION,
        "transformation_version": version,
    }
    transformation = TransformationManifest(
        transformation_id=f"{version}:{release.release_id}:{data_manifest.sha256}:{dictionary_manifest.sha256}:{output_hash}",
        created_at=datetime.now(UTC),
        software_version=__version__,
        output_sha256=output_hash,
        input_artifact_ids=(data_manifest.artifact_id, dictionary_manifest.artifact_id),
        parameters=parameters,
    )
    processing = IPEDSRetentionProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        entry_cohort_year=entry_year,
        observation_year=observation_year,
        population=POPULATION,
        row_count=frame.height,
        columns=tuple(frame.columns),
        output_path=relative.as_posix(),
    )
    manifest_path = destination.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = IPEDSRetentionProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if existing.model_dump(exclude={"transformation": {"created_at"}}) != processing.model_dump(
            exclude={"transformation": {"created_at"}}
        ):
            raise IPEDSProcessedArtifactConflict(
                f"processed retention manifest differs: {manifest_path}"
            )
        return ProcessedIPEDSRetention(destination, manifest_path, existing)
    payload = json.dumps(processing.model_dump(mode="json"), indent=2) + "\n"
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-ret-manifest-", suffix=".partial", dir=output_root
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    temporary = Path(name)
    try:
        _publish_immutable(temporary, manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return ProcessedIPEDSRetention(destination, manifest_path, processing)
