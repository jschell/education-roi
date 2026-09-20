import pytest

from education_roi.acs.crosswalk import CrosswalkStatus
from education_roi.cashflow import CashFlowPoint, CashFlowSeries, DollarMode, MoneyBasis
from education_roi.reproduction.comparison import ReproductionTarget
from education_roi.reproduction.costs import (
    CostComponents,
    CostEvidence,
    CostLevel,
    CostProvenance,
    CostSensitivitySet,
    EducationCostEstimate,
)
from education_roi.reproduction.runner import (
    PublicCostReproductionFixture,
    evaluate_public_cost_reproductions,
)

PROVENANCE = CostProvenance(
    "versioned public fixture",
    "NCES",
    "2023-24-final",
    "a" * 64,
    "https://nces.ed.gov/ipeds/",
)


def estimate(name: str, cost: float) -> EducationCostEstimate:
    return EducationCostEstimate(
        name,
        CostLevel.INSTITUTION_PROGRAM,
        CostLevel.INSTITUTION,
        CostEvidence.PUBLIC_SUBSTITUTE,
        2021,
        CostComponents(cost, 0, 0, 0),
        PROVENANCE,
        ("not an exact paper cost cell",),
    )


def cash_flow() -> CashFlowSeries:
    return CashFlowSeries(
        "earnings advantage before education costs",
        MoneyBasis(DollarMode.REAL, 2021),
        tuple(CashFlowPoint(age, 0 if age < 22 else 100_000) for age in range(18, 23)),
    )


def target() -> ReproductionTarget:
    return ReproductionTarget("table-3-public-cost", "Table 3 fixture", 1.5, 0.01)


def available_fixture(reproduction_id: str = "aggregate-men") -> PublicCostReproductionFixture:
    base = estimate("base", 20_000)
    return PublicCostReproductionFixture(
        reproduction_id,
        CostLevel.INSTITUTION_PROGRAM,
        (base,),
        CostSensitivitySet(estimate("low", 10_000), base, estimate("high", 30_000)),
        cash_flow(),
        (18, 19, 20, 21),
        0.04,
        target(),
        CrosswalkStatus.VERIFIED,
    )


def test_public_cost_runner_selects_fallback_and_compares_every_case() -> None:
    analyses, comparisons = evaluate_public_cost_reproductions(
        (available_fixture(),),
        configuration_hash="configuration",
        dataset_hashes=("dataset",),
    )
    assert [item["case"] for item in analyses] == ["LOW", "BASE", "HIGH"]
    assert all(item["status"] == "AVAILABLE" for item in analyses)
    selection = analyses[0]["selection"]
    assert isinstance(selection, dict)
    selected = selection["estimate"]
    assert isinstance(selected, dict)
    assert selected["actual_level"] == "INSTITUTION"
    assert [item["cost_case"] for item in comparisons] == ["LOW", "BASE", "HIGH"]
    assert comparisons[1]["cost_irr_delta_from_base"] == 0
    assert comparisons[1]["cost_npv_delta_from_base"] == 0
    assert comparisons[0]["cost_irr_delta_from_base"] > 0  # type: ignore[operator]
    assert comparisons[2]["cost_irr_delta_from_base"] < 0  # type: ignore[operator]
    assert comparisons[0]["target_id"] == "table-3-public-cost:low"
    assert comparisons[0]["cost_evidence"] == "PUBLIC_SUBSTITUTE"


def test_public_cost_runner_preserves_insufficient_data() -> None:
    fixture = PublicCostReproductionFixture(
        "missing-cost",
        CostLevel.INSTITUTION_PROGRAM,
        (),
        None,
        None,
        (),
        0.04,
        target(),
        CrosswalkStatus.VERIFIED,
    )
    analyses, comparisons = evaluate_public_cost_reproductions(
        (fixture,), configuration_hash="configuration", dataset_hashes=("dataset",)
    )
    assert analyses[0]["status"] == "INSUFFICIENT_DATA"
    assert analyses[0]["estimate"] is None
    assert comparisons[0]["status"] == "REVIEW"
    assert comparisons[0]["reproduced_value"] is None
    assert comparisons[0]["cost_selection_status"] == "INSUFFICIENT_DATA"


def test_public_cost_fixture_requires_selected_base_and_unique_identity() -> None:
    selected = estimate("selected", 20_000)
    with pytest.raises(ValueError, match="base sensitivity estimate"):
        PublicCostReproductionFixture(
            "mismatch",
            CostLevel.INSTITUTION_PROGRAM,
            (selected,),
            CostSensitivitySet(
                estimate("low", 10_000), estimate("other", 21_000), estimate("high", 30_000)
            ),
            cash_flow(),
            (18, 19, 20, 21),
            0.04,
            target(),
            CrosswalkStatus.VERIFIED,
        )
    fixture = available_fixture("duplicate")
    with pytest.raises(ValueError, match="IDs must be unique"):
        evaluate_public_cost_reproductions(
            (fixture, fixture), configuration_hash="configuration", dataset_hashes=("dataset",)
        )
