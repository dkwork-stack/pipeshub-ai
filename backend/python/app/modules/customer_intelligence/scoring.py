"""Revenue-weighted feature-gap scoring.

Kept as a single, pure, injectable function so the prioritization formula can
change without touching ingestion, storage, or API code. Per product
decision: rank by revenue at stake AND demand breadth (number of distinct
customers/mentions pending on this feature) — a gap requested by many
mid-market accounts should be able to outrank a single whale's request.
"""
from __future__ import annotations

import math


def compute_feature_gap_score(
    total_arr_at_stake: float,
    customer_count: int,
    mention_count: int,
) -> float:
    """Return a single sortable priority score for a feature gap.

    ``total_arr_at_stake``: sum of ARR across every distinct customer who
        raised this gap (revenue impact).
    ``customer_count``: distinct customers requesting it (demand breadth).
    ``mention_count``: total mentions across all customers/sources (demand
        intensity/pending volume) — a log dampens runaway weight from one
        chatty customer's many tickets on the same gap.

    Score = ARR at stake * customers requesting it, boosted by mention
    volume on a log scale so it never dominates revenue.
    """
    revenue_component = max(total_arr_at_stake, 0.0)
    breadth_component = max(customer_count, 0)
    volume_boost = 1.0 + math.log1p(max(mention_count, 0))
    return round(revenue_component * breadth_component * volume_boost, 2)
