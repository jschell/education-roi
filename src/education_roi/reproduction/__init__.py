"""Zhang reproduction configuration, sample flow, and target comparisons."""

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
from education_roi.reproduction.sample_flow import (
    SampleFlowRecord,
    SampleFlowResult,
    zhang_sample_flow,
)

__all__ = [
    "AggregateReproductionResult",
    "CovariateSlopeSpecification",
    "EarningsCoefficients",
    "EarningsPoint",
    "EarningsProfile",
    "ReproductionStatus",
    "ReproductionTarget",
    "SampleFlowRecord",
    "SampleFlowResult",
    "ZhangConfiguration",
    "build_age_earnings_profile",
    "compare_target",
    "published_zhang_configuration",
    "reproduce_aggregate_target",
    "zhang_sample_flow",
]
