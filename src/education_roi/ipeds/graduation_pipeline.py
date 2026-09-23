"""Immutable, source-paired final GR2023 bachelor's cohort table."""

import csv
import io
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from education_roi import __version__
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSPublicationStatus, IPEDSRelease
from education_roi.ipeds.graduation import (
    GR2023_DATASET_ID,
    GR2023_DICTIONARY_DATASET_ID,
    REQUIRED_GR_COLUMNS,
    ROW_CODES,
    IPEDSGraduationError,
    _verify_dictionary,
    _verify_manifest,
)
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict, _publish_immutable
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

GR_TRANSFORMATION_VERSION = "ipeds-gr2023-bachelors-v1"


class IPEDSGraduationProcessingManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    publication_status: str
    cohort_year: int
    cohort_scope: str
    award_outcome: str
    normal_time_percent: int
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ProcessedIPEDSGraduation:
    parquet_path: Path
    manifest_path: Path
    manifest: IPEDSGraduationProcessingManifest


def _count(cell: str | None) -> int | None:
    if cell is None or not cell.strip():
        return None
    try:
        value = int(cell)
    except ValueError as error:
        raise IPEDSGraduationError(f"invalid GR2023 total count {cell!r}") from error
    return value if value >= 0 else None


def _frame(archive: Path, release: IPEDSRelease, data_id: str, dictionary_id: str) -> pl.DataFrame:
    selected: dict[int, dict[str, dict[str, str]]] = {}
    try:
        with ZipFile(archive) as source:
            if release.data_member not in source.namelist():
                raise IPEDSGraduationError(f"GR2023 archive is missing {release.data_member}")
            with source.open(release.data_member) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
                missing = REQUIRED_GR_COLUMNS.difference(reader.fieldnames or ())
                if missing:
                    raise IPEDSGraduationError(
                        "GR2023 archive is missing columns: " + ", ".join(sorted(missing))
                    )
                for number, row in enumerate(reader, start=2):
                    if row["GRTYPE"] not in ROW_CODES or row["SECTION"] != "2":
                        continue
                    try:
                        unitid = int(row["UNITID"])
                    except (ValueError, TypeError) as error:
                        raise IPEDSGraduationError(
                            f"invalid UNITID on GR2023 row {number}"
                        ) from error
                    if unitid <= 0:
                        raise IPEDSGraduationError(f"invalid UNITID on GR2023 row {number}")
                    code = row["GRTYPE"]
                    status, line = ROW_CODES[code]
                    if (row["CHRTSTAT"], row["COHORT"], row["LINE"]) != (status, "2", line):
                        raise IPEDSGraduationError(f"incompatible GR2023 keys on row {number}")
                    group = selected.setdefault(unitid, {})
                    if code in group:
                        raise IPEDSGraduationError(
                            f"duplicate GR2023 row {code} for UNITID {unitid}"
                        )
                    group[code] = row
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSGraduationError(f"could not read GR2023 archive: {error}") from error
    if not selected:
        raise IPEDSGraduationError("GR2023 archive has no bachelor's cohort rows")
    records = []
    for unitid, rows in sorted(selected.items()):
        cohort = rows.get("8")
        award = rows.get("12")
        denominator = _count(cohort["GRTOTLT"]) if cohort else None
        numerator = _count(award["GRTOTLT"]) if award else None
        if denominator is not None and numerator is not None and numerator > denominator:
            raise IPEDSGraduationError(f"bachelor's awards exceed cohort for UNITID {unitid}")
        if cohort is None or award is None:
            reason = "missing cohort or award row"
        elif denominator is None or numerator is None:
            reason = "blank or negative count"
        elif denominator == 0:
            reason = "zero adjusted cohort"
        else:
            reason = None
        records.append(
            {
                "unitid": unitid,
                "release_id": release.release_id,
                "publication_status": release.publication_status.value,
                "cohort_year": 2017,
                "cohort_scope": "bachelors_seeking_first_time_full_time",
                "award_outcome": "bachelors_degree",
                "normal_time_percent": 150,
                "adjusted_cohort": denominator,
                "bachelors_awards": numerator,
                "observed_rate": (
                    numerator / denominator
                    if reason is None and numerator is not None and denominator is not None
                    else None
                ),
                "unavailable_reason": reason,
                "raw_adjusted_cohort": cohort["GRTOTLT"] if cohort else None,
                "raw_bachelors_awards": award["GRTOTLT"] if award else None,
                "cohort_status": cohort["XGRTOTLT"] if cohort else None,
                "award_status": award["XGRTOTLT"] if award else None,
                "cohort_row_key": "COHORT=2;SECTION=2;GRTYPE=8" if cohort else None,
                "award_row_key": "COHORT=2;SECTION=2;GRTYPE=12" if award else None,
                "data_artifact_id": data_id,
                "dictionary_artifact_id": dictionary_id,
                "transformation_version": GR_TRANSFORMATION_VERSION,
            }
        )
    schema = {
        "unitid": pl.Int64,
        "release_id": pl.String,
        "publication_status": pl.String,
        "cohort_year": pl.Int32,
        "cohort_scope": pl.String,
        "award_outcome": pl.String,
        "normal_time_percent": pl.Int32,
        "adjusted_cohort": pl.Int64,
        "bachelors_awards": pl.Int64,
        "observed_rate": pl.Float64,
        "unavailable_reason": pl.String,
        "raw_adjusted_cohort": pl.String,
        "raw_bachelors_awards": pl.String,
        "cohort_status": pl.String,
        "award_status": pl.String,
        "cohort_row_key": pl.String,
        "award_row_key": pl.String,
        "data_artifact_id": pl.String,
        "dictionary_artifact_id": pl.String,
        "transformation_version": pl.String,
    }
    return pl.DataFrame(records, schema=schema)


def transform_gr2023_archive(
    archive: Path,
    dictionary: Path,
    output_root: Path,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    release: IPEDSRelease,
) -> ProcessedIPEDSGraduation:
    """Build an immutable final cohort table from exactly paired validated inputs."""
    if (
        release.component is not IPEDSComponent.GRADUATION_RATES
        or release.release_id != "2023-24-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "gr2023_RV.csv"
    ):
        raise IPEDSGraduationError("requires reviewed final GR2023_RV release")
    _verify_manifest(archive, data_manifest, release, GR2023_DATASET_ID, str(release.data_url))
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        GR2023_DICTIONARY_DATASET_ID,
        str(release.dictionary_url),
    )
    _verify_dictionary(dictionary)
    frame = _frame(archive, release, data_manifest.artifact_id, dictionary_manifest.artifact_id)
    relative_directory = (
        Path(GR2023_DATASET_ID)
        / release.release_id
        / data_manifest.sha256
        / dictionary_manifest.sha256
        / GR_TRANSFORMATION_VERSION
    )
    relative = relative_directory / "bachelors.parquet"
    destination = output_root / relative
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="ipeds-gr2023-", suffix=".partial", dir=output_root
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.write_parquet(temporary, compression="zstd", statistics=True, row_group_size=100_000)
        _publish_immutable(temporary, destination)
        output_hash, _ = sha256_file(destination)
    finally:
        temporary.unlink(missing_ok=True)

    transformation = TransformationManifest(
        transformation_id=(
            f"{GR_TRANSFORMATION_VERSION}:{release.release_id}:"
            f"{data_manifest.sha256}:{dictionary_manifest.sha256}:{output_hash}"
        ),
        created_at=datetime.now(UTC),
        software_version=__version__,
        output_sha256=output_hash,
        input_artifact_ids=(data_manifest.artifact_id, dictionary_manifest.artifact_id),
        parameters={
            "data_member": release.data_member,
            "cohort_year": 2017,
            "cohort_scope": "bachelors_seeking_first_time_full_time",
            "award_outcome": "bachelors_degree",
            "normal_time_percent": 150,
            "transformation_version": GR_TRANSFORMATION_VERSION,
        },
    )
    processing = IPEDSGraduationProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        cohort_year=2017,
        cohort_scope="bachelors_seeking_first_time_full_time",
        award_outcome="bachelors_degree",
        normal_time_percent=150,
        row_count=frame.height,
        columns=tuple(frame.columns),
        output_path=relative.as_posix(),
    )
    manifest_path = destination.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = IPEDSGraduationProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            existing.transformation.output_sha256 != output_hash
            or existing.transformation.input_artifact_ids
            != (data_manifest.artifact_id, dictionary_manifest.artifact_id)
            or existing.output_path != relative.as_posix()
        ):
            raise IPEDSProcessedArtifactConflict(f"processed GR manifest differs: {manifest_path}")
        return ProcessedIPEDSGraduation(destination, manifest_path, existing)
    payload = json.dumps(processing.model_dump(mode="json"), indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="ipeds-gr-manifest-", suffix=".partial", dir=output_root
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    temp_manifest = Path(temporary_name)
    try:
        _publish_immutable(temp_manifest, manifest_path)
    finally:
        temp_manifest.unlink(missing_ok=True)
    return ProcessedIPEDSGraduation(destination, manifest_path, processing)
