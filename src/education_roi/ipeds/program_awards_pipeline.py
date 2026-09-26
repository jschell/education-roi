"""Immutable paired C2023_A award table with exact source keys and statuses."""

import csv
import io
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from education_roi import __version__
from education_roi.ipeds.catalog import IPEDSRelease
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict, _publish_immutable
from education_roi.ipeds.program_awards import (
    PROGRAM_DATA,
    PROGRAM_DICTIONARY,
    _read_awards,
    _require_release,
    _verify_manifest,
    verify_program_dictionary,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

VERSION = "ipeds-c2023a-program-awards-v1"
KEYS = ("unitid", "cip_code", "major_number", "award_level")


class IPEDSProgramAwardsProcessingManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    publication_status: str
    cip_version: str
    period_start: str
    period_end: str
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ProcessedProgramAwards:
    parquet_path: Path
    manifest_path: Path
    manifest: IPEDSProgramAwardsProcessingManifest


def transform_program_awards(
    archive: Path,
    dictionary: Path,
    output_root: Path,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    release: IPEDSRelease,
) -> ProcessedProgramAwards:
    """Preserve all exact award keys, including aggregate rows, without summing them."""
    _require_release(release)
    _verify_manifest(
        archive, data_manifest, release, PROGRAM_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        PROGRAM_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_program_dictionary(dictionary)
    count, _ = _read_awards(archive, release.data_member or "")
    records = []
    with ZipFile(archive) as zipped, zipped.open(release.data_member or "") as stream:
        for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")):
            raw = row["CTOTALT"].strip()
            value = int(raw) if raw else None
            available = value is not None and value >= 0
            records.append(
                {
                    "unitid": int(row["UNITID"]),
                    "cip_code": row["CIPCODE"].strip(),
                    "major_number": int(row["MAJORNUM"]),
                    "award_level": int(row["AWLEVEL"]),
                    "cip_version": "2020",
                    "is_aggregate_cip": row["CIPCODE"].strip() == "99",
                    "award_count": value if available else None,
                    "raw_award_count": raw,
                    "source_status": row["XCTOTALT"].strip() or None,
                    "unavailable_reason": None if available else "missing or negative source count",
                    "release_id": release.release_id,
                    "publication_status": release.publication_status.value,
                    "period_start": "2022-07-01",
                    "period_end": "2023-06-30",
                    "data_artifact_id": data_manifest.artifact_id,
                    "dictionary_artifact_id": dictionary_manifest.artifact_id,
                    "transformation_version": VERSION,
                }
            )
    schema = {
        "unitid": pl.Int64,
        "cip_code": pl.String,
        "major_number": pl.Int64,
        "award_level": pl.Int64,
        "cip_version": pl.String,
        "is_aggregate_cip": pl.Boolean,
        "award_count": pl.Int64,
        "raw_award_count": pl.String,
        "source_status": pl.String,
        "unavailable_reason": pl.String,
        "release_id": pl.String,
        "publication_status": pl.String,
        "period_start": pl.String,
        "period_end": pl.String,
        "data_artifact_id": pl.String,
        "dictionary_artifact_id": pl.String,
        "transformation_version": pl.String,
    }
    frame = pl.DataFrame(records, schema=schema).sort(KEYS)
    if frame.height != count:
        raise IPEDSProcessedArtifactConflict("program row count changed during transformation")
    relative = (
        Path(PROGRAM_DATA.dataset_id)
        / release.release_id
        / data_manifest.sha256
        / dictionary_manifest.sha256
        / VERSION
        / "program-awards.parquet"
    )
    destination = output_root / relative
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="ipeds-program-", suffix=".partial", dir=output_root)
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
            "cip_version": "2020",
            "period_start": "2022-07-01",
            "period_end": "2023-06-30",
            "transformation_version": VERSION,
        },
    )
    manifest = IPEDSProgramAwardsProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        cip_version="2020",
        period_start="2022-07-01",
        period_end="2023-06-30",
        row_count=frame.height,
        columns=tuple(frame.columns),
        key_columns=KEYS,
        output_path=relative.as_posix(),
    )
    manifest_path = destination.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = IPEDSProgramAwardsProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if existing.model_dump(exclude={"transformation": {"created_at"}}) != manifest.model_dump(
            exclude={"transformation": {"created_at"}}
        ):
            raise IPEDSProcessedArtifactConflict(f"program manifest differs: {manifest_path}")
        return ProcessedProgramAwards(destination, manifest_path, existing)
    payload = json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-program-manifest-", suffix=".partial", dir=output_root
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
    return ProcessedProgramAwards(destination, manifest_path, manifest)
