"""Zhang reproduction configuration, profiles, reports, and target comparisons."""

from education_roi.reproduction.aggregate import (
    AggregateReproductionResult,
    reproduce_aggregate_target,
)
from education_roi.reproduction.comparison import (
    ReproductionStatus,
    ReproductionTarget,
    compare_target,
)
from education_roi.reproduction.config import ZhangConfiguration, published_zhang_configuration
from education_roi.reproduction.profiles import (
    CovariateSlopeSpecification,
    EarningsCoefficients,
    EarningsPoint,
    EarningsProfile,
    build_age_earnings_profile,
)
from education_roi.reproduction.quantiles import (
    DECILES,
    RANK_INVARIANCE_WARNING,
    ProfileValidationReport,
    QuantileCashFlow,
    QuantileDefinition,
    QuantileEarningsCoefficients,
    QuantileEarningsPoint,
    QuantileEarningsProfile,
    QuantileIRRResult,
    QuantileProfileFit,
    QuantileSolverMetadata,
    SolverStatus,
    build_quantile_earnings_profile,
    calculate_quantile_irrs,
    validate_profile_against_reference,
)
from education_roi.reproduction.reporting import (
    CertificationStatus,
    ReproductionReport,
    provisional_reproduction_report,
)
from education_roi.reproduction.sample_flow import (
    SampleFlowRecord,
    SampleFlowResult,
    zhang_sample_flow,
)

__all__ = [
    "DECILES",
    "RANK_INVARIANCE_WARNING",
    "AggregateReproductionResult",
    "CertificationStatus",
    "CovariateSlopeSpecification",
    "EarningsCoefficients",
    "EarningsPoint",
    "EarningsProfile",
    "ProfileValidationReport",
    "QuantileCashFlow",
    "QuantileDefinition",
    "QuantileEarningsCoefficients",
    "QuantileEarningsPoint",
    "QuantileEarningsProfile",
    "QuantileIRRResult",
    "QuantileProfileFit",
    "QuantileSolverMetadata",
    "ReproductionReport",
    "ReproductionStatus",
    "ReproductionTarget",
    "SampleFlowRecord",
    "SampleFlowResult",
    "SolverStatus",
    "ZhangConfiguration",
    "build_age_earnings_profile",
    "build_quantile_earnings_profile",
    "calculate_quantile_irrs",
    "compare_target",
    "provisional_reproduction_report",
    "published_zhang_configuration",
    "reproduce_aggregate_target",
    "validate_profile_against_reference",
    "zhang_sample_flow",
]
