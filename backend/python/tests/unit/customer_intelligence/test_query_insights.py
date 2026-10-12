"""Read-side insights: trends, lifecycle status, customer health, emerging asks.

Data is written through the real store so the read model is exercised
against exactly what ingestion produces.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.intelligence import (
    AskIntent,
    CustomerFilter,
    CustomerRevenueSnapshot,
    FeatureGapFilter,
    FeatureGapMentionRecord,
    IntelligenceTopic,
    MentionFilter,
    PainPointFilter,
    PainPointMentionRecord,
    SignalSourceType,
    TopicGuidanceUpdate,
    TopicKind,
    TopicStatus,
)
from app.services.intelligence_store.mysql.mysql_intelligence_query_repository import (
    MySQLIntelligenceQueryRepository,
)
from app.services.intelligence_store.mysql.sql import utcnow
from tests.unit.customer_intelligence.fakes import LOG, ORG_ID, sqlite_store


@pytest.fixture
async def env():
    store = await sqlite_store()
    repo = MySQLIntelligenceQueryRepository(logger=LOG, engine=store.engine)
    yield store, repo
    await store.close()


async def _gap(store, customer, feature, event, days_ago=1, **attrs) -> None:
    await store.upsert_customer(ORG_ID, customer, customer.title())
    await store.upsert_feature_gap_mention(
        FeatureGapMentionRecord(
            org_id=ORG_ID, external_customer_id=customer, feature_name=feature, description="d",
            confidence=0.9, excerpt="x", source_connector="zammad", source_type=SignalSourceType.SUPPORT_TICKET,
            external_event_id=event, occurred_at=utcnow() - timedelta(days=days_ago), **attrs,
        )
    )


async def _pain(store, customer, topic, event, days_ago=1, **attrs) -> None:
    await store.upsert_customer(ORG_ID, customer, customer.title())
    await store.upsert_pain_point_mention(
        PainPointMentionRecord(
            org_id=ORG_ID, external_customer_id=customer, topic_name=topic, summary=topic,
            confidence=0.8, excerpt="x", source_connector="zammad", source_type=SignalSourceType.SUPPORT_TICKET,
            external_event_id=event, occurred_at=utcnow() - timedelta(days=days_ago), **attrs,
        )
    )


async def _arr(store, customer, arr) -> None:
    await store.upsert_revenue_snapshot(
        CustomerRevenueSnapshot(org_id=ORG_ID, source_connector="file_upload", external_customer_id=customer,
                                customer_name=customer.title(), arr=arr, mrr=arr / 12)
    )


async def test_feature_gap_rows_carry_trend_and_status_and_filter_by_both(env) -> None:
    store, repo = env
    await _gap(store, "acme", "SSO", "t1", intent="feature_request")
    await _gap(store, "acme", "Slow reports", "t2", intent="performance")
    sso = await store.upsert_topic(IntelligenceTopic(org_id=ORG_ID, kind=TopicKind.FEATURE_GAP, canonical_name="SSO"))
    await store.update_topic_guidance(ORG_ID, sso.id, TopicGuidanceUpdate(status=TopicStatus.PLANNED))

    rows, total = await repo.search_feature_gaps(ORG_ID, FeatureGapFilter(), limit=10, offset=0)
    by_name = {r.feature_name: r for r in rows}
    assert total == 2
    assert by_name["SSO"].status == TopicStatus.PLANNED
    assert by_name["Slow reports"].status == TopicStatus.OPEN
    assert by_name["SSO"].trend.mentions_last_30d == 1

    planned, _ = await repo.search_feature_gaps(ORG_ID, FeatureGapFilter(status=TopicStatus.PLANNED), limit=10, offset=0)
    assert [r.feature_name for r in planned] == ["SSO"]
    open_, _ = await repo.search_feature_gaps(ORG_ID, FeatureGapFilter(status=TopicStatus.OPEN), limit=10, offset=0)
    assert [r.feature_name for r in open_] == ["Slow reports"]
    perf, _ = await repo.search_feature_gaps(ORG_ID, FeatureGapFilter(intent=AskIntent.PERFORMANCE), limit=10, offset=0)
    assert [r.feature_name for r in perf] == ["Slow reports"]


async def test_feature_gap_detail_mentions_expose_attributes(env) -> None:
    store, repo = env
    await _gap(store, "acme", "SSO", "t1", tone="angry", urgency="critical", business_impact="blocks rollout",
               workaround="shared logins", competitor="Okta", churn_risk=True, speaker_role="customer")
    detail = await repo.get_feature_gap(ORG_ID, "SSO", MentionFilter())
    (mention,) = detail.mentions
    assert (mention.tone.value, mention.urgency.value, mention.business_impact) == ("angry", "critical", "blocks rollout")
    assert (mention.workaround, mention.competitor, mention.churn_risk) == ("shared logins", "Okta", True)
    assert detail.score.trend.churn_risk_count == 1


async def test_pain_points_have_top_customers_trend_status_and_filter(env) -> None:
    store, repo = env
    await _pain(store, "acme", "Login loops", "p1", sentiment="Negative")
    await _pain(store, "acme", "Login loops", "p2", sentiment="Negative", days_ago=45)
    await _pain(store, "globex", "Login loops", "p3", sentiment="Neutral")
    await _pain(store, "globex", "Confusing UI", "p4")
    topic = (await store.list_topics(ORG_ID, TopicKind.PAIN_POINT))[0]
    await store.update_topic_guidance(ORG_ID, topic.id, TopicGuidanceUpdate(status=TopicStatus.UNDER_REVIEW))

    rows, total = await repo.search_pain_points(ORG_ID, PainPointFilter(), limit=10, offset=0)
    login = next(r for r in rows if r.topic_name == "Login loops")
    assert total == 2
    assert login.top_customers == ["Acme", "Globex"]
    assert (login.trend.mentions_last_30d, login.trend.mentions_prev_30d) == (2, 1)
    assert login.trend.negative_share == pytest.approx(2 / 3, abs=1e-3)

    reviewed, _ = await repo.search_pain_points(ORG_ID, PainPointFilter(status=topic.status.UNDER_REVIEW), limit=10, offset=0)
    assert [r.topic_name for r in reviewed] == [topic.canonical_name]
    detail = await repo.get_pain_point(ORG_ID, "Login loops", MentionFilter())
    assert detail.score.trend is not None and detail.score.top_customers == ["Acme", "Globex"]


async def test_customer_health_and_at_risk_filter(env) -> None:
    store, repo = env
    await _arr(store, "acme", 200_000)
    await _arr(store, "globex", 50_000)
    await _arr(store, "initech", 90_000)
    await _gap(store, "acme", "SSO", "t1", churn_risk=True, competitor="Okta", urgency="high")
    await _pain(store, "globex", "Login loops", "p1", sentiment="Negative")
    await _pain(store, "globex", "Slow", "p2", sentiment="Negative")
    await _gap(store, "globex", "Export", "t2", sentiment="Neutral")
    await _gap(store, "initech", "Export", "t3", sentiment="Positive")

    everyone, _ = await repo.search_customers(ORG_ID, CustomerFilter(), limit=10, offset=0)
    health = {c.external_customer_id: c.health for c in everyone}
    assert (health["acme"].churn_risk_count, health["acme"].competitors, health["acme"].high_urgency_count) == (1, ["Okta"], 1)
    assert health["globex"].negative_share == pytest.approx(2 / 3, abs=1e-3)
    assert {c.external_customer_id: c.pain_point_count for c in everyone}["globex"] == 2

    at_risk, total = await repo.search_customers(ORG_ID, CustomerFilter(at_risk=True), limit=10, offset=0)
    assert [c.external_customer_id for c in at_risk] == ["acme", "globex"]
    assert total == 2


async def test_overview_emerging_at_risk_and_mixes(env) -> None:
    store, repo = env
    await _arr(store, "acme", 100_000)
    for i in range(3):
        await _gap(store, "acme", "Audit log", f"new-{i}", days_ago=2, intent="compliance_security")
    for i in range(3):
        await _gap(store, "acme", "Dark mode", f"old-{i}", days_ago=40)
    await _gap(store, "acme", "Dark mode", "recent", days_ago=3)
    await _gap(store, "acme", "SSO", "churn", churn_risk=True, sentiment="Negative")
    await _pain(store, "acme", "Login loops", "p1", sentiment="Negative")

    overview = await repo.get_overview(ORG_ID)

    assert overview.pain_point_count == 1
    assert [g.feature_name for g in overview.emerging_feature_gaps][0] == "Audit log"
    assert "Dark mode" not in [g.feature_name for g in overview.emerging_feature_gaps]
    assert [c.external_customer_id for c in overview.at_risk_customers] == ["acme"]
    assert overview.intent_mix["compliance_security"] == 3
    assert overview.tone_mix["Negative"] == 2
