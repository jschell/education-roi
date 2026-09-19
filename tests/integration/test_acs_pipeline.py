import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from pydantic import HttpUrl

from education_roi.acs.archive import ACSArchiveError, person_csv_member
from education_roi.acs.ingest import read_person_archive
from education_roi.acs.models import ACSProduct, ACSRelease
from education_roi.acs.pipeline import transform_zhang_archive
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ArtifactManifest

COLUMNS = [
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
    "EXTRA",
]


def write_archive(path: Path, member: str = "psam_p53.csv") -> None:
    rows = [
        ["one", 1, 1_020_000, 10, 30, 1, 21, 100_000, 1101, 1, "unused"],
        ["two", 1, 1_020_000, 5, 17, 1, 21, 50_000, 1101, 1, "filtered"],
    ]
    csv = ",".join(COLUMNS) + "\n" + "\n".join(",".join(map(str, row)) for row in rows) + "\n"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(member, csv)
        bundle.writestr("ACS_README.pdf", b"fixture")


def raw_manifest(archive: Path) -> ArtifactManifest:
    digest, size = sha256_file(archive)
    return ArtifactManifest(
        artifact_id=f"acs-pums:2024-1yr-wa:{digest}",
        dataset_id="acs-pums",
        publisher="U.S. Census Bureau",
        release="2024-1yr-wa",
        vintage="2024",
        retrieved_at=datetime.now(UTC),
        source_url=HttpUrl("https://www2.census.gov/example.zip"),
        final_url=HttpUrl("https://www2.census.gov/example.zip"),
        sha256=digest,
        file_size=size,
        publication_status="final",
        schema_version="2024",
        software_version="test",
        storage_path="acs-pums/fixture.zip",
    )


@pytest.mark.integration
def test_archive_read_selects_only_requested_columns(tmp_path: Path) -> None:
    archive = tmp_path / "pums.zip"
    write_archive(archive)
    frame = read_person_archive(archive)
    assert "EXTRA" not in frame.columns
    assert set(frame.columns) == set(COLUMNS) - {"EXTRA"}
    with_extra = read_person_archive(archive, ["EXTRA"])
    assert with_extra.get_column("EXTRA").to_list() == ["unused", "filtered"]


@pytest.mark.integration
def test_archive_rejects_traversal_and_ambiguous_person_files(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    write_archive(traversal, "../psam_p53.csv")
    with pytest.raises(ACSArchiveError, match="unsafe"):
        person_csv_member(traversal)

    ambiguous = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(ambiguous, "w") as bundle:
        bundle.writestr("psam_p01.csv", ",".join(COLUMNS))
        bundle.writestr("psam_p02.csv", ",".join(COLUMNS))
    with pytest.raises(ACSArchiveError, match="exactly one"):
        person_csv_member(ambiguous)


@pytest.mark.integration
def test_archive_to_parquet_has_lineage_and_is_repeatable(tmp_path: Path) -> None:
    archive = tmp_path / "pums.zip"
    write_archive(archive)
    source = raw_manifest(archive)
    release = ACSRelease(vintage=2024, product=ACSProduct.ONE_YEAR, geography="wa")

    first = transform_zhang_archive(archive, tmp_path / "processed", source, release)
    second = transform_zhang_archive(archive, tmp_path / "processed", source, release)

    assert first.parquet_path == second.parquet_path
    assert sha256_file(first.parquet_path) == sha256_file(second.parquet_path)
    frame = pl.read_parquet(first.parquet_path)
    assert frame.height == 1
    assert frame.item(0, "source_artifact_id") == source.artifact_id
    assert frame.item(0, "acs_release_id") == "2024-1yr-wa"
    assert frame.item(0, "wage_salary_adjusted") == 102_000.0
    payload = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert payload["transformation"]["input_artifact_ids"] == [source.artifact_id]
    assert payload["transformation"]["output_sha256"] == sha256_file(first.parquet_path)[0]
    assert payload["row_count"] == 1


@pytest.mark.integration
def test_pipeline_rejects_raw_manifest_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "pums.zip"
    write_archive(archive)
    source = raw_manifest(archive).model_copy(update={"file_size": archive.stat().st_size + 1})
    release = ACSRelease(vintage=2024, product=ACSProduct.ONE_YEAR, geography="wa")
    with pytest.raises(ValueError, match="does not match"):
        transform_zhang_archive(archive, tmp_path / "processed", source, release)
