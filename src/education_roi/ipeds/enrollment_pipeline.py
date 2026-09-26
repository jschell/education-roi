"""Immutable paired EF2023A table of reviewed fall enrollment cohorts."""

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
from education_roi.ipeds.enrollment import (
    COHORTS,
    ENROLLMENT_DATA,
    ENROLLMENT_DICTIONARY,
    _require_release,
    _verify_manifest,
    read_enrollment_rows,
    verify_enrollment_dictionary,
)
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict, _publish_immutable
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

VERSION = "ipeds-ef2023a-enrollment-v1"
KEYS = ("unitid", "efalevel")
COLUMNS = (
    "unitid",
    "efalevel",
    "cohort",
    "population",
    "line",
    "section",
    "lstudy",
    "enrollment_count",
    "raw_enrollment_count",
    "source_status",
    "unavailable_reason",
    "fall_year",
    "release_id",
    "publication_status",
    "data_artifact_id",
    "dictionary_artifact_id",
    "transformation_version",
)


class IPEDSEnrollmentProcessingManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    publication_status: str
    fall_year: int
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ProcessedEnrollment:
    parquet_path: Path
    manifest_path: Path
    manifest: IPEDSEnrollmentProcessingManifest


def transform_enrollment(
    archive: Path,
    dictionary: Path,
    output_root: Path,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    release: IPEDSRelease,
) -> ProcessedEnrollment:
    """Keep one exact row per reviewed institution/level, without cohort sums."""
    _require_release(release)
    _verify_manifest(
        archive, data_manifest, release, ENROLLMENT_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        ENROLLMENT_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_enrollment_dictionary(dictionary)
    rows = read_enrollment_rows(archive, release.data_member or "")
    levels = {
        level: (cohort, line, section, study, label)
        for cohort, (level, line, section, study, label) in COHORTS.items()
    }
    records = []
    for (unitid, level), row in sorted(
        rows.items(), key=lambda item: (item[0][0], int(item[0][1]))
    ):
        cohort, line, section, study, label = levels[level]
        raw = row["EFTOTLT"]
        parsed = int(raw) if raw else None
        available = parsed is not None and parsed >= 0
        records.append(
            {
                "unitid": unitid,
                "efalevel": int(level),
                "cohort": cohort.value,
                "population": label,
                "line": int(line),
                "section": int(section),
                "lstudy": int(study),
                "enrollment_count": parsed if available else None,
                "raw_enrollment_count": raw,
                "source_status": row["XEFTOTLT"],
                "unavailable_reason": None if available else "missing or negative source count",
                "fall_year": 2023,
                "release_id": release.release_id,
                "publication_status": release.publication_status.value,
                "data_artifact_id": data_manifest.artifact_id,
                "dictionary_artifact_id": dictionary_manifest.artifact_id,
                "transformation_version": VERSION,
            }
        )
    schema: dict[str, type[pl.DataType]] = {
        "unitid": pl.Int64,
        "efalevel": pl.Int64,
        "line": pl.Int64,
        "section": pl.Int64,
        "lstudy": pl.Int64,
        "enrollment_count": pl.Int64,
        "fall_year": pl.Int64,
    }
    schema.update({column: pl.String for column in COLUMNS if column not in schema})
    frame = pl.DataFrame(records, schema=schema)
    relative = (
        Path(ENROLLMENT_DATA.dataset_id)
        / release.release_id
        / data_manifest.sha256
        / dictionary_manifest.sha256
        / VERSION
        / "enrollment.parquet"
    )
    destination = output_root / relative
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-enrollment-", suffix=".partial", dir=output_root
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        frame.write_parquet(temporary, compression="zstd", statistics=True, row_group_size=100_000)
        _publish_immutable(temporary, destination)
        output_hash, _ = sha256_file(destination)
    finally:
        temporary.unlink(missing_ok=True)
    transformation = TransformationManifest(
        transformation_id=(
            f"{VERSION}:{release.release_id}:{data_manifest.sha256}:"
            f"{dictionary_manifest.sha256}:{output_hash}"
        ),
        created_at=datetime.now(UTC),
        software_version=__version__,
        output_sha256=output_hash,
        input_artifact_ids=(data_manifest.artifact_id, dictionary_manifest.artifact_id),
        parameters={
            "data_member": release.data_member,
            "fall_year": 2023,
            "cohort_definitions": json.dumps(
                {cohort.value: values for cohort, values in COHORTS.items()}, sort_keys=True
            ),
            "transformation_version": VERSION,
        },
    )
    manifest = IPEDSEnrollmentProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        fall_year=2023,
        row_count=frame.height,
        columns=tuple(frame.columns),
        key_columns=KEYS,
        output_path=relative.as_posix(),
    )
    manifest_path = destination.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = IPEDSEnrollmentProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if existing.model_dump(exclude={"transformation": {"created_at"}}) != manifest.model_dump(
            exclude={"transformation": {"created_at"}}
        ):
            raise IPEDSProcessedArtifactConflict(f"enrollment manifest differs: {manifest_path}")
        return ProcessedEnrollment(destination, manifest_path, existing)
    payload = json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-enrollment-manifest-", suffix=".partial", dir=output_root
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
    return ProcessedEnrollment(destination, manifest_path, manifest)
