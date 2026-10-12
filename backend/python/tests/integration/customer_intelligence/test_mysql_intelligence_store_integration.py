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
    AuditEntry,
    CustomerFilter,
    CustomerRevenueSnapshot,
    FeatureGapFilter,
    FeatureGapMentionRecord,
    MentionFilter,
    SignalSourceType,
)
from app.services.intelligence_store.mysql.mysql_intelligence_query_repository import (
    MySQLIntelligenceQueryRepository,
)
from app.services.intelligence_store.mysql.mysql_intelligence_store import (
    MySQLIntelligenceStore,
)
from app.services.intelligence_store.mysql.sql import utcnow

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


def _repo(store: MySQLIntelligenceStore) -> MySQLIntelligenceQueryRepository:
    return MySQLIntelligenceQueryRepository(logger=logging.getLogger("test"), engine=store.engine)


def _mention(org_id: str, customer: str, feature: str, event: str, **attrs) -> FeatureGapMentionRecord:
    return FeatureGapMentionRecord(
        org_id=org_id,
        external_customer_id=customer,
        feature_name=feature,
        description=f"Wants {feature}",
        confidence=0.9,
        excerpt=f"We really need {feature}",
        source_connector="freshdesk",
        source_type=SignalSourceType.SUPPORT_TICKET,
        external_event_id=event,
        occurred_at=utcnow(),
        **attrs,
    )


async def test_upsert_customer_and_revenue_snapshot_then_list(store) -> None:
    org_id = _org_id()
    await store.upsert_revenue_snapshot(
        CustomerRevenueSnapshot(
            org_id=org_id, external_customer_id="cust-acme", customer_name="Acme Corp",
            mrr=10_000.0, arr=120_000.0, seats_used=42, seats_licensed=50,
        )
    )
    customers, total = await _repo(store).search_customers(org_id, CustomerFilter(), limit=10, offset=0)
    assert total == 1
    assert customers[0].customer_name == "Acme Corp"
    assert customers[0].latest_revenue.arr == 120_000.0


async def test_feature_gap_mention_recomputes_score_with_trend(store) -> None:
    org_id = _org_id()
    await store.upsert_revenue_snapshot(
        CustomerRevenueSnapshot(org_id=org_id, external_customer_id="cust-1", customer_name="Beta Inc", arr=50_000.0)
    )
    await store.upsert_feature_gap_mention(_mention(org_id, "cust-1", "Bulk CSV export", "ticket-1", churn_risk=True))

    scores, _ = await _repo(store).search_feature_gaps(org_id, FeatureGapFilter(), limit=10, offset=0)
    (score,) = scores
    assert (score.feature_name, score.customer_count, score.mention_count) == ("Bulk CSV export", 1, 1)
    assert score.total_arr_at_stake == 50_000.0
    assert score.score > 0
    assert score.trend.churn_risk_count == 1


async def test_reingesting_same_event_id_is_idempotent_not_duplicated(store) -> None:
    org_id = _org_id()
    mention = _mention(org_id, "cust-1", "SSO support", "case-1")
    await store.upsert_feature_gap_mention(mention)
    await store.upsert_feature_gap_mention(mention)

    detail = await _repo(store).get_feature_gap(org_id, "SSO support", MentionFilter())
    assert detail.score.mention_count == 1
    assert len(detail.mentions) == 1


async def test_erasure_and_audit_on_mysql(store) -> None:
    org_id = _org_id()
    await store.upsert_customer(org_id, "cust-1", "Beta Inc")
    await store.upsert_feature_gap_mention(_mention(org_id, "cust-1", "SSO support", "case-1", source_record_id="rec-1"))
    assert (await store.erase_source_record(org_id, "rec-1")).feature_gap_mentions == 1
    assert (await store.erase_customer(org_id, "cust-1")).customers == 1
    await store.record_audit(AuditEntry(org_id=org_id, action="erasure.customer", target_type="customer", target_id="cust-1"))
    entries, total = await store.list_audit(org_id)
    assert total == 1 and entries[0].action == "erasure.customer"
