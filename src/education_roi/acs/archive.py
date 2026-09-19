"""Safe access to ACS PUMS ZIP archives."""

import csv
import io
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
        if (
            name.parent == PurePosixPath(".")
            and name.name.lower().startswith("psam_p")
            and name.suffix.lower() == ".csv"
        ):
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


def person_csv_columns(archive: Path) -> tuple[str, ...]:
    """Read only the validated person CSV header."""
    member = person_csv_member(archive)
    try:
        with (
            zipfile.ZipFile(archive) as bundle,
            bundle.open(member) as raw,
            io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text,
        ):
            header = next(csv.reader(text))
    except (OSError, UnicodeError, csv.Error, StopIteration) as error:
        raise ACSArchiveError(f"could not read ACS person CSV header: {error}") from error
    if not header or len(set(header)) != len(header):
        raise ACSArchiveError("ACS person CSV header is empty or contains duplicate columns")
    return tuple(header)


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
