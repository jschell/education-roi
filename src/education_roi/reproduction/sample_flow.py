from dataclasses import dataclass

import polars as pl

from education_roi.acs.transform import validate_person_schema


@dataclass(frozen=True)
class SampleFlowRecord:
    step: str
    description: str
    unweighted_n: int
    weighted_n: float

    def as_dict(self) -> dict[str, str | int | float]:
        return {
            "step": self.step,
            "description": self.description,
            "unweighted_n": self.unweighted_n,
            "weighted_n": self.weighted_n,
        }


@dataclass(frozen=True)
class SampleFlowResult:
    records: tuple[SampleFlowRecord, ...]
    final_frame: pl.DataFrame

    def as_dict(self) -> list[dict[str, str | int | float]]:
        return [record.as_dict() for record in self.records]


def _record(step: str, description: str, frame: pl.DataFrame) -> SampleFlowRecord:
    weights = frame.get_column("PWGTP").cast(pl.Float64, strict=False).fill_null(0)
    return SampleFlowRecord(step, description, frame.height, float(weights.sum()))


def zhang_sample_flow(frame: pl.DataFrame) -> SampleFlowResult:
    validate_person_schema(frame.columns)
    current = frame.with_columns(
        pl.col("AGEP").cast(pl.Int64, strict=False),
        pl.col("NATIVITY").cast(pl.Int64, strict=False),
        pl.col("SCH").cast(pl.Int64, strict=False),
        pl.col("SCHL").cast(pl.Int64, strict=False),
        pl.col("WAGP").cast(pl.Float64, strict=False),
        pl.col("ADJINC").cast(pl.Float64, strict=False),
        pl.col("PWGTP").cast(pl.Float64, strict=False),
        pl.col("FOD1P").cast(pl.String, strict=False),
    )
    records = [_record("input", "all input person records", current)]
    restrictions = (
        ("age", "ages 18 through 65", pl.col("AGEP").is_between(18, 65, closed="both")),
        ("nativity", "U.S.-born", pl.col("NATIVITY") == 1),
        ("enrollment", "not enrolled in school", pl.col("SCH") == 1),
        ("education", "exactly high-school diploma or bachelor's", pl.col("SCHL").is_in([16, 21])),
        ("earnings", "positive wage and salary earnings", pl.col("WAGP") > 0),
        ("weight", "positive person weight", pl.col("PWGTP") > 0),
        ("income_adjustment", "positive ACS income adjustment", pl.col("ADJINC") > 0),
        (
            "major",
            "bachelor's records report first field of degree",
            (pl.col("SCHL") != 21)
            | (pl.col("FOD1P").is_not_null() & (pl.col("FOD1P").str.strip_chars() != "")),
        ),
    )
    for step, description, expression in restrictions:
        current = current.filter(expression)
        records.append(_record(step, description, current))
    return SampleFlowResult(tuple(records), current)
