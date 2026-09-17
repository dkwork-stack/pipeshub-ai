"""Behavioural tests for MySQLIntelligenceQueryRepository against an in-memory SQLite engine.

The repository is written in portable SQLAlchemy Core (window functions,
EXISTS, GROUP BY + group_concat), all of which SQLite >= 3.25 supports, so the
same statements that run on MySQL in production can be exercised here without
a database server. What these tests pin down: org isolation, latest-snapshot
resolution, filter semantics, pagination totals and per-customer insight
aggregation — the logic most likely to regress silently.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.intelligence import CustomerFilter, FeatureGapFilter, MentionFilter
from app.services.intelligence_store.mysql.mysql_intelligence_query_repository import (
    MySQLIntelligenceQueryRepository,
)
from app.services.intelligence_store.mysql.schema import (
    customers,
    feature_gap_mentions,
    feature_gap_scores,
    feature_gaps,
    metadata,
    revenue_snapshots,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

ORG = "org-a"
OTHER_ORG = "org-b"
T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _mention(org: str, cust: str, feature: str, event: str, connector: str, days: int, conf: float = 0.8) -> dict:
    return {
        "org_id": org,
        "external_customer_id": cust,
        "feature_name": feature,
        "description": f"{cust} wants {feature}",
        "confidence": conf,
        "excerpt": f"we need {feature}",
        "source_connector": connector,
        "source_type": "support_ticket",
        "external_event_id": event,
        "citation_url": f"https://src/{event}",
        "occurred_at": T0 + timedelta(days=days),
        "created_at": T0,
    }


def _snapshot(
    org: str,
    cust: str,
    mrr: float,
    arr: float,
    days: int,
    *,
    seats_used: int | None = None,
    seats_licensed: int | None = None,
    features: list[str] | None = None,
) -> dict:
    # Uniform keys on every row: SQLAlchemy executemany compiles against the
    # first row's keys and silently drops columns missing from it.
    return {
        "org_id": org,
        "external_customer_id": cust,
        "source_connector": "chargebee",
        "mrr": mrr,
        "arr": arr,
        "seats_used": seats_used,
        "seats_licensed": seats_licensed,
        "consumed_features": features,
        "renewal_date": None,
        "snapshot_at": T0 + timedelta(days=days),
    }


def _score(org: str, feature: str, arr: float, customers_n: int, mentions_n: int, score: float) -> dict:
    return {
        "org_id": org,
        "feature_name": feature,
        "total_arr_at_stake": arr,
        "total_mrr_at_stake": arr / 12,
        "customer_count": customers_n,
        "mention_count": mentions_n,
        "score": score,
        "top_customers": ["Acme"],
        "updated_at": T0,
    }


@pytest.fixture
async def repo() -> AsyncIterator[MySQLIntelligenceQueryRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.execute(
            insert(customers),
            [
                {"org_id": ORG, "external_customer_id": "acme", "customer_name": "Acme Corp", "created_at": T0, "updated_at": T0},
                {"org_id": ORG, "external_customer_id": "globex", "customer_name": "Globex", "created_at": T0, "updated_at": T0},
                {"org_id": ORG, "external_customer_id": "initech", "customer_name": "Initech", "created_at": T0, "updated_at": T0},
                {"org_id": OTHER_ORG, "external_customer_id": "acme", "customer_name": "Acme (other org)", "created_at": T0, "updated_at": T0},
            ],
        )
        await conn.execute(
            insert(revenue_snapshots),
            [
                # acme: old snapshot 50k, newer snapshot 120k -> latest must be 120k
                _snapshot(ORG, "acme", 4000, 50_000, 0),
                _snapshot(ORG, "acme", 10_000, 120_000, 10, seats_used=40, seats_licensed=50, features=["sso"]),
                _snapshot(ORG, "globex", 2500, 30_000, 0),
                _snapshot(OTHER_ORG, "acme", 1, 999_999, 0),
            ],
        )
        await conn.execute(
            insert(feature_gaps),
            [
                {"org_id": ORG, "feature_name": "Bulk CSV export", "created_at": T0},
                {"org_id": ORG, "feature_name": "SSO", "created_at": T0},
                {"org_id": ORG, "feature_name": "Dark mode", "created_at": T0},
                {"org_id": OTHER_ORG, "feature_name": "Bulk CSV export", "created_at": T0},
            ],
        )
        await conn.execute(
            insert(feature_gap_mentions),
            [
                _mention(ORG, "acme", "Bulk CSV export", "t1", "freshdesk", 1, 0.9),
                _mention(ORG, "acme", "Bulk CSV export", "t2", "gong", 3, 0.7),
                _mention(ORG, "acme", "SSO", "t3", "freshdesk", 2),
                _mention(ORG, "globex", "Bulk CSV export", "t4", "file_upload", 5),
                _mention(ORG, "initech", "Dark mode", "t5", "file_upload", 6),
                _mention(OTHER_ORG, "acme", "Bulk CSV export", "x1", "zendesk", 1),
            ],
        )
        await conn.execute(
            insert(feature_gap_scores),
            [
                _score(ORG, "Bulk CSV export", 150_000, 2, 3, 900),
                _score(ORG, "SSO", 120_000, 1, 1, 500),
                _score(ORG, "Dark mode", 0, 1, 1, 10),
                _score(OTHER_ORG, "Bulk CSV export", 999_999, 1, 1, 9999),
            ],
        )
    yield MySQLIntelligenceQueryRepository(logging.getLogger("test"), engine)
    await engine.dispose()


async def test_overview_counts_arr_once_per_customer_and_is_org_scoped(repo) -> None:
    overview = await repo.get_overview(ORG, top_n=2)

    # acme (latest 120k) + globex (30k); initech has no revenue; other org excluded.
    assert overview.total_arr_at_stake == 150_000
    assert overview.total_mrr_at_stake == 12_500
    assert overview.customer_count == 3
    assert overview.feature_gap_count == 3
    assert overview.mention_count == 5
    assert overview.source_connectors == ["file_upload", "freshdesk", "gong"]
    assert [g.feature_name for g in overview.top_feature_gaps] == ["Bulk CSV export", "SSO"]
    assert [c.customer_name for c in overview.top_customers] == ["Acme Corp", "Globex"]
    assert overview.last_mention_at == T0 + timedelta(days=6)


async def test_search_feature_gaps_filters_and_pagination(repo) -> None:
    items, total = await repo.search_feature_gaps(ORG, FeatureGapFilter(), limit=2, offset=0)
    assert total == 3
    assert [i.feature_name for i in items] == ["Bulk CSV export", "SSO"]

    items, total = await repo.search_feature_gaps(ORG, FeatureGapFilter(), limit=2, offset=2)
    assert total == 3
    assert [i.feature_name for i in items] == ["Dark mode"]

    items, _ = await repo.search_feature_gaps(ORG, FeatureGapFilter(query="csv"), limit=10, offset=0)
    assert [i.feature_name for i in items] == ["Bulk CSV export"]

    items, _ = await repo.search_feature_gaps(ORG, FeatureGapFilter(min_arr=100_000), limit=10, offset=0)
    assert {i.feature_name for i in items} == {"Bulk CSV export", "SSO"}

    items, _ = await repo.search_feature_gaps(ORG, FeatureGapFilter(source_connector="gong"), limit=10, offset=0)
    assert [i.feature_name for i in items] == ["Bulk CSV export"]

    items, total = await repo.search_feature_gaps(
        ORG, FeatureGapFilter(external_customer_id="initech"), limit=10, offset=0
    )
    assert total == 1
    assert items[0].feature_name == "Dark mode"


async def test_feature_gap_detail_affected_customers_and_mention_filter(repo) -> None:
    detail = await repo.get_feature_gap(ORG, "Bulk CSV export", MentionFilter())
    assert detail is not None
    assert detail.score.score == 900
    assert [(c.external_customer_id, c.arr, c.mention_count) for c in detail.affected_customers] == [
        ("acme", 120_000, 2),
        ("globex", 30_000, 1),
    ]
    assert [m.external_event_id for m in detail.mentions] == ["t4", "t2", "t1"]

    detail = await repo.get_feature_gap(ORG, "Bulk CSV export", MentionFilter(external_customer_id="acme"))
    assert [m.external_event_id for m in detail.mentions] == ["t2", "t1"]

    detail = await repo.get_feature_gap(ORG, "Bulk CSV export", MentionFilter(source_connector="gong"))
    assert [m.external_event_id for m in detail.mentions] == ["t2"]

    assert await repo.get_feature_gap(ORG, "Nope", MentionFilter()) is None
    assert await repo.get_feature_gap(OTHER_ORG, "SSO", MentionFilter()) is None


async def test_search_customers_latest_snapshot_insights_and_filters(repo) -> None:
    items, total = await repo.search_customers(ORG, CustomerFilter(), limit=10, offset=0, top_insights=1)
    assert total == 3
    assert [c.external_customer_id for c in items] == ["acme", "globex", "initech"]

    acme = items[0]
    assert acme.latest_revenue is not None
    assert acme.latest_revenue.arr == 120_000
    assert acme.latest_revenue.consumed_features == ["sso"]
    assert acme.feature_gap_count == 2
    assert acme.mention_count == 3
    assert len(acme.top_insights) == 1
    assert acme.top_insights[0].feature_name == "Bulk CSV export"
    assert acme.top_insights[0].mention_count == 2
    assert acme.top_insights[0].source_connectors == ["freshdesk", "gong"]

    initech = items[2]
    assert initech.latest_revenue is None
    assert initech.feature_gap_count == 1

    items, _ = await repo.search_customers(ORG, CustomerFilter(query="GLOB"), limit=10, offset=0)
    assert [c.customer_name for c in items] == ["Globex"]

    items, _ = await repo.search_customers(ORG, CustomerFilter(min_arr=100_000), limit=10, offset=0)
    assert [c.external_customer_id for c in items] == ["acme"]

    items, _ = await repo.search_customers(ORG, CustomerFilter(source_connector="file_upload"), limit=10, offset=0)
    assert {c.external_customer_id for c in items} == {"globex", "initech"}

    items, total = await repo.search_customers(ORG, CustomerFilter(), limit=1, offset=1)
    assert total == 3
    assert [c.external_customer_id for c in items] == ["globex"]


async def test_customer_detail_and_org_isolation(repo) -> None:
    detail = await repo.get_customer(ORG, "acme", MentionFilter())
    assert detail is not None
    assert detail.customer_name == "Acme Corp"
    assert detail.latest_revenue.arr == 120_000
    assert [i.feature_name for i in detail.insights] == ["Bulk CSV export", "SSO"]
    assert [m.external_event_id for m in detail.mentions] == ["t2", "t3", "t1"]

    detail = await repo.get_customer(ORG, "acme", MentionFilter(source_connector="gong"))
    assert [m.external_event_id for m in detail.mentions] == ["t2"]

    other = await repo.get_customer(OTHER_ORG, "acme", MentionFilter())
    assert other.customer_name == "Acme (other org)"
    assert other.latest_revenue.arr == 999_999
    assert [m.external_event_id for m in other.mentions] == ["x1"]

    assert await repo.get_customer(ORG, "unknown", MentionFilter()) is None


async def test_list_source_connectors(repo) -> None:
    assert await repo.list_source_connectors(ORG) == ["file_upload", "freshdesk", "gong"]
    assert await repo.list_source_connectors(OTHER_ORG) == ["zendesk"]
    assert await repo.list_source_connectors("empty") == []
