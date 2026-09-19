"""Selective ACS person-file reads."""

from collections.abc import Collection
from pathlib import Path

import polars as pl

from education_roi.acs.archive import materialize_person_csv
from education_roi.acs.source import REQUIRED_PERSON_COLUMNS
from education_roi.acs.transform import validate_person_schema

PERSON_COLUMN_ORDER = (
    "SERIALNO",
    "SPORDER",
    "ADJINC",
    "PWGTP",
    "AGEP",
    "SCH",
    "SCHL",
    "WAGP",
    "FOD1P",
    "NATIVITY",
)


def read_person_csv(path: Path, extra_columns: Collection[str] = ()) -> pl.DataFrame:
    """Lazily select only required and explicitly requested person columns."""
    scan = pl.scan_csv(path, infer_schema_length=10_000, null_values=["", "N/A"])
    available = scan.collect_schema().names()
    validate_person_schema(available)
    extras = tuple(dict.fromkeys(extra_columns))
    missing_extras = sorted(set(extras).difference(available))
    if missing_extras:
        raise ValueError(f"requested ACS columns are missing: {', '.join(missing_extras)}")
    selected = (
        *PERSON_COLUMN_ORDER,
        *(column for column in extras if column not in REQUIRED_PERSON_COLUMNS),
    )
    return scan.select(selected).collect()


def read_person_archive(archive: Path, extra_columns: Collection[str] = ()) -> pl.DataFrame:
    """Read selected columns from a validated ACS person archive."""
    with materialize_person_csv(archive) as csv_path:
        return read_person_csv(csv_path, extra_columns)
