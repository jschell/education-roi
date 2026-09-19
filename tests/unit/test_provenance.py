import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

from education_roi.provenance.integrity import IntegrityError, sha256_file, validate_archive
from education_roi.provenance.models import (
    ApprovalState,
    ArtifactManifest,
    DatasetDefinition,
    TransformationManifest,
)
from education_roi.provenance.store import (
    ArtifactStore,
    DomainNotAllowedError,
    InvalidTransitionError,
    ProvenanceError,
    Registry,
    validate_source_url,
)


def definition() -> DatasetDefinition:
    return DatasetDefinition(
        dataset_id="acs-pums",
        publisher="U.S. Census Bureau",
        name="ACS PUMS",
        allowed_domains=("census.gov",),
    )


def test_domain_policy_accepts_subdomains_and_rejects_lookalikes() -> None:
    validate_source_url("https://www.census.gov/file.zip", ("census.gov",))
    with pytest.raises(DomainNotAllowedError):
        validate_source_url("https://census.gov.example.test/file.zip", ("census.gov",))
    with pytest.raises(DomainNotAllowedError):
        validate_source_url("http://www.census.gov/file.zip", ("census.gov",))


def test_hash_streams_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "data.csv"
    artifact.write_bytes(b"abc")
    digest, size = sha256_file(artifact, chunk_size=1)
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert size == 3


def test_corrupt_zip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("file.txt", "contents")
    content = archive.read_bytes()
    archive.write_bytes(content[:-2])
    with pytest.raises((IntegrityError, zipfile.BadZipFile)):
        validate_archive(archive)


def test_register_is_immutable_and_idempotent(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "metadata.sqlite")
    dataset = definition()
    registry.add_dataset(dataset)
    source = tmp_path / "download.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    store = ArtifactStore(tmp_path / "raw", registry)

    first = store.register(
        source,
        dataset,
        release="2024-5yr",
        source_url="https://www.census.gov/download.csv",
        final_url="https://www.census.gov/download.csv",
        publication_status="final",
        schema_version="2024",
    )
    second = store.register(
        source,
        dataset,
        release="2024-5yr",
        source_url="https://www.census.gov/download.csv",
        final_url="https://www.census.gov/download.csv",
        publication_status="final",
        schema_version="2024",
    )

    assert first.artifact_id == second.artifact_id
    destination = tmp_path / "raw" / first.storage_path
    assert destination.read_text(encoding="utf-8") == "value\n1\n"
    assert destination.stat().st_mode & 0o222 == 0
    manifest = json.loads(
        destination.with_suffix(destination.suffix + ".manifest.json").read_text()
    )
    assert manifest["sha256"] == first.sha256


def test_reused_release_with_changed_bytes_requires_review(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "metadata.sqlite")
    dataset = definition()
    registry.add_dataset(dataset)
    store = ArtifactStore(tmp_path / "raw", registry)
    source = tmp_path / "download.csv"
    source.write_text("one", encoding="utf-8")
    store.register(
        source,
        dataset,
        release="2024-5yr",
        source_url="https://census.gov/download.csv",
        final_url="https://census.gov/download.csv",
        publication_status="final",
        schema_version="2024",
    )
    source.write_text("two", encoding="utf-8")
    changed = store.register(
        source,
        dataset,
        release="2024-5yr",
        source_url="https://census.gov/download.csv",
        final_url="https://census.gov/download.csv",
        publication_status="final",
        schema_version="2024",
    )
    assert changed.state is ApprovalState.REVIEW_REQUIRED


def test_checksum_mismatch_leaves_no_artifact(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "metadata.sqlite")
    dataset = definition()
    registry.add_dataset(dataset)
    source = tmp_path / "download.csv"
    source.write_text("data", encoding="utf-8")
    with pytest.raises(ProvenanceError, match="SHA-256"):
        ArtifactStore(tmp_path / "raw", registry).register(
            source,
            dataset,
            release="2024",
            source_url="https://census.gov/data",
            final_url="https://census.gov/data",
            publication_status="final",
            schema_version="1",
            expected_sha256="0" * 64,
        )
    assert not (tmp_path / "raw").exists()


def test_state_machine_records_valid_transition(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "metadata.sqlite")
    dataset = definition()
    registry.add_dataset(dataset)
    source = tmp_path / "download.csv"
    source.write_text("data", encoding="utf-8")
    manifest = ArtifactStore(tmp_path / "raw", registry).register(
        source,
        dataset,
        release="2024",
        source_url="https://census.gov/data",
        final_url="https://census.gov/data",
        publication_status="final",
        schema_version="1",
    )
    validated = registry.transition(manifest.artifact_id, ApprovalState.VALIDATED, "checks passed")
    assert validated.state is ApprovalState.VALIDATED
    with pytest.raises(InvalidTransitionError):
        registry.transition(manifest.artifact_id, ApprovalState.DISCOVERED)
    with sqlite3.connect(registry.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transitions").fetchone() == (1,)


def test_manifest_rejects_unsafe_path() -> None:
    with pytest.raises(ValidationError):
        ArtifactManifest(
            artifact_id=f"acs-pums:2024:{'0' * 64}",
            dataset_id="acs-pums",
            publisher="Census",
            release="2024",
            retrieved_at=datetime.now(UTC),
            source_url=HttpUrl("https://census.gov/data"),
            final_url=HttpUrl("https://census.gov/data"),
            sha256="0" * 64,
            file_size=1,
            publication_status="final",
            schema_version="1",
            software_version="test",
            storage_path="../escape",
        )


def test_transformation_requires_raw_lineage() -> None:
    with pytest.raises(ValidationError):
        TransformationManifest(
            transformation_id="test",
            created_at=datetime.now(UTC),
            software_version="test",
            output_sha256="0" * 64,
            input_artifact_ids=(),
        )


def test_artifact_name_must_be_safe_basename(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "metadata.sqlite")
    dataset = definition()
    registry.add_dataset(dataset)
    source = tmp_path / "download.partial"
    source.write_text("data", encoding="utf-8")
    with pytest.raises(ProvenanceError, match="safe basename"):
        ArtifactStore(tmp_path / "raw", registry).register(
            source,
            dataset,
            release="2024",
            source_url="https://census.gov/data",
            final_url="https://census.gov/data",
            publication_status="final",
            schema_version="1",
            artifact_name="../data.csv",
        )
