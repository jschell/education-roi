"""Import documented 2022→2023 institution identity events from NCES directories."""

import csv
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

from education_roi.ipeds.identity import (
    InstitutionHistory,
    InstitutionHistoryEntry,
    InstitutionHistoryError,
    InstitutionMappingConfidence,
    InstitutionRelationship,
)
from education_roi.provenance.integrity import sha256_file

PREVIOUS_SHA256 = "e36389b793741bf6886b8d85fa9b42614644162b0d0b1d024a663a9c1865c782"
CURRENT_SHA256 = "e11d35af6f50fbe2f51d8ddd5a9d4f49860abbab7d73beae1f8524f13ad8945b"
DICTIONARY_SHA256 = "131d8f2f56a71078ea453989384cce91985fa2a29a94f168a718dedc6a466e3b"
SOURCE_URL = "https://nces.ed.gov/ipeds/datacenter/data/HD2023.zip"
REQUIRED = {"UNITID", "ACT", "NEWID", "DEATHYR", "CYACTIVE"}


def _rows(path: Path, digest: str, member: str, encoding: str) -> list[dict[str, str]]:
    if sha256_file(path)[0] != digest:
        raise InstitutionHistoryError(f"{path.name} differs from the reviewed NCES SHA-256")
    with zipfile.ZipFile(path) as archive:
        if archive.namelist() != [member]:
            raise InstitutionHistoryError(f"unexpected NCES directory members in {path.name}")
        with archive.open(member) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding=encoding, newline=""))
            if not REQUIRED.issubset(set(reader.fieldnames or ())):
                raise InstitutionHistoryError(f"missing NCES directory fields in {path.name}")
            rows = list(reader)
    if any(None in row or any(row.get(key) is None for key in REQUIRED) for row in rows):
        raise InstitutionHistoryError(f"malformed NCES directory row in {path.name}")
    return rows


def _check_dictionary(path: Path) -> None:
    if sha256_file(path)[0] != DICTIONARY_SHA256:
        raise InstitutionHistoryError("HD2023 dictionary differs from reviewed NCES SHA-256")
    with zipfile.ZipFile(path) as archive:
        if archive.namelist() != ["HD2023_dict.xlsx"]:
            raise InstitutionHistoryError("unexpected NCES directory dictionary member")
        # The reviewed workbook definitions are fixed by the archive digest.
        if not archive.getinfo("HD2023_dict.xlsx").file_size:
            raise InstitutionHistoryError("empty NCES directory dictionary")


def import_official_institution_history(
    previous: Path, current: Path, dictionary: Path
) -> InstitutionHistory:
    """Emit documented identity events, blocking unresolved status continuity."""
    try:
        _check_dictionary(dictionary)
        prior = _rows(previous, PREVIOUS_SHA256, "hd2022.csv", "cp1252")
        target = _rows(current, CURRENT_SHA256, "HD2023.csv", "utf-8-sig")
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeError, csv.Error) as error:
        raise InstitutionHistoryError(f"invalid NCES institution source: {error}") from error
    prior_ids = [int(row["UNITID"]) for row in prior]
    target_ids = [int(row["UNITID"]) for row in target]
    if (
        len(prior) != 6256
        or len(target) != 6163
        or len(set(prior_ids)) != len(prior_ids)
        or len(set(target_ids)) != len(target_ids)
    ):
        raise InstitutionHistoryError("NCES directory coverage differs from reviewed source")
    prior_set, target_set = set(prior_ids), set(target_ids)
    events: list[InstitutionHistoryEntry] = []
    counts: Counter[str] = Counter()
    for row in target:
        status = row["ACT"].strip()
        if status not in {"C", "D", "M"}:
            continue
        counts[status] += 1
        unitid = int(row["UNITID"])
        if unitid not in prior_set or (
            status != "M" and (row["CYACTIVE"] != "3" or row["DEATHYR"] != "2023")
        ):
            raise InstitutionHistoryError(f"unexpected NCES identity event for {unitid}")
        if status == "C":
            successor = int(row["NEWID"])
            if unitid == 413972 and successor == unitid:
                events.append(
                    InstitutionHistoryEntry(
                        source_unitid=unitid,
                        relationship=InstitutionRelationship.UNRESOLVED,
                        confidence=InstitutionMappingConfidence.LOW,
                        note="HD2023 ACT=C has self-referential NEWID; successor unresolved",
                    )
                )
                continue
            if successor not in target_set or successor == unitid:
                raise InstitutionHistoryError(f"invalid NCES combined successor for {unitid}")
            events.append(
                InstitutionHistoryEntry(
                    source_unitid=unitid,
                    target_unitid=successor,
                    relationship=InstitutionRelationship.MERGED,
                    confidence=InstitutionMappingConfidence.HIGH,
                    note="HD2023 ACT=C; NEWID identifies combined institution",
                )
            )
        elif status == "D":
            if row["NEWID"] != "-2":
                raise InstitutionHistoryError(f"deleted NCES institution {unitid} has a successor")
            events.append(
                InstitutionHistoryEntry(
                    source_unitid=unitid,
                    relationship=InstitutionRelationship.CLOSED,
                    confidence=InstitutionMappingConfidence.HIGH,
                    note="HD2023 ACT=D; deleted out of business",
                )
            )
        else:
            if row["NEWID"] != "-2" or row["CYACTIVE"] != "1":
                raise InstitutionHistoryError(f"unexpected NCES active-with-data event {unitid}")
            events.append(
                InstitutionHistoryEntry(
                    source_unitid=unitid,
                    relationship=InstitutionRelationship.UNRESOLVED,
                    confidence=InstitutionMappingConfidence.LOW,
                    note="HD2023 ACT=M; closure timing and data availability need review",
                )
            )
    if counts != {"C": 18, "D": 56, "M": 21}:
        raise InstitutionHistoryError("NCES institution event counts differ from reviewed source")
    return InstitutionHistory.model_validate(
        {
            "history_id": "nces-hd2022-to-hd2023-reviewed-2026-09",
            "source_release": "2022-23-final",
            "target_release": "2023-24-final",
            "source_url": SOURCE_URL,
            "source_sha256": CURRENT_SHA256,
            "entries": tuple(sorted(events, key=lambda event: event.source_unitid)),
        }
    )


def write_official_institution_history(
    previous: Path, current: Path, dictionary: Path, destination: Path
) -> InstitutionHistory:
    """Write immutable canonical JSON after checking all three pinned NCES archives."""
    history = import_official_institution_history(previous, current, dictionary)
    payload = json.dumps(history.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_text(encoding="utf-8") != payload:
                raise InstitutionHistoryError(
                    "existing institution history differs from reviewed source"
                )
        else:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(payload)
    except OSError as error:
        raise InstitutionHistoryError(f"could not write institution history: {error}") from error
    return history
