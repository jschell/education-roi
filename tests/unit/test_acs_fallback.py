import polars as pl
import pytest

from education_roi.acs.fallback import (
    FallbackCandidate,
    FallbackStatus,
    SampleScope,
    SupportThresholds,
    fallback_weighted_quantile,
)


def candidate(level: str, geography: str, age: str, values: list[float]) -> FallbackCandidate:
    return FallbackCandidate(
        scope=SampleScope(level=level, geography=geography, age=age, major="computer-science"),
        frame=pl.DataFrame(
            {
                "wage_salary_adjusted": values,
                "person_weight": [10.0] * len(values),
            }
        ),
    )


def test_fallback_selects_first_supported_scope_and_discloses_rejections() -> None:
    result = fallback_weighted_quantile(
        [
            candidate("seattle-exact-age", "Seattle", "32", [100.0, 110.0]),
            candidate("seattle-age-band", "Seattle", "30-34", [100.0, 120.0, 140.0]),
            candidate("washington-age-band", "Washington", "30-34", [90.0] * 4),
        ],
        0.5,
        SupportThresholds(min_unweighted_n=3, min_weighted_n=25),
    )

    assert result.status is FallbackStatus.SELECTED
    assert result.estimate is not None
    assert result.estimate.value == 120.0
    assert result.selected_scope is not None
    assert result.selected_scope.level == "seattle-age-band"
    assert result.fallback_used is True
    assert [attempt.scope.level for attempt in result.attempts] == [
        "seattle-exact-age",
        "seattle-age-band",
    ]
    assert result.attempts[0].failures == (
        "unweighted_n 2 < 3",
        "weighted_n 20 < 25",
    )


def test_first_supported_scope_does_not_report_fallback() -> None:
    result = fallback_weighted_quantile(
        [candidate("exact", "Seattle", "32", [100.0, 120.0])],
        0.5,
        SupportThresholds(min_unweighted_n=2, min_weighted_n=20),
    )
    assert result.status is FallbackStatus.SELECTED
    assert result.fallback_used is False


def test_exhausted_hierarchy_returns_insufficient_data() -> None:
    result = fallback_weighted_quantile(
        [
            candidate("exact", "Seattle", "32", [100.0]),
            candidate("state", "Washington", "30-34", [100.0, 120.0]),
        ],
        0.5,
        SupportThresholds(min_unweighted_n=3, min_weighted_n=30),
    )
    assert result.status is FallbackStatus.INSUFFICIENT_DATA
    assert result.estimate is None
    assert result.selected_scope is None
    assert result.fallback_used is False
    assert len(result.attempts) == 2
    assert all(not attempt.sufficient for attempt in result.attempts)


def test_support_excludes_null_values_and_nonpositive_weights() -> None:
    frame = pl.DataFrame(
        {
            "wage_salary_adjusted": [100.0, None, 300.0],
            "person_weight": [10.0, 10.0, 0.0],
        }
    )
    result = fallback_weighted_quantile(
        [FallbackCandidate(SampleScope("exact", "Seattle", "32", "computer-science"), frame)],
        0.5,
        SupportThresholds(min_unweighted_n=2, min_weighted_n=1),
    )
    assert result.status is FallbackStatus.INSUFFICIENT_DATA
    assert result.attempts[0].unweighted_n == 1
    assert result.attempts[0].weighted_n == 10.0


def test_fallback_contract_rejects_ambiguous_or_invalid_configuration() -> None:
    exact = candidate("exact", "Seattle", "32", [100.0])
    with pytest.raises(ValueError, match="at least one"):
        fallback_weighted_quantile([], 0.5, SupportThresholds(1, 1))
    with pytest.raises(ValueError, match="unique"):
        fallback_weighted_quantile([exact, exact], 0.5, SupportThresholds(1, 1))
    with pytest.raises(ValueError, match="quantile"):
        fallback_weighted_quantile([exact], 1.1, SupportThresholds(2, 1))
    with pytest.raises(ValueError, match="at least 1"):
        SupportThresholds(0, 1)
    with pytest.raises(ValueError, match="greater than zero"):
        SupportThresholds(1, 0)
