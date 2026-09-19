import polars as pl
import pytest
from pydantic import ValidationError

from education_roi.acs.crosswalk import (
    CrosswalkStatus,
    DegreeCrosswalk,
    ReproductionCrosswalkError,
)
from education_roi.acs.models import ACSProduct, ACSRelease
from education_roi.acs.statistics import weighted_quantile
from education_roi.acs.transform import ACSchemaError, apply_zhang_sample, validate_person_schema


def person_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "SERIALNO": "1",
        "SPORDER": 1,
        "ADJINC": 1_020_000,
        "PWGTP": 10,
        "AGEP": 30,
        "SCH": 1,
        "SCHL": 21,
        "WAGP": 100_000,
        "FOD1P": "1101",
        "NATIVITY": 1,
    }
    row.update(overrides)
    return row


def test_release_constructs_authoritative_urls() -> None:
    release = ACSRelease(vintage=2024, product=ACSProduct.ONE_YEAR, geography="wa")
    assert release.release_id == "2024-1yr-wa"
    assert release.person_archive_url.endswith("/2024/1-Year/csv_pwa.zip")
    assert release.variables_url == (
        "https://api.census.gov/data/2024/acs/acs1/pums/variables.json"
    )
    with pytest.raises(ValidationError):
        ACSRelease(vintage=2024, product=ACSProduct.ONE_YEAR, geography="washington")


def test_schema_error_names_missing_columns() -> None:
    with pytest.raises(ACSchemaError, match="ADJINC"):
        validate_person_schema({"AGEP"})


def test_sample_restrictions_and_normalization_preserve_raw_fields() -> None:
    rows = [
        person_row(SERIALNO="included-bachelors"),
        person_row(SERIALNO="included-hs", SCHL=16, FOD1P=None, AGEP=65),
        person_row(SERIALNO="foreign", NATIVITY=2),
        person_row(SERIALNO="enrolled", SCH=2),
        person_row(SERIALNO="zero-wage", WAGP=0),
        person_row(SERIALNO="graduate", SCHL=22),
        person_row(SERIALNO="missing-major", FOD1P=None),
        person_row(SERIALNO="too-young", AGEP=17),
    ]
    result = apply_zhang_sample(pl.DataFrame(rows))
    assert result.get_column("SERIALNO").to_list() == ["included-bachelors", "included-hs"]
    assert result.get_column("education_level").to_list() == ["bachelors", "high_school"]
    assert result.get_column("age_band").to_list() == ["30-34", "60-65"]
    assert result.get_column("WAGP").to_list() == [100_000.0, 100_000.0]
    assert result.get_column("wage_salary_adjusted").to_list() == [102_000.0, 102_000.0]
    assert result.get_column("person_weight").to_list() == [10.0, 10.0]


@pytest.mark.parametrize(
    ("age", "expected"),
    [(18, "18-24"), (24, "18-24"), (25, "25-29"), (59, "55-59"), (60, "60-65")],
)
def test_age_band_boundaries(age: int, expected: str) -> None:
    result = apply_zhang_sample(pl.DataFrame([person_row(AGEP=age)]))
    assert result.item(0, "age_band") == expected


def test_weighted_quantile_retains_support() -> None:
    frame = pl.DataFrame(
        {"wage_salary_adjusted": [10.0, 20.0, 30.0], "person_weight": [1.0, 8.0, 1.0]}
    )
    estimate = weighted_quantile(frame, 0.5)
    assert estimate.value == 20.0
    assert estimate.unweighted_n == 3
    assert estimate.weighted_n == 10.0


def test_provisional_crosswalk_cannot_certify_reproduction() -> None:
    crosswalk = DegreeCrosswalk(
        version="draft-1",
        status=CrosswalkStatus.PROVISIONAL,
        source="main paper reconstruction; Table A1 unavailable",
        mappings={"1101": "agriculture"},
    )
    with pytest.raises(ReproductionCrosswalkError, match="Table A1"):
        crosswalk.require_verified_for_reproduction()
