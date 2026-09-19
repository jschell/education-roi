"""SQLite registry and immutable content-addressed storage."""

import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import HttpUrl

from education_roi import __version__
from education_roi.provenance.integrity import sha256_file, validate_archive
from education_roi.provenance.models import (
    ALLOWED_TRANSITIONS,
    ApprovalState,
    ArtifactManifest,
    DatasetDefinition,
)


class ProvenanceError(RuntimeError):
    """Base provenance failure."""


class DomainNotAllowedError(ProvenanceError):
    """A source or redirect target is outside the dataset policy."""


class InvalidTransitionError(ProvenanceError):
    """A lifecycle transition is not permitted."""


def validate_source_url(url: str, allowed_domains: tuple[str, ...]) -> None:
    """Require HTTPS and an exact or subdomain match."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not any(
        host == domain or host.endswith(f".{domain}") for domain in allowed_domains
    ):
        raise DomainNotAllowedError(f"URL is outside the allowed HTTPS domains: {url}")


class Registry:
    """Persistent metadata registry with atomic writes."""

    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    definition_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
                    release TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    UNIQUE(dataset_id, release, sha256)
                );
                CREATE INDEX IF NOT EXISTS artifacts_release
                    ON artifacts(dataset_id, release);
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    reason TEXT
                );
                """
            )

    def add_dataset(self, definition: DatasetDefinition) -> None:
        payload = definition.model_dump_json()
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT definition_json FROM datasets WHERE dataset_id = ?",
                (definition.dataset_id,),
            ).fetchone()
            if existing is not None and existing[0] != payload:
                raise ProvenanceError(f"dataset definition changed: {definition.dataset_id}")
            connection.execute(
                "INSERT OR IGNORE INTO datasets VALUES (?, ?)",
                (definition.dataset_id, payload),
            )

    def add_artifact(self, manifest: ArtifactManifest) -> ArtifactManifest:
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT manifest_json FROM artifacts WHERE artifact_id = ?",
                (manifest.artifact_id,),
            ).fetchone()
            if existing is not None:
                return ArtifactManifest.model_validate_json(existing[0])
            reused_release = connection.execute(
                "SELECT 1 FROM artifacts WHERE dataset_id = ? AND release = ? AND sha256 != ?",
                (manifest.dataset_id, manifest.release, manifest.sha256),
            ).fetchone()
            stored = manifest
            if reused_release is not None:
                stored = manifest.model_copy(update={"state": ApprovalState.REVIEW_REQUIRED})
            connection.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    stored.artifact_id,
                    stored.dataset_id,
                    stored.release,
                    stored.sha256,
                    stored.state.value,
                    stored.model_dump_json(),
                ),
            )
            return stored

    def transition(
        self, artifact_id: str, target: ApprovalState, reason: str | None = None
    ) -> ArtifactManifest:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT state, manifest_json FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            current = ApprovalState(row[0])
            if target not in ALLOWED_TRANSITIONS[current]:
                raise InvalidTransitionError(f"cannot transition {current} to {target}")
            manifest = ArtifactManifest.model_validate_json(row[1]).model_copy(
                update={"state": target}
            )
            connection.execute(
                "UPDATE artifacts SET state = ?, manifest_json = ? WHERE artifact_id = ?",
                (target.value, manifest.model_dump_json(), artifact_id),
            )
            connection.execute(
                "INSERT INTO transitions (artifact_id, from_state, to_state, changed_at, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (artifact_id, current.value, target.value, datetime.now(UTC).isoformat(), reason),
            )
            return manifest


class ArtifactStore:
    """Register local downloads under immutable, content-addressed paths."""

    def __init__(self, root: Path, registry: Registry) -> None:
        self.root = root
        self.registry = registry

    def register(
        self,
        source: Path,
        definition: DatasetDefinition,
        *,
        release: str,
        source_url: str,
        final_url: str,
        publication_status: str,
        schema_version: str,
        vintage: str | None = None,
        expected_sha256: str | None = None,
    ) -> ArtifactManifest:
        validate_source_url(source_url, definition.allowed_domains)
        validate_source_url(final_url, definition.allowed_domains)
        digest, size = sha256_file(source)
        if expected_sha256 is not None and digest != expected_sha256.lower():
            raise ProvenanceError("download SHA-256 does not match the expected value")
        validate_archive(source)
        relative = Path(definition.dataset_id) / release / digest / source.name
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + ".partial")
            try:
                with source.open("rb") as incoming, temporary.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                temporary.replace(destination)
                destination.chmod(0o444)
            except FileExistsError:
                pass
            finally:
                temporary.unlink(missing_ok=True)
        artifact_id = f"{definition.dataset_id}:{release}:{digest}"
        manifest = ArtifactManifest(
            artifact_id=artifact_id,
            dataset_id=definition.dataset_id,
            publisher=definition.publisher,
            release=release,
            vintage=vintage,
            retrieved_at=datetime.now(UTC),
            source_url=HttpUrl(source_url),
            final_url=HttpUrl(final_url),
            sha256=digest,
            file_size=size,
            publication_status=publication_status,
            schema_version=schema_version,
            software_version=__version__,
            storage_path=relative.as_posix(),
        )
        stored = self.registry.add_artifact(manifest)
        manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
        if not manifest_path.exists():
            manifest_path.write_text(
                json.dumps(stored.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
            )
            manifest_path.chmod(0o444)
        return stored
