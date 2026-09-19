"""Hashing and archive-integrity checks."""

import hashlib
import tarfile
import zipfile
from pathlib import Path


class IntegrityError(ValueError):
    """Artifact bytes fail an integrity requirement."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    """Return a streaming SHA-256 digest and byte count."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def validate_archive(path: Path) -> None:
    """Validate ZIP or tar archives; leave ordinary files unchanged."""
    if path.suffix.lower() == ".zip" or zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as archive:
                corrupt = archive.testzip()
                if corrupt is not None:
                    raise IntegrityError(f"corrupt ZIP member: {corrupt}")
        except zipfile.BadZipFile as error:
            raise IntegrityError(f"corrupt ZIP archive: {error}") from error
        return
    tar_suffixes = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
    if path.name.lower().endswith(tar_suffixes) or tarfile.is_tarfile(path):
        try:
            with tarfile.open(path) as archive:
                for member in archive:
                    if member.isfile():
                        extracted = archive.extractfile(member)
                        if extracted is not None:
                            while extracted.read(1024 * 1024):
                                pass
        except (tarfile.TarError, OSError) as error:
            raise IntegrityError(f"corrupt tar archive: {error}") from error
