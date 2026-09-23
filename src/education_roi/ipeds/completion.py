"""Explicit institutional completion cohort evidence, pending release-specific GR mapping."""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from education_roi.ipeds.catalog import IPEDSComponent, IPEDSPublicationStatus
from education_roi.scenarios.models import StrictModel


class GraduationCohortScope(StrEnum):
    BACHELORS_SEEKING = "bachelors_seeking"
    OTHER_DEGREE_OR_CERTIFICATE_SEEKING = "other_degree_or_certificate_seeking"
    ALL_DEGREE_OR_CERTIFICATE_SEEKING = "all_degree_or_certificate_seeking"


class IPEDSGraduationObservation(StrictModel):
    """One observed rate cell; no inference of a student's eventual completion chance."""

    unitid: int = Field(gt=0)
    release_id: str = Field(min_length=1)
    publication_status: IPEDSPublicationStatus
    component: IPEDSComponent
    cohort_year: int = Field(ge=1900, le=2200)
    cohort_scope: GraduationCohortScope
    normal_time_percent: int
    adjusted_cohort: int = Field(ge=0)
    completers: int = Field(ge=0)
    source_artifact_id: str = Field(min_length=1)
    source_columns: tuple[str, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_cohort(self) -> Self:
        if self.component not in {
            IPEDSComponent.GRADUATION_RATES,
            IPEDSComponent.GRADUATION_RATES_200,
        }:
            raise ValueError("graduation observation requires a GR or GR200 component")
        if self.normal_time_percent != (
            150 if self.component is IPEDSComponent.GRADUATION_RATES else 200
        ):
            raise ValueError("GR uses 150% and GR200 uses 200% of normal time")
        if self.completers > self.adjusted_cohort:
            raise ValueError("completers exceed adjusted cohort")
        if len(set(self.source_columns)) != len(self.source_columns):
            raise ValueError("source columns must be distinct")
        if not self.release_id.endswith(f"-{self.publication_status.value}"):
            raise ValueError("release ID does not match publication status")
        return self

    @property
    def observed_rate(self) -> float | None:
        """None represents an unavailable denominator, not a zero completion rate."""
        if self.adjusted_cohort == 0:
            return None
        return self.completers / self.adjusted_cohort
