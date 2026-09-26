"""Verify a processed SFA2223 table and resolve one exact net-price population."""

import json
from pathlib import Path

import polars as pl
from pydantic import Field, ValidationError

from education_roi.ipeds.net_price import FIELDS, NET_PRICE_DATA, NetPriceBasis
from education_roi.ipeds.net_price_pipeline import (
    BASIS_FIELDS,
    COLUMNS,
    VERSION,
    IPEDSNetPriceProcessingManifest,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel


class IPEDSNetPriceTableError(ValueError):
    """Invalid processed net-price table or lineage."""


class NetPriceEvidence(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    basis: NetPriceBasis
    source_field: str
    average_net_price: int | None
    raw_average_net_price: str | None
    source_status: str | None
    reason: str | None
    release_id: str
    publication_status: str
    aid_year: str
    data_artifact_id: str
    dictionary_artifact_id: str
    transformation_version: str
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation: str = (
        "Historical institutional average for a selected aid-recipient group. "
        "Already reflects qualifying grants; not a student-specific offer or tuition alone."
    )


def resolve_net_price_evidence(path: Path, unitid: int, basis: NetPriceBasis) -> NetPriceEvidence:
    """Validate complete table and sidecar before selecting one institution and basis."""
    if unitid <= 0:
        raise ValueError("UNITID must be positive")
    if not isinstance(basis, NetPriceBasis):
        raise ValueError("requires an explicit net-price population basis")
    sidecar = path.with_suffix(".manifest.json")
    try:
        manifest = IPEDSNetPriceProcessingManifest.model_validate_json(
            sidecar.read_text(encoding="utf-8")
        )
        table_hash = sha256_file(path)[0]
        manifest_hash = sha256_file(sidecar)[0]
        if table_hash != manifest.transformation.output_sha256:
            raise IPEDSNetPriceTableError("net-price table hash differs from manifest")
        frame = pl.read_parquet(path)
    except (OSError, UnicodeError, ValidationError, pl.exceptions.PolarsError) as error:
        raise IPEDSNetPriceTableError(f"could not verify net-price table: {error}") from error
    parameters = manifest.transformation.parameters
    path_parts = Path(manifest.output_path).parts
    if (
        manifest.release_id != "2023-24-final"
        or manifest.publication_status != "final"
        or manifest.aid_year != "2022-23"
        or manifest.key_columns != ("unitid",)
        or parameters.get("data_member") != "sfa2223_RV.csv"
        or parameters.get("aid_year") != manifest.aid_year
        or parameters.get("basis_fields") != json.dumps(dict(BASIS_FIELDS), sort_keys=True)
        or parameters.get("transformation_version") != VERSION
        or len(path_parts) != 6
        or path_parts[0] != NET_PRICE_DATA.dataset_id
        or path_parts[1] != manifest.release_id
        or any(
            len(component) != 64 or any(char not in "0123456789abcdef" for char in component)
            for component in path_parts[2:4]
        )
        or path_parts[4:] != (VERSION, "net-price.parquet")
        or manifest.transformation.transformation_id
        != (f"{VERSION}:{manifest.release_id}:{path_parts[2]}:{path_parts[3]}:{table_hash}")
        or not (
            manifest.output_path == path.name
            or path.as_posix().endswith("/" + manifest.output_path)
        )
    ):
        raise IPEDSNetPriceTableError("unsupported net-price release, definitions or path")
    if (
        not frame.height
        or frame.height != manifest.row_count
        or tuple(frame.columns) != COLUMNS
        or manifest.columns != COLUMNS
        or len(manifest.transformation.input_artifact_ids) != 2
    ):
        raise IPEDSNetPriceTableError("net-price table schema, count or lineage differs")
    data_id, dictionary_id = manifest.transformation.input_artifact_ids
    previous_unitid = 0
    selected = None
    for row in frame.iter_rows(named=True):
        row_id = row["unitid"]
        if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id <= previous_unitid:
            raise IPEDSNetPriceTableError("net-price UNITIDs are invalid, duplicated or unordered")
        previous_unitid = row_id
        if (
            row["release_id"] != manifest.release_id
            or row["publication_status"] != manifest.publication_status
            or row["aid_year"] != manifest.aid_year
            or row["data_artifact_id"] != data_id
            or row["dictionary_artifact_id"] != dictionary_id
            or row["transformation_version"] != VERSION
        ):
            raise IPEDSNetPriceTableError("net-price row definitions or lineage differ")
        for name, _ in BASIS_FIELDS:
            raw = row[f"raw_{name}"]
            source_status = row[f"status_{name}"]
            if not isinstance(raw, str) or not isinstance(source_status, str):
                raise IPEDSNetPriceTableError("net-price source cells must be strings")
            try:
                parsed = int(raw) if raw else None
            except ValueError as error:
                raise IPEDSNetPriceTableError("invalid raw net-price cell") from error
            expected = parsed if parsed is not None and parsed >= 0 else None
            if row[name] != expected or (
                row[name] is not None
                and (not isinstance(row[name], int) or isinstance(row[name], bool))
            ):
                raise IPEDSNetPriceTableError("net-price source cell or availability differs")
        if row_id == unitid:
            selected = row
    name = basis.value
    value = selected[name] if selected else None
    return NetPriceEvidence(
        status="OBSERVED" if value is not None else "INSUFFICIENT_DATA",
        unitid=unitid,
        basis=basis,
        source_field=FIELDS[basis][0],
        average_net_price=value,
        raw_average_net_price=selected[f"raw_{name}"] if selected else None,
        source_status=selected[f"status_{name}"] if selected else None,
        reason=None if value is not None else "source row absent or net price unavailable",
        release_id=manifest.release_id,
        publication_status=manifest.publication_status,
        aid_year=manifest.aid_year,
        data_artifact_id=data_id,
        dictionary_artifact_id=dictionary_id,
        transformation_version=VERSION,
        table_sha256=table_hash,
        manifest_sha256=manifest_hash,
    )
