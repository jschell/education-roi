"""Strict parsing for an IPEDS academic-year charges ZIP artifact."""

import csv
import io
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from education_roi.ipeds.source import REQUIRED_COLUMNS, UNITID_COLUMN


class IPEDSArchiveError(ValueError):
    """The IPEDS archive does not satisfy the pinned schema contract."""


def _member(archive: ZipFile) -> str:
    members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if len(members) != 1:
        raise IPEDSArchiveError("IPEDS charges archive must contain exactly one CSV file")
    return members[0]


def read_charge_rows(path: Path) -> dict[int, dict[str, str]]:
    """Return rows by UNITID while preserving raw cells for policy-aware parsing."""
    try:
        with ZipFile(path) as archive:
            data = archive.read(_member(archive)).decode("utf-8-sig")
    except (OSError, BadZipFile, KeyError, UnicodeError) as error:
        raise IPEDSArchiveError(f"could not read IPEDS charges archive: {error}") from error
    try:
        reader = csv.DictReader(io.StringIO(data))
        columns = frozenset(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS.difference(columns))
        if missing:
            raise IPEDSArchiveError("IPEDS archive is missing columns: " + ", ".join(missing))
        rows: dict[int, dict[str, str]] = {}
        for number, row in enumerate(reader, start=2):
            try:
                unitid = int((row.get(UNITID_COLUMN) or "").strip())
            except ValueError as error:
                raise IPEDSArchiveError(f"invalid UNITID on CSV row {number}") from error
            if unitid <= 0:
                raise IPEDSArchiveError(f"invalid UNITID on CSV row {number}")
            if unitid in rows:
                raise IPEDSArchiveError(f"duplicate UNITID {unitid}")
            rows[unitid] = {key: (value or "").strip() for key, value in row.items()}
        return rows
    except csv.Error as error:
        raise IPEDSArchiveError(f"could not parse IPEDS charges CSV: {error}") from error


def parse_nonnegative_cost(cell: str) -> float | None:
    """Parse a reported cost; blank or negative sentinel values are unavailable."""
    if not cell:
        return None
    try:
        value = float(cell)
    except ValueError as error:
        raise IPEDSArchiveError(f"invalid IPEDS cost value: {cell!r}") from error
    if value < 0:
        return None
    return value
