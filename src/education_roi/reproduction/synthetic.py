"""Explicitly synthetic inputs for clean-environment reproduction smoke tests."""

from hashlib import sha256
from json import dumps

import polars as pl

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
    PublicCostReproductionFixture,
    TargetObservation,
)

SYNTHETIC_FIXTURE_VERSION = "synthetic-zhang-smoke-v2"


def _hash(value: object) -> str:
    encoded = dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _profile(
    group: str, intercept: float, reference: tuple[tuple[int, float], ...]
) -> ProfileFixture:
    coefficients = QuantileEarningsCoefficients(
        group,
        QuantileDefinition(0.50),
        intercept,
        0.04,
        -0.0004,
        f"{SYNTHETIC_FIXTURE_VERSION}; not paper coefficients",
    )
    solver = QuantileSolverMetadata(
        "interior-point",
        "synthetic-fixed-fixture",
        "1.0",
        SolverStatus.CONVERGED,
        12,
        1e-9,
        100.0,
        "synthetic convergence metadata",
    )
    return ProfileFixture(
        coefficients,
        solver,
        18,
        19,
        reference,
        "independently frozen synthetic math fixture v1",
        1e-9,
        1e-12,
    )


def _cost_estimate(name: str, net_cost: float) -> EducationCostEstimate:
    return EducationCostEstimate(
        f"{SYNTHETIC_FIXTURE_VERSION}-{name}",
        CostLevel.INSTITUTION_PROGRAM,
        CostLevel.INSTITUTION,
        CostEvidence.PUBLIC_SUBSTITUTE,
        2021,
        CostComponents(net_cost, 0, 0, 0),
        CostProvenance(
            "synthetic public-cost fixture; not observed data",
            "Education ROI test suite",
            SYNTHETIC_FIXTURE_VERSION,
            _hash({"fixture": SYNTHETIC_FIXTURE_VERSION, "name": name, "cost": net_cost}),
            "https://example.invalid/synthetic-public-cost-fixture",
        ),
        ("synthetic orchestration input; not a paper cost cell",),
    )


def synthetic_provisional_request() -> ProvisionalRunRequest:
    """Return stable fake inputs that exercise every implemented runner stage."""
    records = {
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
    option = _profile(
        "synthetic-bachelors",
        9.0,
        ((18, 14_623.717851741809), (19, 14_996.918115378601)),
    )
    counterfactual = _profile(
        "synthetic-high-school",
        8.8,
        ((18, 11_972.887529556507), (19, 12_278.43806245276)),
    )
    cash_flow = QuantileCashFlow(
        QuantileDefinition(0.50),
        CashFlowSeries(
            "synthetic P50 fixture",
            MoneyBasis(DollarMode.REAL, 2021),
            (CashFlowPoint(18, -100), CashFlowPoint(19, 120)),
        ),
        option.coefficients.coefficient_hash,
        counterfactual.coefficients.coefficient_hash,
    )
    target = ReproductionTarget(
        "synthetic-table-target",
        "synthetic fixture; not a paper table",
        0.20,
        1e-8,
    )
    low_cost = _cost_estimate("low", 100)
    base_cost = _cost_estimate("base", 110)
    high_cost = _cost_estimate("high", 115)
    public_cost_target = ReproductionTarget(
        "synthetic-public-cost",
        "synthetic public-cost fixture; not a paper table",
        120 / 110 - 1,
        1e-8,
    )
    public_cost_reproductions = (
        PublicCostReproductionFixture(
            "available-public-cost",
            CostLevel.INSTITUTION_PROGRAM,
            (base_cost,),
            CostSensitivitySet(low_cost, base_cost, high_cost),
            CashFlowSeries(
                "synthetic earnings advantage before education costs",
                MoneyBasis(DollarMode.REAL, 2021),
                (CashFlowPoint(18, 0), CashFlowPoint(19, 120)),
            ),
            (18,),
            0.04,
            public_cost_target,
            CrosswalkStatus.PROVISIONAL,
        ),
        PublicCostReproductionFixture(
            "missing-public-cost",
            CostLevel.INSTITUTION_PROGRAM,
            (),
            None,
            None,
            (),
            0.04,
            ReproductionTarget(
                "synthetic-missing-cost",
                "synthetic missing-cost fixture; not a paper table",
                0.10,
                1e-8,
            ),
            CrosswalkStatus.PROVISIONAL,
        ),
    )
    configuration = {
        "fixture_version": SYNTHETIC_FIXTURE_VERSION,
        "ages": [18, 19],
        "quantile": 0.50,
        "money_basis": {"mode": "real", "dollar_year": 2021},
        "public_cost_fixture": "available and insufficient-data cases",
    }
    return ProvisionalRunRequest(
        _hash(configuration),
        (_hash(records),),
        pl.DataFrame(records),
        (counterfactual, option),
        (cash_flow,),
        (TargetObservation(target, 0.20, CrosswalkStatus.PROVISIONAL),),
        (
            "SYNTHETIC FIXTURE: contains no authoritative ACS observations or paper estimates",
            "authoritative coefficients and Table A1 remain unavailable; public cost substitutes "
            "are not exact paper inputs",
        ),
        ("smoke-test values validate orchestration only",),
        public_cost_reproductions=public_cost_reproductions,
    )
