"""Verify a processed C2022_A or C2023_A exact program award cell."""

from pathlib import Path

import polars as pl
from pydantic import Field, ValidationError

from education_roi.ipeds.program_awards import (
    CIP_PATTERN,
    PROGRAM_DATA,
    PROGRAM_DATA_2022,
    PROGRAM_DICTIONARY,
    PROGRAM_DICTIONARY_2022,
)
from education_roi.ipeds.program_awards_pipeline import (
    KEYS,
    VERSION,
    VERSION_2022,
    IPEDSProgramAwardsProcessingManifest,
)
from education_roi.ipeds.program_awards_status import interpret_award_status
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel

EXPECTED_COLUMNS = (
    "unitid",
    "cip_code",
    "major_number",
    "award_level",
    "cip_version",
    "is_aggregate_cip",
    "award_count",
    "raw_award_count",
    "source_status",
    "unavailable_reason",
    "release_id",
    "publication_status",
    "period_start",
    "period_end",
    "data_artifact_id",
    "dictionary_artifact_id",
    "transformation_version",
)


class IPEDSProgramAwardsTableError(ValueError):
    """Invalid processed award table, source cells, or manifest lineage."""


class ProgramAwardEvidence(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    cip_code: str
    cip_version: str
    major_number: int
    award_level: int
    award_count: int | None
    raw_award_count: str | None
    source_status: str | None
    source_status_label: str | None
    source_status_review_required: bool
    unavailable_reason: str | None
    release_id: str
    publication_status: str
    period_start: str
    period_end: str
    data_artifact_id: str
    dictionary_artifact_id: str
    transformation_version: str
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation: str = (
        "Awards conferred at an exact institution, CIP 2020 code, major number, and "
        "award level. Not distinct graduates or a program completion probability."
    )


def resolve_program_awards_evidence(
    path: Path, unitid: int, cip_code: str, major_number: int, award_level: int
) -> ProgramAwardEvidence:
    """Validate the complete table and adjacent sidecar before returning one exact row."""
    if (
        unitid <= 0
        or not CIP_PATTERN.fullmatch(cip_code)
        or major_number not in (1, 2)
        or award_level <= 0
    ):
        raise ValueError("requires positive UNITID, six-digit CIP, major 1/2 and award level")
    sidecar = path.with_suffix(".manifest.json")
    try:
        manifest = IPEDSProgramAwardsProcessingManifest.model_validate_json(
            sidecar.read_text(encoding="utf-8")
        )
        table_hash = sha256_file(path)[0]
        manifest_hash = sha256_file(sidecar)[0]
        if table_hash != manifest.transformation.output_sha256:
            raise IPEDSProgramAwardsTableError("program table hash differs from manifest")
        frame = pl.read_parquet(path)
    except (OSError, UnicodeError, ValidationError, pl.exceptions.PolarsError) as error:
        raise IPEDSProgramAwardsTableError(f"could not verify program table: {error}") from error
    parameters = manifest.transformation.parameters
    path_parts = Path(manifest.output_path).parts
    configurations = {
        "2022-23-final": (
            PROGRAM_DATA_2022.dataset_id,
            PROGRAM_DICTIONARY_2022.dataset_id,
            VERSION_2022,
            "c2022_a_rv.csv",
            ("2021-07-01", "2022-06-30"),
        ),
        "2023-24-final": (
            PROGRAM_DATA.dataset_id,
            PROGRAM_DICTIONARY.dataset_id,
            VERSION,
            "C2023_a_RV.csv",
            ("2022-07-01", "2023-06-30"),
        ),
    }
    if manifest.release_id not in configurations:
        raise IPEDSProgramAwardsTableError("unsupported program release")
    dataset_id, dictionary_dataset_id, version, member, period = configurations[manifest.release_id]
    if (
        manifest.publication_status != "final"
        or manifest.cip_version != "2020"
        or (manifest.period_start, manifest.period_end) != period
        or manifest.key_columns != KEYS
        or parameters.get("data_member") != member
        or parameters.get("cip_version") != "2020"
        or parameters.get("period_start") != manifest.period_start
        or parameters.get("period_end") != manifest.period_end
        or parameters.get("transformation_version") != version
        or len(path_parts) != 6
        or path_parts[0] != dataset_id
        or path_parts[1] != manifest.release_id
        or any(
            len(component) != 64 or any(char not in "0123456789abcdef" for char in component)
            for component in path_parts[2:4]
        )
        or path_parts[4:] != (version, "program-awards.parquet")
        or manifest.transformation.transformation_id
        != (f"{version}:{manifest.release_id}:{path_parts[2]}:{path_parts[3]}:{table_hash}")
        or not (
            manifest.output_path == path.name
            or path.as_posix().endswith("/" + manifest.output_path)
        )
    ):
        raise IPEDSProgramAwardsTableError("unsupported program release, definitions or path")
    if (
        not frame.height
        or frame.height != manifest.row_count
        or tuple(frame.columns) != EXPECTED_COLUMNS
        or manifest.columns != EXPECTED_COLUMNS
        or len(manifest.transformation.input_artifact_ids) != 2
    ):
        raise IPEDSProgramAwardsTableError("program table schema, count or lineage differs")
    data_id, dictionary_id = manifest.transformation.input_artifact_ids
    if (
        data_id != f"{dataset_id}:{manifest.release_id}:{path_parts[2]}"
        or dictionary_id != f"{dictionary_dataset_id}:{manifest.release_id}:{path_parts[3]}"
    ):
        raise IPEDSProgramAwardsTableError("program source artifacts differ from output path")
    previous_key: tuple[int, str, int, int] | None = None
    selected = None
    target = (unitid, cip_code, major_number, award_level)
    for row in frame.iter_rows(named=True):
        key = (row["unitid"], row["cip_code"], row["major_number"], row["award_level"])
        if (
            not isinstance(key[0], int)
            or key[0] <= 0
            or not isinstance(key[1], str)
            or (not CIP_PATTERN.fullmatch(key[1]) and key[1] != "99")
            or key[2] not in (1, 2)
            or not isinstance(key[3], int)
            or key[3] <= 0
            or (previous_key is not None and key <= previous_key)
        ):
            raise IPEDSProgramAwardsTableError("program keys are invalid, duplicated or unordered")
        previous_key = key
        if (
            row["cip_version"] != manifest.cip_version
            or row["is_aggregate_cip"] is not (key[1] == "99")
            or row["release_id"] != manifest.release_id
            or row["publication_status"] != manifest.publication_status
            or row["period_start"] != manifest.period_start
            or row["period_end"] != manifest.period_end
            or row["transformation_version"] != version
            or row["data_artifact_id"] != data_id
            or row["dictionary_artifact_id"] != dictionary_id
            or not isinstance(row["raw_award_count"], str)
            or row["source_status"] is not None
            and not isinstance(row["source_status"], str)
        ):
            raise IPEDSProgramAwardsTableError("program row definitions or lineage differ")
        raw = row["raw_award_count"]
        try:
            parsed = int(raw) if raw else None
        except ValueError as error:
            raise IPEDSProgramAwardsTableError("invalid raw award count") from error
        expected = parsed if parsed is not None and parsed >= 0 else None
        reason = None if expected is not None else "missing or negative source count"
        if row["award_count"] != expected or row["unavailable_reason"] != reason:
            raise IPEDSProgramAwardsTableError("program source cell or availability differs")
        if key == target:
            selected = row
    source_status = selected["source_status"] if selected else None
    source_interpretation = interpret_award_status(source_status, manifest.release_id)
    return ProgramAwardEvidence(
        status="OBSERVED"
        if selected and selected["unavailable_reason"] is None
        else "INSUFFICIENT_DATA",
        unitid=unitid,
        cip_code=cip_code,
        cip_version=manifest.cip_version,
        major_number=major_number,
        award_level=award_level,
        award_count=selected["award_count"] if selected else None,
        raw_award_count=selected["raw_award_count"] if selected else None,
        source_status=source_status,
        source_status_label=source_interpretation.label,
        source_status_review_required=source_interpretation.review_required,
        unavailable_reason=(
            selected["unavailable_reason"] if selected else "exact program key absent from table"
        ),
        release_id=manifest.release_id,
        publication_status=manifest.publication_status,
        period_start=manifest.period_start,
        period_end=manifest.period_end,
        data_artifact_id=data_id,
        dictionary_artifact_id=dictionary_id,
        transformation_version=version,
        table_sha256=table_hash,
        manifest_sha256=manifest_hash,
    )
