"""Named, deterministic ACS PUMS person transformations."""

from collections.abc import Collection

import polars as pl

from education_roi.acs.source import REPLICATE_WEIGHT_COLUMNS, REQUIRED_PERSON_COLUMNS


class ACSchemaError(ValueError):
    """Raised when a person file does not satisfy the transformation contract."""


def validate_person_schema(columns: Collection[str]) -> None:
    """Require the fields used by the initial Zhang analytical sample."""
    missing = sorted(REQUIRED_PERSON_COLUMNS.difference(columns))
    if missing:
        raise ACSchemaError(f"ACS person file is missing required columns: {', '.join(missing)}")


def age_band_expression() -> pl.Expr:
    """Return the documented age-band classification for ages 18 through 65."""
    age = pl.col("AGEP")
    return (
        pl.when(age <= 24)
        .then(pl.lit("18-24"))
        .when(age <= 29)
        .then(pl.lit("25-29"))
        .when(age <= 34)
        .then(pl.lit("30-34"))
        .when(age <= 39)
        .then(pl.lit("35-39"))
        .when(age <= 44)
        .then(pl.lit("40-44"))
        .when(age <= 49)
        .then(pl.lit("45-49"))
        .when(age <= 54)
        .then(pl.lit("50-54"))
        .when(age <= 59)
        .then(pl.lit("55-59"))
        .otherwise(pl.lit("60-65"))
        .alias("age_band")
    )


def apply_zhang_sample(frame: pl.DataFrame) -> pl.DataFrame:
    """Apply the paper's verified main-sample restrictions.

    The exact 173-field Table A1 grouping is intentionally not performed here.
    Original Census fields are retained and normalized fields are appended.
    """
    validate_person_schema(frame.columns)
    typed = frame.with_columns(
        pl.col("AGEP").cast(pl.Int64, strict=False),
        pl.col("NATIVITY").cast(pl.Int64, strict=False),
        pl.col("SCH").cast(pl.Int64, strict=False),
        pl.col("SCHL").cast(pl.Int64, strict=False),
        pl.col("WAGP").cast(pl.Float64, strict=False),
        pl.col("ADJINC").cast(pl.Float64, strict=False),
        pl.col("PWGTP").cast(pl.Float64, strict=False),
        pl.col("FOD1P").cast(pl.String, strict=False),
        *(
            pl.col(column).cast(pl.Float64, strict=False)
            for column in REPLICATE_WEIGHT_COLUMNS
            if column in frame.columns
        ),
    )
    bachelor_has_major = (pl.col("SCHL") != 21) | (
        pl.col("FOD1P").is_not_null() & (pl.col("FOD1P").str.strip_chars() != "")
    )
    filtered = typed.filter(
        pl.col("AGEP").is_between(18, 65, closed="both"),
        pl.col("NATIVITY") == 1,
        pl.col("SCH") == 1,
        pl.col("SCHL").is_in([16, 21]),
        pl.col("WAGP") > 0,
        pl.col("PWGTP") > 0,
        pl.col("ADJINC") > 0,
        bachelor_has_major,
    )
    return filtered.with_columns(
        pl.when(pl.col("SCHL") == 16)
        .then(pl.lit("high_school"))
        .otherwise(pl.lit("bachelors"))
        .alias("education_level"),
        (pl.col("ADJINC") / 1_000_000).alias("income_adjustment_factor"),
        (pl.col("WAGP") * pl.col("ADJINC") / 1_000_000).alias("wage_salary_adjusted"),
        pl.col("PWGTP").alias("person_weight"),
        pl.col("FOD1P").alias("field_of_degree_code"),
        age_band_expression(),
    )
