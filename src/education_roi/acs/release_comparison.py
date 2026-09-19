"""Cross-release metric comparisons that block silent anomaly promotion."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class ComparisonStatus(StrEnum):
    """Validation outcome for a metric or complete release comparison."""

    VALIDATED = "VALIDATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, order=True)
class MetricKey:
    """Stable identity for a metric and its analytical dimensions."""

    metric: str
    dimensions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("metric name cannot be empty")
        names = [name for name, _ in self.dimensions]
        if len(names) != len(set(names)):
            raise ValueError("metric dimension names must be unique")
        object.__setattr__(self, "dimensions", tuple(sorted(self.dimensions)))


@dataclass(frozen=True)
class MetricSnapshot:
    """One release's value and sample support for a comparable metric."""

    release_id: str
    key: MetricKey
    value: float
    unweighted_n: int
    weighted_n: float

    def __post_init__(self) -> None:
        if not self.release_id.strip():
            raise ValueError("release_id cannot be empty")
        if not isfinite(self.value) or not isfinite(self.weighted_n):
            raise ValueError("metric values and support must be finite")
        if self.unweighted_n < 0 or self.weighted_n < 0:
            raise ValueError("metric support cannot be negative")


@dataclass(frozen=True)
class ChangeThreshold:
    """Maximum permitted change before manual review is required."""

    max_relative_change: float | None = None
    max_absolute_change: float | None = None

    def __post_init__(self) -> None:
        limits = (self.max_relative_change, self.max_absolute_change)
        if all(limit is None for limit in limits):
            raise ValueError("at least one change threshold is required")
        if any(limit is not None and (not isfinite(limit) or limit < 0) for limit in limits):
            raise ValueError("change thresholds must be finite and nonnegative")


@dataclass(frozen=True)
class MetricComparison:
    """Auditable comparison outcome for one metric key."""

    key: MetricKey
    status: ComparisonStatus
    previous: MetricSnapshot | None
    current: MetricSnapshot | None
    absolute_change: float | None
    relative_change: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseComparisonReport:
    """Promotion gate for a complete previous/current release comparison."""

    previous_release: str
    current_release: str
    status: ComparisonStatus
    comparisons: tuple[MetricComparison, ...]

    @property
    def promotion_allowed(self) -> bool:
        """Return true only when every configured comparison validates."""
        return self.status is ComparisonStatus.VALIDATED


def _index_snapshots(
    snapshots: Sequence[MetricSnapshot], expected_release: str
) -> dict[MetricKey, MetricSnapshot]:
    indexed: dict[MetricKey, MetricSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.release_id != expected_release:
            raise ValueError(
                f"snapshot release {snapshot.release_id!r} does not match {expected_release!r}"
            )
        if snapshot.key in indexed:
            raise ValueError(f"duplicate metric snapshot: {snapshot.key}")
        indexed[snapshot.key] = snapshot
    return indexed


def compare_release_snapshots(
    previous_release: str,
    current_release: str,
    previous: Sequence[MetricSnapshot],
    current: Sequence[MetricSnapshot],
    thresholds: Mapping[str, ChangeThreshold],
) -> ReleaseComparisonReport:
    """Compare release metrics and require review for anomalies or coverage changes."""
    if not previous_release.strip() or not current_release.strip():
        raise ValueError("release IDs cannot be empty")
    if previous_release == current_release:
        raise ValueError("release comparison requires two different releases")
    previous_by_key = _index_snapshots(previous, previous_release)
    current_by_key = _index_snapshots(current, current_release)
    comparisons: list[MetricComparison] = []

    for key in sorted(previous_by_key.keys() | current_by_key.keys()):
        before = previous_by_key.get(key)
        after = current_by_key.get(key)
        if before is None or after is None:
            reason = (
                "new metric requires review"
                if before is None
                else "metric missing from new release"
            )
            comparisons.append(
                MetricComparison(
                    key=key,
                    status=ComparisonStatus.REVIEW_REQUIRED,
                    previous=before,
                    current=after,
                    absolute_change=None,
                    relative_change=None,
                    reasons=(reason,),
                )
            )
            continue

        if key.metric not in thresholds:
            raise ValueError(f"no change threshold configured for metric {key.metric!r}")
        threshold = thresholds[key.metric]
        absolute_change = after.value - before.value
        if before.value == 0:
            relative_change = 0.0 if after.value == 0 else None
        else:
            relative_change = absolute_change / abs(before.value)

        reasons: list[str] = []
        if threshold.max_absolute_change is not None and (
            abs(absolute_change) > threshold.max_absolute_change
        ):
            reasons.append(
                f"absolute change {absolute_change:g} exceeds {threshold.max_absolute_change:g}"
            )
        if threshold.max_relative_change is not None:
            if relative_change is None:
                reasons.append("relative change is undefined from a zero baseline")
            elif abs(relative_change) > threshold.max_relative_change:
                reasons.append(
                    f"relative change {relative_change:.1%} exceeds "
                    f"{threshold.max_relative_change:.1%}"
                )
        comparisons.append(
            MetricComparison(
                key=key,
                status=(
                    ComparisonStatus.REVIEW_REQUIRED if reasons else ComparisonStatus.VALIDATED
                ),
                previous=before,
                current=after,
                absolute_change=absolute_change,
                relative_change=relative_change,
                reasons=tuple(reasons),
            )
        )

    status = (
        ComparisonStatus.REVIEW_REQUIRED
        if any(item.status is ComparisonStatus.REVIEW_REQUIRED for item in comparisons)
        else ComparisonStatus.VALIDATED
    )
    return ReleaseComparisonReport(
        previous_release=previous_release,
        current_release=current_release,
        status=status,
        comparisons=tuple(comparisons),
    )
