"""Explicitly synthetic inputs for clean-environment reproduction smoke tests."""

from hashlib import sha256
from json import dumps

import polars as pl

from education_roi.acs.crosswalk import CrosswalkStatus
from education_roi.cashflow import CashFlowPoint, CashFlowSeries, DollarMode, MoneyBasis
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
)

SYNTHETIC_FIXTURE_VERSION = "synthetic-zhang-smoke-v1"


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
    configuration = {
        "fixture_version": SYNTHETIC_FIXTURE_VERSION,
        "ages": [18, 19],
        "quantile": 0.50,
        "money_basis": {"mode": "real", "dollar_year": 2021},
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
            "authoritative coefficients, restricted cost cells, and Table A1 remain unavailable",
        ),
        ("smoke-test values validate orchestration only",),
    )
