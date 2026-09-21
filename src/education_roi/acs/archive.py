"""Safe access to ACS PUMS ZIP archives."""

import csv
import io
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath


class ACSArchiveError(ValueError):
    """Raised when an ACS archive is corrupt, ambiguous, or unsafe."""


def person_csv_member(
    archive: Path,
    *,
    max_uncompressed_bytes: int = 8_000_000_000,
    max_compression_ratio: float = 1_000,
) -> zipfile.ZipInfo:
    """Validate an archive and return its single ACS person CSV member."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            corrupt = bundle.testzip()
    except (OSError, zipfile.BadZipFile) as error:
        raise ACSArchiveError(f"invalid ZIP archive: {error}") from error
    if corrupt is not None:
        raise ACSArchiveError(f"corrupt ZIP member: {corrupt}")

    person_files: list[zipfile.ZipInfo] = []
    total_uncompressed = 0
    total_compressed = 0
    for member in members:
        name = PurePosixPath(member.filename)
        if name.is_absolute() or ".." in name.parts or member.flag_bits & 0x1:
            raise ACSArchiveError(f"unsafe ZIP member: {member.filename}")
        if member.is_dir():
            continue
        total_uncompressed += member.file_size
        total_compressed += member.compress_size
        is_person_csv = name.name.lower().startswith("psam_p") or re.fullmatch(
            r"ss\d{2}pus[ab]\.csv", name.name.lower()
        )
        if name.parent == PurePosixPath(".") and is_person_csv and name.suffix.lower() == ".csv":
            person_files.append(member)

    if total_uncompressed > max_uncompressed_bytes:
        raise ACSArchiveError("archive exceeds the configured uncompressed size limit")
    ratio = total_uncompressed / max(total_compressed, 1)
    if ratio > max_compression_ratio:
        raise ACSArchiveError("archive exceeds the configured compression-ratio limit")
    if len(person_files) != 1:
        raise ACSArchiveError(
            f"expected exactly one root-level psam_p*.csv member; found {len(person_files)}"
        )
    return person_files[0]


def person_csv_members(
    archive: Path,
    *,
    max_uncompressed_bytes: int = 8_000_000_000,
    max_compression_ratio: float = 1_000,
) -> tuple[zipfile.ZipInfo, ...]:
    """Return the one state file or the two published nationwide file parts."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            corrupt = bundle.testzip()
    except (OSError, zipfile.BadZipFile) as error:
        raise ACSArchiveError(f"invalid ZIP archive: {error}") from error
    if corrupt is not None:
        raise ACSArchiveError(f"corrupt ZIP member: {corrupt}")

    person_files: list[zipfile.ZipInfo] = []
    total_uncompressed = 0
    total_compressed = 0
    for member in members:
        name = PurePosixPath(member.filename)
        if name.is_absolute() or ".." in name.parts or member.flag_bits & 0x1:
            raise ACSArchiveError(f"unsafe ZIP member: {member.filename}")
        if member.is_dir():
            continue
        total_uncompressed += member.file_size
        total_compressed += member.compress_size
        is_person_csv = name.name.lower().startswith("psam_p") or re.fullmatch(
            r"ss\d{2}pus[ab]\.csv", name.name.lower()
        )
        if name.parent == PurePosixPath(".") and is_person_csv and name.suffix.lower() == ".csv":
            person_files.append(member)

    if total_uncompressed > max_uncompressed_bytes:
        raise ACSArchiveError("archive exceeds the configured uncompressed size limit")
    ratio = total_uncompressed / max(total_compressed, 1)
    if ratio > max_compression_ratio:
        raise ACSArchiveError("archive exceeds the configured compression-ratio limit")
    person_files.sort(key=lambda member: member.filename.lower())
    names = {PurePosixPath(member.filename).name.lower() for member in person_files}
    modern_pair = names == {"psam_pusa.csv", "psam_pusb.csv"}
    legacy_pair = len(names) == 2 and all(
        re.fullmatch(r"ss\d{2}pus[ab]\.csv", name) for name in names
    )
    if len(person_files) == 1 or modern_pair or legacy_pair:
        return tuple(person_files)
    raise ACSArchiveError(
        "expected one root-level person CSV or nationwide psam_pusa/psam_pusb parts; "
        f"found {len(person_files)}"
    )


def person_csv_columns(archive: Path) -> tuple[str, ...]:
    """Read only the validated person CSV header."""
    members = person_csv_members(archive)
    try:
        headers: list[list[str]] = []
        with zipfile.ZipFile(archive) as bundle:
            for member in members:
                with (
                    bundle.open(member) as raw,
                    io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text,
                ):
                    headers.append(next(csv.reader(text)))
    except (OSError, UnicodeError, csv.Error, StopIteration) as error:
        raise ACSArchiveError(f"could not read ACS person CSV header: {error}") from error
    header = headers[0]
    normalized_header = [column.upper() for column in header]
    if not header or len(set(normalized_header)) != len(normalized_header):
        raise ACSArchiveError("ACS person CSV header is empty or contains duplicate columns")
    if any(
        [column.upper() for column in candidate] != normalized_header for candidate in headers[1:]
    ):
        raise ACSArchiveError("nationwide ACS person CSV parts have different headers")
    return tuple(normalized_header)


@contextmanager
def materialize_person_csv(archive: Path) -> Iterator[Path]:
    """Stream the validated person member into an isolated temporary directory."""
    member = person_csv_member(archive)
    with tempfile.TemporaryDirectory(prefix="education-roi-acs-") as temporary_directory:
        destination = Path(temporary_directory) / member.filename
        try:
            with (
                zipfile.ZipFile(archive) as bundle,
                bundle.open(member) as source,
                destination.open("xb") as output,
            ):
                shutil.copyfileobj(source, output, length=1024 * 1024)
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            raise ACSArchiveError(f"could not extract ACS person CSV: {error}") from error
        yield destination


@contextmanager
def materialize_person_csvs(archive: Path) -> Iterator[tuple[Path, ...]]:
    """Stream all validated person-file parts into an isolated directory."""
    members = person_csv_members(archive)
    with tempfile.TemporaryDirectory(prefix="education-roi-acs-") as temporary_directory:
        destinations: list[Path] = []
        try:
            with zipfile.ZipFile(archive) as bundle:
                for member in members:
                    destination = Path(temporary_directory) / member.filename
                    with bundle.open(member) as source, destination.open("xb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    destinations.append(destination)
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            raise ACSArchiveError(f"could not extract ACS person CSV: {error}") from error
        yield tuple(destinations)
