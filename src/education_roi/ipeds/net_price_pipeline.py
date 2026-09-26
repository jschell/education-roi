"""Immutable, source-paired final SFA2223 institution net-price table."""

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
from education_roi.ipeds.net_price import (
    FIELDS,
    NET_PRICE_DATA,
    NET_PRICE_DICTIONARY,
    _require_release,
    _verify_manifest,
    read_net_price_rows,
    verify_net_price_dictionary,
)
from education_roi.ipeds.pipeline import _publish_immutable
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest, TransformationManifest

VERSION = "ipeds-sfa2223-net-price-v1"
BASIS_FIELDS = tuple((basis.value, code) for basis, (code, *_) in FIELDS.items())
COLUMNS = (
    "unitid",
    *(item for basis, _ in BASIS_FIELDS for item in (basis, f"raw_{basis}", f"status_{basis}")),
    "release_id",
    "publication_status",
    "aid_year",
    "data_artifact_id",
    "dictionary_artifact_id",
    "transformation_version",
)


class IPEDSNetPriceProcessingManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    transformation: TransformationManifest
    release_id: str
    publication_status: str
    aid_year: str
    row_count: int = Field(ge=0)
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ProcessedNetPrice:
    parquet_path: Path
    manifest_path: Path
    manifest: IPEDSNetPriceProcessingManifest


def transform_net_price(
    archive: Path,
    dictionary: Path,
    output_root: Path,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    release: IPEDSRelease,
) -> ProcessedNetPrice:
    """Build one row per institution, retaining four separate aid populations."""
    _require_release(release)
    _verify_manifest(
        archive, data_manifest, release, NET_PRICE_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        NET_PRICE_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_net_price_dictionary(dictionary)
    rows = read_net_price_rows(archive, release.data_member or "")
    records = []
    for unitid, row in sorted(rows.items()):
        record: dict[str, int | str | None] = {"unitid": unitid}
        for basis, code in BASIS_FIELDS:
            raw = row[code]
            parsed = int(raw) if raw else None
            record[basis] = parsed if parsed is not None and parsed >= 0 else None
            record[f"raw_{basis}"] = raw
            record[f"status_{basis}"] = row["X" + code]
        record.update(
            release_id=release.release_id,
            publication_status=release.publication_status.value,
            aid_year="2022-23",
            data_artifact_id=data_manifest.artifact_id,
            dictionary_artifact_id=dictionary_manifest.artifact_id,
            transformation_version=VERSION,
        )
        records.append(record)
    schema: dict[str, type[pl.DataType]] = {"unitid": pl.Int64}
    for basis, _ in BASIS_FIELDS:
        schema.update({basis: pl.Int64, f"raw_{basis}": pl.String, f"status_{basis}": pl.String})
    schema.update({column: pl.String for column in COLUMNS if column not in schema})
    frame = pl.DataFrame(records, schema=schema)
    relative = (
        Path(NET_PRICE_DATA.dataset_id)
        / release.release_id
        / data_manifest.sha256
        / dictionary_manifest.sha256
        / VERSION
        / "net-price.parquet"
    )
    destination = output_root / relative
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-net-price-", suffix=".partial", dir=output_root
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
            "aid_year": "2022-23",
            "basis_fields": json.dumps(dict(BASIS_FIELDS), sort_keys=True),
            "transformation_version": VERSION,
        },
    )
    manifest = IPEDSNetPriceProcessingManifest(
        transformation=transformation,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        aid_year="2022-23",
        row_count=frame.height,
        columns=tuple(frame.columns),
        key_columns=("unitid",),
        output_path=relative.as_posix(),
    )
    manifest_path = destination.with_suffix(".manifest.json")
    if manifest_path.exists():
        existing = IPEDSNetPriceProcessingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if existing.model_dump(exclude={"transformation": {"created_at"}}) != manifest.model_dump(
            exclude={"transformation": {"created_at"}}
        ):
            from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict

            raise IPEDSProcessedArtifactConflict(f"net-price manifest differs: {manifest_path}")
        return ProcessedNetPrice(destination, manifest_path, existing)
    payload = json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    descriptor, name = tempfile.mkstemp(
        prefix="ipeds-net-price-manifest-", suffix=".partial", dir=output_root
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
    return ProcessedNetPrice(destination, manifest_path, manifest)
