"""Unit tests for the revenue-weighted feature-gap scoring formula."""
import math

import pytest

from app.modules.customer_intelligence.scoring import compute_feature_gap_score


def test_zero_inputs_yield_zero_score() -> None:
    assert compute_feature_gap_score(0.0, 0, 0) == 0.0


def test_score_scales_with_revenue_and_customer_breadth() -> None:
    low = compute_feature_gap_score(10_000.0, 1, 1)
    high = compute_feature_gap_score(100_000.0, 5, 1)
    assert high > low


def test_mention_volume_is_log_dampened_not_linear() -> None:
    """One chatty customer filing many tickets must not dominate the score
    the way widening revenue/customer breadth does."""
    base = compute_feature_gap_score(50_000.0, 2, 1)
    ten_x_mentions = compute_feature_gap_score(50_000.0, 2, 10)
    hundred_x_mentions = compute_feature_gap_score(50_000.0, 2, 100)

    assert base < ten_x_mentions < hundred_x_mentions
    # Growth from 10x mentions -> 100x mentions must be sub-linear (log, not
    # linear) relative to growth from 1 -> 10 mentions.
    first_jump = ten_x_mentions - base
    second_jump = hundred_x_mentions - ten_x_mentions
    assert second_jump < first_jump * 10


def test_negative_inputs_are_clamped_to_zero() -> None:
    assert compute_feature_gap_score(-500.0, -3, -7) == 0.0


def test_matches_reference_formula() -> None:
    total_arr, customers, mentions = 25_000.0, 4, 6
    expected = round(total_arr * customers * (1.0 + math.log1p(mentions)), 2)
    assert compute_feature_gap_score(total_arr, customers, mentions) == expected


@pytest.mark.parametrize(
    ("total_arr", "customers", "mentions"),
    [
        (0.0, 5, 5),
        (10_000.0, 0, 5),
        (10_000.0, 5, 0),
    ],
)
def test_any_zero_dimension_except_mentions_boost_zeroes_score(
    total_arr: float, customers: int, mentions: int
) -> None:
    """Revenue and breadth are multiplicative gates: zero either one and the
    whole score collapses, even if mentions are non-zero."""
    if total_arr == 0.0 or customers == 0:
        assert compute_feature_gap_score(total_arr, customers, mentions) == 0.0
