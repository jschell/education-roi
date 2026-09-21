import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
import pytest
from pydantic import HttpUrl

from education_roi.ipeds import (
    IPEDSArchiveError,
    IPEDSComponent,
    IPEDSPublicationStatus,
    IPEDSRelease,
    transform_charges_archive,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest


def write_archive(path: Path, body: str) -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("IC2023_AY.csv", body)
    return path


def release() -> IPEDSRelease:
    return IPEDSRelease(
        release_id="2023-24-provisional",
        collection_year=2023,
        component=IPEDSComponent.ACADEMIC_YEAR_CHARGES,
        publication_status=IPEDSPublicationStatus.PROVISIONAL,
        data_url=HttpUrl("https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip"),
        dictionary_url=HttpUrl("https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY_Dict.zip"),
        inventory_url=HttpUrl(
            "https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023&surveyNumber=1"
        ),
    )


def manifest(archive: Path) -> ArtifactManifest:
    digest, size = sha256_file(archive)
    return ArtifactManifest(
        artifact_id=f"ipeds-institutional-characteristics:2023-24-provisional:{digest}",
        dataset_id="ipeds-institutional-characteristics",
        publisher="National Center for Education Statistics",
        release="2023-24-provisional",
        vintage="2023-24-provisional",
        retrieved_at=datetime.now(UTC),
        source_url=HttpUrl("https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip"),
        final_url=HttpUrl("https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip"),
        sha256=digest,
        file_size=size,
        publication_status="provisional",
        schema_version="ipeds-ic-ay-v1",
        software_version="test",
        storage_path="ipeds/fixture.zip",
    )


@pytest.mark.integration
def test_charge_archive_to_parquet_preserves_bases_status_and_lineage(tmp_path: Path) -> None:
    archive = write_archive(
        tmp_path / "charges.zip",
        (
            "UNITID,CHG1AY3,CHG2AY3,CHG3AY3,CHG4AY3,"
            "XCHG1AY3,XCHG2AY3,XCHG3AY3,XCHG4AY3\n"
            "236949,-1,13000,31000,950,,S,O,B\n"
            "236948,8000,12000,30000,900,D,S,O,B\n"
        ),
    )
    source = manifest(archive)

    first = transform_charges_archive(archive, tmp_path / "processed", source, release())
    second = transform_charges_archive(archive, tmp_path / "processed", source, release())

    assert first.parquet_path == second.parquet_path
    assert sha256_file(first.parquet_path) == sha256_file(second.parquet_path)
    frame = pl.read_parquet(first.parquet_path)
    assert frame.get_column("unitid").to_list() == [236948, 236949]
    assert frame.item(0, "tuition_in_district") == 8000
    assert frame.item(1, "tuition_in_district") is None
    assert frame.item(0, "attendance_basis") == "full_time"
    assert frame.item(0, "reporting_basis") == "academic_year"
    assert frame.item(0, "publication_status") == "provisional"
    assert frame.item(0, "status_tuition_in_state") == "S"
    assert frame.item(0, "source_artifact_id") == source.artifact_id
    payload = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert payload["transformation"]["input_artifact_ids"] == [source.artifact_id]
    assert payload["transformation"]["output_sha256"] == sha256_file(first.parquet_path)[0]
    assert payload["row_count"] == 2


@pytest.mark.integration
def test_charge_pipeline_rejects_invalid_optional_cost(tmp_path: Path) -> None:
    archive = write_archive(
        tmp_path / "charges.zip",
        "UNITID,CHG1AY3,CHG2AY3,CHG3AY3,CHG4AY3\n236948,nope,12000,30000,900\n",
    )
    with pytest.raises(IPEDSArchiveError, match="invalid IPEDS cost"):
        transform_charges_archive(archive, tmp_path / "processed", manifest(archive), release())


@pytest.mark.integration
def test_charge_pipeline_rejects_manifest_or_release_mismatch(tmp_path: Path) -> None:
    archive = write_archive(
        tmp_path / "charges.zip",
        "UNITID,CHG2AY3,CHG4AY3\n236948,12000,900\n",
    )
    source = manifest(archive)
    wrong_dataset = source.model_copy(update={"dataset_id": "not-ipeds"})
    with pytest.raises(ValueError, match="must identify"):
        transform_charges_archive(archive, tmp_path / "processed", wrong_dataset, release())
    wrong_release = source.model_copy(update={"release": "2022-23-final"})
    with pytest.raises(ValueError, match="do not match"):
        transform_charges_archive(archive, tmp_path / "processed", wrong_release, release())
