"""Immutable IC2023 expense estimates with exact data and dictionary lineage."""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from education_roi import __version__
from education_roi.ipeds.archive import IPEDSArchiveError, parse_nonnegative_cost, read_charge_rows
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSPublicationStatus, IPEDSRelease
from education_roi.ipeds.expenses import (
    EXPENSE_LABELS,
    IPEDSExpenseError,
    _verify_dictionary,
    _verify_source,
)
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict, _publish_immutable
from education_roi.ipeds.source import IPEDS_CHARGES_DATASET, IPEDS_DICTIONARY_DATASET
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

EXPENSE_TRANSFORMATION_VERSION = "ipeds-ic2023-expenses-v1"
EXPENSE_COLUMNS = {
    "CHG5AY3": "on_campus_food_housing",
    "CHG6AY3": "on_campus_other",
    "CHG7AY3": "off_campus_food_housing",
    "CHG8AY3": "off_campus_other",
    "CHG9AY3": "with_family_other",
}


class IPEDSExpensesProcessingManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    publication_status: str
    population: str
    reporting_basis: str
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    source_columns: dict[str, str]
    output_path: str


@dataclass(frozen=True)
class ProcessedIPEDSExpenses:
    parquet_path: Path
    manifest_path: Path
    manifest: IPEDSExpensesProcessingManifest


def _expense_frame(
    rows: dict[int, dict[str, str]],
    release: IPEDSRelease,
    data_id: str,
    dictionary_id: str,
) -> pl.DataFrame:
    required = set(EXPENSE_LABELS) | {"X" + code for code in EXPENSE_LABELS}
    if not rows or not required.issubset(next(iter(rows.values()))):
        raise IPEDSExpenseError("IC2023_AY archive lacks expense or source-status columns")
    records = []
    for unitid, row in sorted(rows.items()):
        record: dict[str, str | int | float | None] = {
            "unitid": unitid,
            "release_id": release.release_id,
            "publication_status": release.publication_status.value,
            "population": "full_time_first_time_undergraduate",
            "reporting_basis": "academic_year",
            "data_artifact_id": data_id,
            "dictionary_artifact_id": dictionary_id,
            "transformation_version": EXPENSE_TRANSFORMATION_VERSION,
        }
        for source, target in EXPENSE_COLUMNS.items():
            try:
                record[target] = parse_nonnegative_cost(row[source])
            except IPEDSArchiveError as error:
                raise IPEDSExpenseError(f"{source} for UNITID {unitid}: {error}") from error
            record["raw_" + target] = row[source]
            record["status_" + target] = row["X" + source] or None
        records.append(record)
    schema: dict[str, type[pl.DataType]] = {
        "unitid": pl.Int64,
        "release_id": pl.String,
        "publication_status": pl.String,
        "population": pl.String,
        "reporting_basis": pl.String,
        "data_artifact_id": pl.String,
        "dictionary_artifact_id": pl.String,
        "transformation_version": pl.String,
    }
    for target in EXPENSE_COLUMNS.values():
        schema[target] = pl.Float64
        schema["raw_" + target] = pl.String
        schema["status_" + target] = pl.String
    return pl.DataFrame(records, schema=schema)


def transform_ic2023_expenses(
    archive: Path,
    dictionary: Path,
    output_root: Path,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    release: IPEDSRelease,
) -> ProcessedIPEDSExpenses:
    """Build a paired, immutable institution table without synthesizing net or incremental costs."""
    if (
        release.component is not IPEDSComponent.ACADEMIC_YEAR_CHARGES
        or release.release_id != "2023-24-provisional"
        or release.publication_status is not IPEDSPublicationStatus.PROVISIONAL
    ):
        raise IPEDSExpenseError("requires reviewed provisional IC2023_AY release")
    _verify_source(
        archive, data_manifest, release, IPEDS_CHARGES_DATASET.dataset_id, str(release.data_url)
    )
    _verify_source(
        dictionary,
        dictionary_manifest,
        release,
        IPEDS_DICTIONARY_DATASET.dataset_id,
        str(release.dictionary_url),
    )
    _verify_dictionary(dictionary)
    frame = _expense_frame(
        read_charge_rows(archive),
        release,
        data_manifest.artifact_id,
        dictionary_manifest.artifact_id,
    )
    relative = (
        Path(IPEDS_CHARGES_DATASET.dataset_id)
        / release.release_id
        / data_manifest.sha256
        / dictionary_manifest.sha256
        / EXPENSE_TRANSFORMATION_VERSION
        / "expenses.parquet"
    )
    destination = output_root / relative
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-expenses-", suffix=".partial", dir=output_root
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
            f"{EXPENSE_TRANSFORMATION_VERSION}:{release.release_id}:"
            f"{data_manifest.sha256}:{dictionary_manifest.sha256}:{output_hash}"
        ),
        created_at=datetime.now(UTC),
        software_version=__version__,
        output_sha256=output_hash,
        input_artifact_ids=(data_manifest.artifact_id, dictionary_manifest.artifact_id),
        parameters={
            "population": "full_time_first_time_undergraduate",
            "reporting_basis": "academic_year",
            "transformation_version": EXPENSE_TRANSFORMATION_VERSION,
        },
    )
    manifest = IPEDSExpensesProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        population="full_time_first_time_undergraduate",
        reporting_basis="academic_year",
        row_count=frame.height,
        columns=tuple(frame.columns),
        source_columns={target: source for source, target in EXPENSE_COLUMNS.items()},
        output_path=relative.as_posix(),
    )
    manifest_path = destination.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = IPEDSExpensesProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            existing.transformation.output_sha256 != output_hash
            or existing.transformation.input_artifact_ids
            != (data_manifest.artifact_id, dictionary_manifest.artifact_id)
            or existing.transformation.transformation_id
            != manifest.transformation.transformation_id
            or existing.transformation.parameters != manifest.transformation.parameters
            or existing.release_id != manifest.release_id
            or existing.publication_status != manifest.publication_status
            or existing.population != manifest.population
            or existing.reporting_basis != manifest.reporting_basis
            or existing.row_count != manifest.row_count
            or existing.output_path != relative.as_posix()
            or existing.columns != tuple(frame.columns)
            or existing.source_columns != manifest.source_columns
        ):
            raise IPEDSProcessedArtifactConflict(
                f"processed expense manifest differs: {manifest_path}"
            )
        return ProcessedIPEDSExpenses(destination, manifest_path, existing)
    payload = json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-expenses-manifest-", suffix=".partial", dir=output_root
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    temporary_manifest = Path(name)
    try:
        _publish_immutable(temporary_manifest, manifest_path)
    finally:
        temporary_manifest.unlink(missing_ok=True)
    return ProcessedIPEDSExpenses(destination, manifest_path, manifest)
