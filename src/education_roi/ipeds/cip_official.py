"""Build a directional CIP 2010→2020 mapping from the reviewed NCES CSV."""

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from education_roi.ipeds.cip import (
    CIPCrosswalk,
    CIPCrosswalkError,
    CIPMapping,
    CIPMappingConfidence,
    CIPRelationship,
)
from education_roi.provenance.integrity import sha256_file

SOURCE_URL = "https://nces.ed.gov/ipeds/cipcode/resources.aspx?y=56"
SOURCE_SHA256 = "3aa75a01b38169b3093f17a15bc3e72d769192ef3fed8935b12215bc4ca087c7"
COLUMNS = (
    "CIPCode2010",
    "CIPTitle2010",
    "Action",
    "Text change",
    "CIPCode2020",
    "CIPTitle2020",
)
CODE = re.compile(r"=\"(\d{2}(?:\.\d{2,4})?)\"")
ACTION_COUNTS = {
    "No substantive changes": 1994,
    "Moved to": 149,
    "Deleted": 12,
    "New": 544,
}


@dataclass(frozen=True)
class ImportedCIPCrosswalk:
    crosswalk: CIPCrosswalk
    source_rows: int
    omitted_deleted: int
    omitted_new: int


def _code(raw: str) -> str:
    match = CODE.fullmatch(raw)
    if match is None:
        raise CIPCrosswalkError(f"invalid NCES spreadsheet-formatted CIP code {raw!r}")
    return match.group(1)


def import_official_cip_crosswalk(path: Path) -> ImportedCIPCrosswalk:
    """Validate every official row; omit new/deleted codes rather than invent matches."""
    try:
        digest, _ = sha256_file(path)
        if digest != SOURCE_SHA256:
            raise CIPCrosswalkError("NCES CIP CSV differs from reviewed source SHA-256")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise CIPCrosswalkError("NCES CIP CSV columns differ from reviewed source")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise CIPCrosswalkError(f"could not read NCES CIP CSV: {error}") from error
    counts = {action: 0 for action in ACTION_COUNTS}
    mappings = []
    sources: set[str] = set()
    targets: set[str] = set()
    for index, row in enumerate(rows, 2):
        if None in row or any(row.get(column) is None for column in COLUMNS):
            raise CIPCrosswalkError(f"malformed NCES CIP row {index}")
        action = row["Action"]
        if action not in counts or row["Text change"] not in {"yes", "no"}:
            raise CIPCrosswalkError(f"unknown NCES CIP action or text change on row {index}")
        counts[action] += 1
        target = _code(row["CIPCode2020"])
        if target in targets:
            raise CIPCrosswalkError(f"duplicate NCES CIP 2020 code {target}")
        targets.add(target)
        source = _code(row["CIPCode2010"]) if row["CIPCode2010"] else None
        if action == "New":
            if source is not None or row["CIPTitle2010"]:
                raise CIPCrosswalkError(f"new NCES CIP code has a 2010 source on row {index}")
            continue
        if source is None or source in sources:
            raise CIPCrosswalkError(f"missing or duplicate NCES CIP 2010 code on row {index}")
        sources.add(source)
        if not row["CIPTitle2010"] or not row["CIPTitle2020"]:
            raise CIPCrosswalkError(f"missing NCES CIP title on row {index}")
        if action == "Deleted":
            if source != target:
                raise CIPCrosswalkError(f"deleted NCES CIP code changed key on row {index}")
            continue
        if (action == "No substantive changes") != (source == target):
            raise CIPCrosswalkError(f"NCES CIP action and code differ on row {index}")
        mappings.append(
            CIPMapping(
                source_code=source,
                target_code=target,
                relationship=(
                    CIPRelationship.EXACT
                    if action == "No substantive changes"
                    else CIPRelationship.REVISED
                ),
                confidence=(
                    CIPMappingConfidence.HIGH
                    if action == "No substantive changes"
                    else CIPMappingConfidence.MEDIUM
                ),
                note=(
                    "NCES: no substantive changes"
                    + ("; text changed" if row["Text change"] == "yes" else "")
                    if action == "No substantive changes"
                    else "NCES: moved to"
                    + ("; text changed" if row["Text change"] == "yes" else "")
                ),
            )
        )
    if counts != ACTION_COUNTS or len(mappings) != sum(
        ACTION_COUNTS[action] for action in ("No substantive changes", "Moved to")
    ):
        raise CIPCrosswalkError("NCES CIP action counts differ from reviewed source")
    crosswalk = CIPCrosswalk.model_validate(
        {
            "crosswalk_id": "nces-cip-2010-to-2020-reviewed-2026-09",
            "source_version": "2010",
            "target_version": "2020",
            "source_url": SOURCE_URL,
            "source_sha256": digest,
            "mappings": tuple(sorted(mappings, key=lambda item: item.source_code)),
        }
    )
    return ImportedCIPCrosswalk(crosswalk, len(rows), counts["Deleted"], counts["New"])


def write_official_cip_crosswalk(path: Path, destination: Path) -> ImportedCIPCrosswalk:
    """Write canonical, immutable JSON for the validated directional mapping."""
    result = import_official_cip_crosswalk(path)
    payload = json.dumps(result.crosswalk.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if destination.exists():
        try:
            existing = destination.read_text(encoding="utf-8")
        except OSError as error:
            raise CIPCrosswalkError(f"could not read existing crosswalk: {error}") from error
        if existing != payload:
            raise CIPCrosswalkError("existing CIP crosswalk differs from reviewed source")
        return result
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8") as output:
            output.write(payload)
    except FileExistsError as error:
        raise CIPCrosswalkError("CIP crosswalk was created concurrently") from error
    return result
