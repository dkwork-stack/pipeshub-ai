"""Integration tests for MySQLIntelligenceStore against a real MySQL server.

Requires a running MySQL instance, e.g.:
  docker run --rm -p 3399:3306 -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
    -e MYSQL_DATABASE=pipeshub_intelligence_test mysql:8.0

Run explicitly:
  pytest tests/integration/customer_intelligence/ -m integration --timeout=120

Environment variables used (all optional, sane localhost defaults):
  INTELLIGENCE_TEST_MYSQL_HOST (default: localhost)
  INTELLIGENCE_TEST_MYSQL_PORT (default: 3399)
  INTELLIGENCE_TEST_MYSQL_USER (default: root)
  INTELLIGENCE_TEST_MYSQL_PASSWORD (default: "")
  INTELLIGENCE_TEST_MYSQL_DATABASE (default: pipeshub_intelligence_test)

If the server is unreachable, every test in this module is skipped rather
than failed — mirrors tests/integration/vector_db/conftest.py.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator

import pytest

from app.models.intelligence import (
    CustomerRevenueSnapshot,
    FeatureGapMentionRecord,
    SignalSourceType,
)
from app.services.intelligence_store.mysql.mysql_intelligence_store import (
    MySQLIntelligenceStore,
)

pytestmark = pytest.mark.integration


def _dsn() -> str:
    host = os.environ.get("INTELLIGENCE_TEST_MYSQL_HOST", "localhost")
    port = os.environ.get("INTELLIGENCE_TEST_MYSQL_PORT", "3399")
    user = os.environ.get("INTELLIGENCE_TEST_MYSQL_USER", "root")
    password = os.environ.get("INTELLIGENCE_TEST_MYSQL_PASSWORD", "")
    database = os.environ.get("INTELLIGENCE_TEST_MYSQL_DATABASE", "pipeshub_intelligence_test")
    auth = f"{user}:{password}" if password else user
    return f"mysql+aiomysql://{auth}@{host}:{port}/{database}"


@pytest.fixture
async def store() -> AsyncIterator[MySQLIntelligenceStore]:
    s = MySQLIntelligenceStore(logger=logging.getLogger("test"), dsn=_dsn())
    connected = await s.connect()
    if not connected:
        pytest.skip(f"MySQL not reachable at {_dsn()} — start it via the docstring instructions")
    yield s
    await s.close()


def _org_id() -> str:
    return f"test-org-{uuid.uuid4().hex[:8]}"


async def test_upsert_customer_and_revenue_snapshot_then_list(store) -> None:
    org_id = _org_id()
    snapshot = CustomerRevenueSnapshot(
        org_id=org_id,
        external_customer_id="cust-acme",
        customer_name="Acme Corp",
        mrr=10_000.0,
        arr=120_000.0,
        seats_used=42,
        seats_licensed=50,
    )
    await store.upsert_revenue_snapshot(snapshot)

    customers = await store.list_customers(org_id)
    assert len(customers) == 1
    assert customers[0]["customer"]["customer_name"] == "Acme Corp"
    assert customers[0]["latest_revenue_snapshot"]["arr"] == 120_000.0


async def test_feature_gap_mention_recomputes_score(store) -> None:
    org_id = _org_id()
    await store.upsert_revenue_snapshot(
        CustomerRevenueSnapshot(
            org_id=org_id, external_customer_id="cust-1", customer_name="Beta Inc", arr=50_000.0
        )
    )
    await store.upsert_feature_gap_mention(
        FeatureGapMentionRecord(
            org_id=org_id,
            external_customer_id="cust-1",
            feature_name="Bulk CSV export",
            description="Wants to export tickets in bulk",
            confidence=0.9,
            excerpt="We really need bulk export",
            source_connector="freshdesk",
            source_type=SignalSourceType.SUPPORT_TICKET,
            external_event_id="ticket-1",
            occurred_at=__import__("datetime").datetime.utcnow(),
        )
    )

    scores = await store.list_feature_gap_scores(org_id)
    assert len(scores) == 1
    assert scores[0].feature_name == "Bulk CSV export"
    assert scores[0].customer_count == 1
    assert scores[0].mention_count == 1
    assert scores[0].total_arr_at_stake == 50_000.0
    assert scores[0].score > 0


async def test_reingesting_same_event_id_is_idempotent_not_duplicated(store) -> None:
    org_id = _org_id()
    await store.upsert_revenue_snapshot(
        CustomerRevenueSnapshot(
            org_id=org_id, external_customer_id="cust-1", customer_name="Beta Inc", arr=50_000.0
        )
    )
    mention = FeatureGapMentionRecord(
        org_id=org_id,
        external_customer_id="cust-1",
        feature_name="SSO support",
        description="Needs SSO",
        confidence=0.8,
        excerpt="Please add SSO",
        source_connector="salesforce",
        source_type=SignalSourceType.CRM_NOTE,
        external_event_id="case-1",
        occurred_at=__import__("datetime").datetime.utcnow(),
    )
    await store.upsert_feature_gap_mention(mention)
    await store.upsert_feature_gap_mention(mention)  # re-processing the same event id

    score, mentions = await store.get_feature_gap_detail(org_id, "SSO support")
    assert score.mention_count == 1
    assert len(mentions) == 1


async def test_get_feature_gap_detail_returns_none_for_unknown_feature(store) -> None:
    org_id = _org_id()
    score, mentions = await store.get_feature_gap_detail(org_id, "does-not-exist")
    assert score is None
    assert mentions == []
