"""Processed two-year cohort lookup verifies full rows and paired lineage."""

import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSReleaseCatalog
from education_roi.ipeds.graduation_comparison import IPEDSGraduationComparisonError
from education_roi.ipeds.graduation_pipeline import (
    GR2023_TWO_YEAR_TRANSFORMATION_VERSION,
    _frame,
)
from education_roi.ipeds.graduation_two_year_evidence import resolve_two_year_graduation_evidence
from education_roi.provenance.integrity import sha256_file

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,GRTYPE,CHRTSTAT,SECTION,COHORT,LINE,XGRTOTLT,GRTOTLT\n"


def processed(tmp_path: Path) -> Path:
    release = next(
        item
        for item in IPEDSReleaseCatalog.from_file(CATALOG).releases
        if item.component is IPEDSComponent.GRADUATION_RATES and item.release_id == "2023-24-final"
    )
    archive = tmp_path / "source.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr(
            "gr2023_RV.csv",
            HEADER + "1,29,12,4,4,50,R,225\n1,30,13,4,4,29A,R,54\n" + "2,29,12,4,4,50,R,10\n",
        )
    path = tmp_path / "two-year-any-award.parquet"
    _frame(
        archive, release, "data:2023-24-final", "dictionary:2023-24-final", two_year=True
    ).write_parquet(path)
    payload = {
        "transformation": {
            "transformation_id": "synthetic-fixture",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "software_version": "test",
            "output_sha256": sha256_file(path)[0],
            "input_artifact_ids": ["data:2023-24-final", "dictionary:2023-24-final"],
            "parameters": {
                "data_member": "gr2023_RV.csv",
                "cohort_year": 2020,
                "cohort_scope": "all_degree_or_certificate_seeking_first_time_full_time_two_year",
                "award_outcome": "any_award",
                "normal_time_percent": 150,
                "transformation_version": GR2023_TWO_YEAR_TRANSFORMATION_VERSION,
            },
        },
        "release_id": "2023-24-final",
        "publication_status": "final",
        "cohort_year": 2020,
        "cohort_scope": "all_degree_or_certificate_seeking_first_time_full_time_two_year",
        "award_outcome": "any_award",
        "normal_time_percent": 150,
        "row_count": 2,
        "columns": pl.read_parquet(path).columns,
        "output_path": path.name,
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(payload))
    return path


def test_two_year_exact_lookup_and_cli(tmp_path: Path) -> None:
    path = processed(tmp_path)
    observed = resolve_two_year_graduation_evidence(path, 1)
    assert observed.status == "OBSERVED" and observed.observed_rate == pytest.approx(0.24)
    assert observed.any_awards == 54 and observed.cohort_year == 2020
    assert observed.manifest_sha256 == sha256_file(path.with_suffix(".manifest.json"))[0]
    missing = resolve_two_year_graduation_evidence(path, 2)
    assert missing.status == "INSUFFICIENT_DATA"
    assert missing.unavailable_reason == "missing cohort or award row"
    absent = resolve_two_year_graduation_evidence(path, 3)
    assert absent.status == "INSUFFICIENT_DATA" and absent.any_awards is None
    cli = CliRunner().invoke(app, ["ipeds", "resolve-gr2023-two-year-table", str(path), "1"])
    assert cli.exit_code == 0
    assert json.loads(cli.stdout)["any_awards"] == 54


def test_two_year_rejects_source_cell_and_manifest_tampering(tmp_path: Path) -> None:
    path = processed(tmp_path)
    sidecar = path.with_suffix(".manifest.json")
    frame = pl.read_parquet(path)
    frame = frame.with_columns(
        pl.when(pl.col("unitid") == 2)
        .then(pl.lit("9"))
        .otherwise(pl.col("raw_adjusted_cohort"))
        .alias("raw_adjusted_cohort")
    )
    frame.write_parquet(path)
    payload = json.loads(sidecar.read_text())
    payload["transformation"]["output_sha256"] = sha256_file(path)[0]
    sidecar.write_text(json.dumps(payload))
    with pytest.raises(IPEDSGraduationComparisonError, match="parsed counts"):
        resolve_two_year_graduation_evidence(path, 1)
    sidecar.unlink()
    with pytest.raises(IPEDSGraduationComparisonError, match="verify two-year table"):
        resolve_two_year_graduation_evidence(path, 1)
