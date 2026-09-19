"""Reproducible ACS archive-to-Parquet transformation."""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from education_roi import __version__
from education_roi.acs.ingest import read_person_archive
from education_roi.acs.models import ACSRelease
from education_roi.acs.transform import apply_zhang_sample
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

TRANSFORMATION_VERSION = "acs-zhang-sample-v1"


class ProcessedArtifactConflict(RuntimeError):
    """Raised when a stable processed path contains different bytes."""


class ACSProcessingManifest(BaseModel):
    """Dataset-specific lineage and output description."""

    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    vintage: int
    product: str
    geography: str
    cpi_basis: str
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ProcessedACSArtifact:
    """Paths and manifest produced by an ACS transformation."""

    parquet_path: Path
    manifest_path: Path
    manifest: ACSProcessingManifest


def _publish_immutable(temporary: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        temporary_hash, temporary_size = sha256_file(temporary)
        current_hash, current_size = sha256_file(destination)
        if (temporary_hash, temporary_size) != (current_hash, current_size):
            raise ProcessedArtifactConflict(
                f"processed path already contains different bytes: {destination}"
            )
        return
    try:
        os.link(temporary, destination)
    except FileExistsError:
        _publish_immutable(temporary, destination)


def transform_zhang_archive(
    archive: Path,
    output_root: Path,
    raw_manifest: ArtifactManifest,
    release: ACSRelease,
) -> ProcessedACSArtifact:
    """Create a versioned analytical Parquet file with complete raw lineage."""
    if raw_manifest.dataset_id != "acs-pums":
        raise ValueError("raw manifest must identify the acs-pums dataset")
    archive_hash, archive_size = sha256_file(archive)
    if (archive_hash, archive_size) != (raw_manifest.sha256, raw_manifest.file_size):
        raise ValueError("raw archive does not match its artifact manifest")

    transformed = apply_zhang_sample(read_person_archive(archive)).with_columns(
        pl.lit(raw_manifest.artifact_id).alias("source_artifact_id"),
        pl.lit(release.release_id).alias("acs_release_id"),
        pl.lit(TRANSFORMATION_VERSION).alias("transformation_version"),
        pl.lit(f"ACS {release.vintage} ADJINC-adjusted dollars").alias("cpi_basis"),
    )
    relative_directory = (
        Path("acs-pums") / release.release_id / raw_manifest.sha256 / TRANSFORMATION_VERSION
    )
    parquet_relative = relative_directory / "zhang-sample.parquet"
    parquet_path = output_root / parquet_relative

    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="acs-parquet-", suffix=".partial", dir=output_root
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        transformed.write_parquet(
            temporary,
            compression="zstd",
            statistics=True,
            row_group_size=100_000,
        )
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
            "release_id": release.release_id,
            "sample": "zhang-main",
            "transformation_version": TRANSFORMATION_VERSION,
        },
    )
    processing = ACSProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        vintage=release.vintage,
        product=release.product.value,
        geography=release.geography,
        cpi_basis=f"ACS {release.vintage} ADJINC-adjusted dollars",
        row_count=transformed.height,
        columns=tuple(transformed.columns),
        output_path=parquet_relative.as_posix(),
    )
    manifest_path = parquet_path.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = ACSProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            existing.transformation.output_sha256 != output_hash
            or existing.transformation.input_artifact_ids != (raw_manifest.artifact_id,)
            or existing.output_path != parquet_relative.as_posix()
        ):
            raise ProcessedArtifactConflict(
                f"processed manifest does not match regenerated output: {manifest_path}"
            )
        return ProcessedACSArtifact(parquet_path, manifest_path, existing)
    manifest_payload = json.dumps(processing.model_dump(mode="json"), indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="acs-manifest-", suffix=".partial", dir=output_root
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(manifest_payload)
        output.flush()
        os.fsync(output.fileno())
    temporary_manifest = Path(temporary_name)
    try:
        _publish_immutable(temporary_manifest, manifest_path)
    finally:
        temporary_manifest.unlink(missing_ok=True)
    return ProcessedACSArtifact(parquet_path, manifest_path, processing)
