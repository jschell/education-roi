from pathlib import Path

import pytest

from education_roi.cashflow import CashFlowPoint, CashFlowSeries, DollarMode, MoneyBasis
from education_roi.reproduction.costs import (
    CostComponents,
    CostEvidence,
    CostLevel,
    CostProvenance,
    CostSelectionStatus,
    CostSensitivitySet,
    EducationCostEstimate,
    evaluate_cost_sensitivity,
    select_cost_estimate,
)
from education_roi.reproduction.reporting import provisional_reproduction_report


def provenance(source: str = "IPEDS public fixture") -> CostProvenance:
    return CostProvenance(
        source,
        "NCES",
        "2023-24-provisional",
        "a" * 64,
        "https://nces.ed.gov/ipeds/",
    )


def estimate(
    estimate_id: str,
    actual_level: CostLevel,
    net_cost: float,
    *,
    requested_level: CostLevel = CostLevel.INSTITUTION_PROGRAM,
    evidence: CostEvidence = CostEvidence.PUBLIC_SUBSTITUTE,
) -> EducationCostEstimate:
    return EducationCostEstimate(
        estimate_id,
        requested_level,
        actual_level,
        evidence,
        2021,
        CostComponents(net_cost, 0, 0, 0),
        provenance(),
        ("versioned public-data fixture; not a paper cost cell",),
    )


def test_fallback_is_deterministic_and_discloses_actual_level() -> None:
    institution = estimate("institution", CostLevel.INSTITUTION, 20_000)
    sector = estimate("sector", CostLevel.SECTOR_CREDENTIAL, 15_000)
    first = select_cost_estimate(CostLevel.INSTITUTION_PROGRAM, (sector, institution))
    second = select_cost_estimate(CostLevel.INSTITUTION_PROGRAM, (institution, sector))
    assert first == second
    assert first.status is CostSelectionStatus.AVAILABLE
    assert first.estimate == institution
    assert first.as_dict()["estimate"]["actual_level"] == "INSTITUTION"  # type: ignore[index]
    assert first.as_dict()["estimate"]["evidence"] == "PUBLIC_SUBSTITUTE"  # type: ignore[index]


def test_broader_estimate_cannot_claim_direct_or_exact_evidence() -> None:
    for evidence in (CostEvidence.DIRECT, CostEvidence.EXACT_PUBLISHED_INPUT):
        with pytest.raises(ValueError, match="broader aggregation"):
            estimate("misleading", CostLevel.INSTITUTION, 20_000, evidence=evidence)


def test_missing_cost_is_insufficient_data_and_duplicates_are_ambiguous() -> None:
    missing = select_cost_estimate(CostLevel.INSTITUTION_PROGRAM, ())
    assert missing.status is CostSelectionStatus.INSUFFICIENT_DATA
    assert missing.estimate is None
    with pytest.raises(ValueError, match="ambiguous"):
        select_cost_estimate(
            CostLevel.INSTITUTION_PROGRAM,
            (
                estimate("one", CostLevel.INSTITUTION, 20_000),
                estimate("two", CostLevel.INSTITUTION, 21_000),
            ),
        )


def test_cost_sensitivity_changes_npv_and_irr_monotonically() -> None:
    cash_flow = CashFlowSeries(
        "earnings advantage before education costs",
        MoneyBasis(DollarMode.REAL, 2021),
        tuple(CashFlowPoint(age, 0 if age < 22 else 100_000) for age in range(18, 23)),
    )
    sensitivity = CostSensitivitySet(
        estimate("low", CostLevel.INSTITUTION, 10_000),
        estimate("base", CostLevel.INSTITUTION, 20_000),
        estimate("high", CostLevel.INSTITUTION, 30_000),
    )
    results = evaluate_cost_sensitivity(
        cash_flow, sensitivity, education_ages=(18, 19, 20, 21), discount_rate=0.04
    )
    assert [item.case.value for item in results] == ["LOW", "BASE", "HIGH"]
    assert (
        results[0].net_present_value > results[1].net_present_value > results[2].net_present_value
    )
    roots = [item.internal_rate_of_return.roots[0] for item in results]
    assert roots[0] > roots[1] > roots[2]
    assert not any(item.as_dict()["exact_input_eligible"] for item in results)


def test_report_exposes_substitute_costs_and_bundle_payload_is_deterministic(
    tmp_path: Path,
) -> None:
    del tmp_path
    cash_flow = CashFlowSeries(
        "fixture",
        MoneyBasis(DollarMode.REAL, 2021),
        (CashFlowPoint(18, 0), CashFlowPoint(19, 100_000)),
    )
    cases = CostSensitivitySet(
        estimate("low", CostLevel.INSTITUTION, 10_000),
        estimate("base", CostLevel.INSTITUTION, 20_000),
        estimate("high", CostLevel.INSTITUTION, 30_000),
    )
    analysis = evaluate_cost_sensitivity(cash_flow, cases, education_ages=(18,), discount_rate=0.04)
    report = provisional_reproduction_report(
        configuration_hash="config",
        dataset_hashes=("dataset",),
        sample_flow=(),
        profiles=(),
        profile_validations=(),
        cash_flows=(),
        comparisons=(),
        blockers=("public cost substitutes are not exact paper inputs",),
        ambiguity_notes=(),
        cost_analysis=tuple(item.as_dict() for item in analysis),
    )
    assert report.schema_version == "reproduction-report-v2"
    assert report.as_dict()["cost_analysis"][1]["case"] == "BASE"  # type: ignore[index]
    assert "PUBLIC_SUBSTITUTE" in report.to_markdown()
    assert "Exact-input eligible" in report.to_markdown()
