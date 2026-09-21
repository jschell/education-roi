"""Reproducible IPEDS academic-year charges to Parquet transformation."""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from education_roi import __version__
from education_roi.ipeds.archive import parse_nonnegative_cost, read_charge_rows
from education_roi.ipeds.catalog import IPEDSRelease
from education_roi.ipeds.source import (
    BOOKS_COLUMN,
    BOOKS_STATUS_COLUMN,
    IPEDS_CHARGES_DATASET,
    TUITION_COLUMNS,
    TUITION_STATUS_COLUMNS,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

TRANSFORMATION_VERSION = "ipeds-academic-year-charges-v1"


class IPEDSProcessedArtifactConflict(RuntimeError):
    """A stable processed path already contains different bytes or lineage."""


class IPEDSChargesProcessingManifest(BaseModel):
    """Lineage and reporting bases for one normalized charge table."""

    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    publication_status: str
    reporting_basis: str
    attendance_basis: str
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ProcessedIPEDSCharges:
    parquet_path: Path
    manifest_path: Path
    manifest: IPEDSChargesProcessingManifest


def _publish_immutable(temporary: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(temporary) != sha256_file(destination):
            raise IPEDSProcessedArtifactConflict(
                f"processed path already contains different bytes: {destination}"
            )
        return
    try:
        os.link(temporary, destination)
    except FileExistsError:
        _publish_immutable(temporary, destination)


def _status(row: dict[str, str], column: str) -> str | None:
    value = row.get(column, "").strip()
    return value or None


def _normalized_frame(
    rows: dict[int, dict[str, str]], raw_manifest: ArtifactManifest, release: IPEDSRelease
) -> pl.DataFrame:
    records = []
    for unitid, row in sorted(rows.items()):
        records.append(
            {
                "unitid": unitid,
                "release_id": release.release_id,
                "publication_status": release.publication_status.value,
                "reporting_basis": "academic_year",
                "attendance_basis": "full_time",
                "tuition_in_district": parse_nonnegative_cost(
                    row.get(TUITION_COLUMNS["in_district"], "")
                ),
                "tuition_in_state": parse_nonnegative_cost(
                    row.get(TUITION_COLUMNS["in_state"], "")
                ),
                "tuition_out_of_state": parse_nonnegative_cost(
                    row.get(TUITION_COLUMNS["out_of_state"], "")
                ),
                "books_and_supplies": parse_nonnegative_cost(row.get(BOOKS_COLUMN, "")),
                "status_tuition_in_district": _status(row, TUITION_STATUS_COLUMNS["in_district"]),
                "status_tuition_in_state": _status(row, TUITION_STATUS_COLUMNS["in_state"]),
                "status_tuition_out_of_state": _status(row, TUITION_STATUS_COLUMNS["out_of_state"]),
                "status_books_and_supplies": _status(row, BOOKS_STATUS_COLUMN),
                "source_artifact_id": raw_manifest.artifact_id,
                "transformation_version": TRANSFORMATION_VERSION,
            }
        )
    return pl.DataFrame(
        records,
        schema={
            "unitid": pl.Int64,
            "release_id": pl.String,
            "publication_status": pl.String,
            "reporting_basis": pl.String,
            "attendance_basis": pl.String,
            "tuition_in_district": pl.Float64,
            "tuition_in_state": pl.Float64,
            "tuition_out_of_state": pl.Float64,
            "books_and_supplies": pl.Float64,
            "status_tuition_in_district": pl.String,
            "status_tuition_in_state": pl.String,
            "status_tuition_out_of_state": pl.String,
            "status_books_and_supplies": pl.String,
            "source_artifact_id": pl.String,
            "transformation_version": pl.String,
        },
    )


def transform_charges_archive(
    archive: Path,
    output_root: Path,
    raw_manifest: ArtifactManifest,
    release: IPEDSRelease,
) -> ProcessedIPEDSCharges:
    """Create an immutable institution/release charge table with full raw lineage."""
    if raw_manifest.dataset_id != IPEDS_CHARGES_DATASET.dataset_id:
        raise ValueError("raw manifest must identify the IPEDS charges dataset")
    if raw_manifest.release != release.release_id:
        raise ValueError("raw manifest and catalog release do not match")
    if sha256_file(archive) != (raw_manifest.sha256, raw_manifest.file_size):
        raise ValueError("raw archive does not match its artifact manifest")

    frame = _normalized_frame(read_charge_rows(archive), raw_manifest, release)
    relative_directory = (
        Path(IPEDS_CHARGES_DATASET.dataset_id)
        / release.release_id
        / raw_manifest.sha256
        / TRANSFORMATION_VERSION
    )
    parquet_relative = relative_directory / "charges.parquet"
    parquet_path = output_root / parquet_relative
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="ipeds-charges-", suffix=".partial", dir=output_root
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.write_parquet(temporary, compression="zstd", statistics=True, row_group_size=100_000)
        _publish_immutable(temporary, parquet_path)
        output_hash, _ = sha256_file(parquet_path)
    finally:
        temporary.unlink(missing_ok=True)

    transformation = TransformationManifest(
        transformation_id=(
            f"{TRANSFORMATION_VERSION}:{release.release_id}:{raw_manifest.sha256}:{output_hash}"
        ),
        created_at=datetime.now(UTC),
        software_version=__version__,
        output_sha256=output_hash,
        input_artifact_ids=(raw_manifest.artifact_id,),
        parameters={
            "attendance_basis": "full_time",
            "release_id": release.release_id,
            "reporting_basis": "academic_year",
            "transformation_version": TRANSFORMATION_VERSION,
        },
    )
    processing = IPEDSChargesProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        reporting_basis="academic_year",
        attendance_basis="full_time",
        row_count=frame.height,
        columns=tuple(frame.columns),
        output_path=parquet_relative.as_posix(),
    )
    manifest_path = parquet_path.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = IPEDSChargesProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            existing.transformation.output_sha256 != output_hash
            or existing.transformation.input_artifact_ids != (raw_manifest.artifact_id,)
            or existing.output_path != parquet_relative.as_posix()
        ):
            raise IPEDSProcessedArtifactConflict(
                f"processed manifest does not match regenerated output: {manifest_path}"
            )
        return ProcessedIPEDSCharges(parquet_path, manifest_path, existing)

    payload = json.dumps(processing.model_dump(mode="json"), indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="ipeds-manifest-", suffix=".partial", dir=output_root
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    temporary_manifest = Path(temporary_name)
    try:
        _publish_immutable(temporary_manifest, manifest_path)
    finally:
        temporary_manifest.unlink(missing_ok=True)
    return ProcessedIPEDSCharges(parquet_path, manifest_path, processing)
