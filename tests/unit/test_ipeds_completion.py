import pytest
from pydantic import ValidationError

from education_roi.ipeds import (
    GraduationCohortScope,
    IPEDSComponent,
    IPEDSGraduationObservation,
    IPEDSPublicationStatus,
    IPEDSRelease,
    IPEDSReleaseCatalog,
    select_release,
)


def observation(**overrides: object) -> IPEDSGraduationObservation:
    payload: dict[str, object] = {
        "unitid": 236948,
        "release_id": "2023-24-final",
        "publication_status": "final",
        "component": "graduation-rates",
        "cohort_year": 2017,
        "cohort_scope": "bachelors_seeking",
        "normal_time_percent": 150,
        "adjusted_cohort": 100,
        "completers": 60,
        "source_artifact_id": "artifact-123",
        "source_columns": ["cohort", "completed"],
    }
    return IPEDSGraduationObservation.model_validate({**payload, **overrides})


def test_observed_rate_preserves_population_and_denominator() -> None:
    result = observation()
    assert result.observed_rate == pytest.approx(0.6)
    assert result.cohort_year == 2017
    assert result.cohort_scope is GraduationCohortScope.BACHELORS_SEEKING
    assert result.source_columns == ("cohort", "completed")
    assert observation(adjusted_cohort=0, completers=0).observed_rate is None
    assert observation(component="graduation-rates-200", normal_time_percent=200).observed_rate == (
        pytest.approx(0.6)
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"component": "outcome-measures"}, "GR or GR200"),
        ({"normal_time_percent": 200}, "GR uses 150%"),
        ({"completers": 101}, "exceed adjusted cohort"),
        ({"adjusted_cohort": -1}, "greater than or equal to 0"),
        ({"source_columns": ["same", "same"]}, "distinct"),
        ({"source_columns": ["only_one"]}, "at least 2"),
        ({"release_id": "2023-24-provisional"}, "publication status"),
    ],
)
def test_cohort_contract_rejects_incompatible_evidence(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        observation(**overrides)


def test_catalog_keeps_gr_gr200_and_outcome_measures_separate() -> None:
    def item(component: IPEDSComponent, status: str) -> IPEDSRelease:
        return IPEDSRelease.model_validate(
            {
                "release_id": f"2023-24-{status}",
                "collection_year": 2023,
                "component": component,
                "publication_status": status,
                "data_url": "https://nces.ed.gov/ipeds/data/fixture.zip",
                "dictionary_url": "https://nces.ed.gov/ipeds/data/fixture-dict.zip",
                "inventory_url": "https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
            }
        )

    catalog = IPEDSReleaseCatalog(
        reviewed_at="2026-09-23",
        releases=(
            item(IPEDSComponent.GRADUATION_RATES, "final"),
            item(IPEDSComponent.GRADUATION_RATES_200, "provisional"),
            item(IPEDSComponent.OUTCOME_MEASURES, "final"),
        ),
    )
    assert select_release(catalog, IPEDSComponent.GRADUATION_RATES).component is (
        IPEDSComponent.GRADUATION_RATES
    )
    with pytest.raises(ValueError, match="no final graduation-rates-200"):
        select_release(catalog, IPEDSComponent.GRADUATION_RATES_200)
    assert select_release(catalog, IPEDSComponent.OUTCOME_MEASURES).publication_status is (
        IPEDSPublicationStatus.FINAL
    )
