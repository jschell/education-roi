from math import exp
from pathlib import Path

import polars as pl
import pytest

from education_roi.acs.crosswalk import CrosswalkStatus
from education_roi.cashflow import CashFlowPoint, CashFlowSeries, DollarMode, MoneyBasis
from education_roi.reproduction.bundle import verify_reproduction_bundle
from education_roi.reproduction.comparison import ReproductionTarget
from education_roi.reproduction.quantiles import (
    QuantileCashFlow,
    QuantileDefinition,
    QuantileEarningsCoefficients,
    QuantileSolverMetadata,
    SolverStatus,
)
from education_roi.reproduction.runner import (
    ProfileFixture,
    ProvisionalRunRequest,
    TargetObservation,
    run_provisional_reproduction,
)


def person_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "SERIALNO": ["1", "2", "3"],
            "SPORDER": [1, 1, 1],
            "ADJINC": [1_000_000, 1_000_000, 1_000_000],
            "PWGTP": [10, 20, 30],
            "AGEP": [30, 40, 17],
            "SCH": [1, 1, 1],
            "SCHL": [21, 16, 16],
            "WAGP": [80_000, 40_000, 10_000],
            "FOD1P": ["1100", None, None],
            "NATIVITY": [1, 1, 1],
        }
    )


def solver() -> QuantileSolverMetadata:
    return QuantileSolverMetadata(
        "interior-point",
        "independent-fixture-solver",
        "1.0",
        SolverStatus.CONVERGED,
        12,
        1e-9,
        100.0,
        "fixture convergence record",
    )


def profile_fixture(group: str, intercept: float) -> ProfileFixture:
    coefficients = QuantileEarningsCoefficients(
        group,
        QuantileDefinition(0.50),
        intercept,
        0.04,
        -0.0004,
        "synthetic orchestration fixture",
    )
    reference = tuple((age, exp(intercept + 0.04 * age - 0.0004 * age**2)) for age in (18, 19))
    return ProfileFixture(
        coefficients,
        solver(),
        18,
        19,
        reference,
        "frozen orchestration fixture v1",
        0,
        0,
    )


def request(*, bad_counterfactual_hash: bool = False) -> ProvisionalRunRequest:
    option = profile_fixture("bachelors", 9.0)
    counterfactual = profile_fixture("high-school", 8.8)
    series = CashFlowSeries(
        "P50 fixture",
        MoneyBasis(DollarMode.REAL, 2021),
        (CashFlowPoint(18, -100), CashFlowPoint(19, 120)),
    )
    cash_flow = QuantileCashFlow(
        QuantileDefinition(0.50),
        series,
        option.coefficients.coefficient_hash,
        "missing-profile"
        if bad_counterfactual_hash
        else counterfactual.coefficients.coefficient_hash,
    )
    target = ReproductionTarget("table-3-men", "Table 3, men", 0.20, 1e-8)
    return ProvisionalRunRequest(
        "configuration-sha256",
        ("dataset-sha256",),
        person_frame(),
        (counterfactual, option),
        (cash_flow,),
        (TargetObservation(target, 0.20, CrosswalkStatus.VERIFIED),),
        ("authoritative ACS inputs unavailable",),
        ("fixture coefficients are not paper estimates",),
    )


def test_runner_executes_all_stages_and_writes_deterministic_bundle(tmp_path: Path) -> None:
    first = run_provisional_reproduction(request(), results_root=tmp_path / "one", run_id="run-001")
    second = run_provisional_reproduction(
        request(), results_root=tmp_path / "two", run_id="run-001"
    )

    assert first.report.certification_status.value == "PROVISIONAL"
    assert first.report.sample_flow[-1]["unweighted_n"] == 2
    assert [fit.profile.group for fit in first.report.profiles if fit.profile is not None] == [
        "bachelors",
        "high-school",
    ]
    assert len(first.report.profile_validations) == 2
    assert first.report.cash_flows[0].internal_rate_of_return.roots == pytest.approx((0.20,))
    assert first.report.comparisons[0]["status"] == "PASS"
    assert verify_reproduction_bundle(first.bundle.path) == first.bundle
    assert first.report.to_json() == second.report.to_json()
    assert {path.name: path.read_bytes() for path in first.bundle.path.iterdir()} == {
        path.name: path.read_bytes() for path in second.bundle.path.iterdir()
    }


def test_runner_rejects_cash_flow_with_unavailable_profile_hash(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing-profile"):
        run_provisional_reproduction(
            request(bad_counterfactual_hash=True),
            results_root=tmp_path,
            run_id="run-001",
        )
    assert not (tmp_path / "run-001").exists()


def test_profile_fixture_preserves_solver_failure_without_fake_validation(
    tmp_path: Path,
) -> None:
    coefficients = QuantileEarningsCoefficients(
        "bachelors", QuantileDefinition(0.50), 9, 0.04, -0.0004, "fixture"
    )
    failed = QuantileSolverMetadata(
        "interior-point", "fixture", "1.0", SolverStatus.FAILED, 12, 1e-9, None, "failed"
    )
    fixture = ProfileFixture(coefficients, failed, 18, 19, None, None)
    with pytest.raises(ValueError, match="unavailable profile hashes"):
        run_provisional_reproduction(
            ProvisionalRunRequest(
                "config",
                ("dataset",),
                person_frame(),
                (fixture,),
                (
                    QuantileCashFlow(
                        QuantileDefinition(0.50),
                        CashFlowSeries(
                            "fixture",
                            MoneyBasis(DollarMode.REAL, 2021),
                            (CashFlowPoint(18, -1), CashFlowPoint(19, 2)),
                        ),
                        coefficients.coefficient_hash,
                        coefficients.coefficient_hash,
                    ),
                ),
                (),
                ("blocked",),
                (),
            ),
            results_root=tmp_path,
            run_id="run-001",
        )
