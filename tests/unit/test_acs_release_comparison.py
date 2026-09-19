import pytest

from education_roi.acs.release_comparison import (
    ChangeThreshold,
    ComparisonStatus,
    MetricKey,
    MetricSnapshot,
    compare_release_snapshots,
)


def snapshot(release: str, value: float, *, geography: str = "wa") -> MetricSnapshot:
    return MetricSnapshot(
        release_id=release,
        key=MetricKey("median_earnings", (("geography", geography), ("major", "cs"))),
        value=value,
        unweighted_n=100,
        weighted_n=10_000,
    )


def test_normal_release_change_validates_and_allows_promotion() -> None:
    report = compare_release_snapshots(
        "2024-5yr",
        "2025-5yr",
        [snapshot("2024-5yr", 138_400)],
        [snapshot("2025-5yr", 145_000)],
        {"median_earnings": ChangeThreshold(max_relative_change=0.25)},
    )
    comparison = report.comparisons[0]
    assert report.status is ComparisonStatus.VALIDATED
    assert report.promotion_allowed is True
    assert comparison.absolute_change == 6_600
    assert comparison.relative_change == pytest.approx(0.0476878613)
    assert comparison.previous is not None
    assert comparison.previous.unweighted_n == 100


def test_large_release_change_requires_review_and_blocks_promotion() -> None:
    report = compare_release_snapshots(
        "2024-5yr",
        "2025-5yr",
        [snapshot("2024-5yr", 138_400)],
        [snapshot("2025-5yr", 189_700)],
        {"median_earnings": ChangeThreshold(max_relative_change=0.25)},
    )
    comparison = report.comparisons[0]
    assert report.status is ComparisonStatus.REVIEW_REQUIRED
    assert report.promotion_allowed is False
    assert comparison.relative_change == pytest.approx(0.37066474)
    assert comparison.reasons == ("relative change 37.1% exceeds 25.0%",)


def test_absolute_threshold_and_zero_baseline_are_conservative() -> None:
    report = compare_release_snapshots(
        "old",
        "new",
        [snapshot("old", 0)],
        [snapshot("new", 2)],
        {"median_earnings": ChangeThreshold(max_relative_change=0.25, max_absolute_change=5)},
    )
    assert report.status is ComparisonStatus.REVIEW_REQUIRED
    assert report.comparisons[0].relative_change is None
    assert report.comparisons[0].reasons == ("relative change is undefined from a zero baseline",)


def test_added_and_missing_metric_coverage_require_review() -> None:
    report = compare_release_snapshots(
        "old",
        "new",
        [snapshot("old", 100, geography="wa")],
        [snapshot("new", 100, geography="or")],
        {"median_earnings": ChangeThreshold(max_relative_change=0.25)},
    )
    assert report.status is ComparisonStatus.REVIEW_REQUIRED
    assert {item.reasons[0] for item in report.comparisons} == {
        "new metric requires review",
        "metric missing from new release",
    }


def test_comparison_rejects_uncontrolled_or_malformed_inputs() -> None:
    old = snapshot("old", 100)
    new = snapshot("new", 101)
    with pytest.raises(ValueError, match="no change threshold"):
        compare_release_snapshots("old", "new", [old], [new], {})
    with pytest.raises(ValueError, match="duplicate"):
        compare_release_snapshots(
            "old",
            "new",
            [old, old],
            [new],
            {"median_earnings": ChangeThreshold(max_relative_change=0.25)},
        )
    with pytest.raises(ValueError, match="does not match"):
        compare_release_snapshots(
            "wrong",
            "new",
            [old],
            [new],
            {"median_earnings": ChangeThreshold(max_relative_change=0.25)},
        )
    with pytest.raises(ValueError, match="at least one"):
        ChangeThreshold()
    with pytest.raises(ValueError, match="finite and nonnegative"):
        ChangeThreshold(max_relative_change=float("nan"))
