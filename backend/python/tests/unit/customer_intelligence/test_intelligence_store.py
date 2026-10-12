"""MySQLIntelligenceStore against in-memory SQLite.

Upserts are built per dialect (``sql.upsert``), so the production store runs
here unchanged. Pins down: idempotent mention writes with attributes,
set-based score + trend recompute, merges, erasure, retention, audit and the
additive schema migrator.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
)

from app.models.intelligence import (
    AuditEntry,
    CustomerRevenueSnapshot,
    FeatureGapMentionRecord,
    IntelligenceTopic,
    PainPointMentionRecord,
    SignalSourceType,
    TopicGuidanceUpdate,
    TopicKind,
    TopicStatus,
)
from app.services.intelligence_store.mysql.mysql_intelligence_store import (
    MySQLIntelligenceStore,
)
from app.services.intelligence_store.mysql.schema import (
    feature_gap_mentions,
    feature_gap_scores,
)
from app.services.intelligence_store.mysql.sql import ensure_schema, utcnow

ORG = "org-a"
OTHER = "org-b"
LOG = logging.getLogger("test-intelligence-store")


@pytest.fixture
async def store() -> MySQLIntelligenceStore:
    s = MySQLIntelligenceStore(logger=LOG, dsn="sqlite+aiosqlite://")
    assert await s.connect()
    yield s
    await s.close()


def _gap(
    customer: str,
    feature: str,
    event: str,
    *,
    org: str = ORG,
    days_ago: int = 1,
    confidence: float = 0.9,
    **attrs,
) -> FeatureGapMentionRecord:
    return FeatureGapMentionRecord(
        org_id=org,
        external_customer_id=customer,
        feature_name=feature,
        description=f"{customer} wants {feature}",
        confidence=confidence,
        excerpt=f"we need {feature}",
        source_connector="zammad",
        source_type=SignalSourceType.SUPPORT_TICKET,
        external_event_id=event,
        occurred_at=utcnow() - timedelta(days=days_ago),
        **attrs,
    )


async def _revenue(store: MySQLIntelligenceStore, customer: str, arr: float) -> None:
    await store.upsert_revenue_snapshot(
        CustomerRevenueSnapshot(
            org_id=ORG, source_connector="file_upload", external_customer_id=customer,
            customer_name=customer.title(), arr=arr, mrr=arr / 12,
        )
    )


async def _scores(store: MySQLIntelligenceStore) -> dict[str, dict]:
    async with store.engine.begin() as conn:
        rows = (await conn.execute(select(feature_gap_scores).where(feature_gap_scores.c.org_id == ORG))).mappings()
        return {r["feature_name"]: dict(r) for r in rows}


async def test_mention_upsert_is_idempotent_and_keeps_attributes(store: MySQLIntelligenceStore) -> None:
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "t1", confidence=0.6, tone="frustrated"))
    await store.upsert_feature_gap_mention(
        _gap("acme", "SSO", "t1", confidence=0.9, tone="angry", urgency="critical",
             churn_risk=True, competitor="Zendesk", source_record_id="rec-1", prompt_version="v2")
    )
    async with store.engine.begin() as conn:
        rows = (await conn.execute(select(feature_gap_mentions))).mappings().all()
    assert len(rows) == 1
    row = rows[0]
    assert row["confidence"] == 0.9
    assert (row["tone"], row["urgency"], row["competitor"]) == ("angry", "critical", "Zendesk")
    assert row["churn_risk"] is True or row["churn_risk"] == 1
    assert (row["source_record_id"], row["prompt_version"]) == ("rec-1", "v2")


async def test_long_feature_names_are_clamped_to_the_mention_column(store: MySQLIntelligenceStore) -> None:
    await store.upsert_feature_gap_mention(_gap("acme", "x" * 400, "t1"))
    assert len(next(iter(await _scores(store)))) == 191


async def test_recompute_weights_revenue_breadth_and_builds_trend(store: MySQLIntelligenceStore) -> None:
    await _revenue(store, "acme", 120_000)
    await _revenue(store, "globex", 30_000)
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "t1", days_ago=2, sentiment="Negative", urgency="high"), recompute=False)
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "t2", days_ago=40, competitor="Okta"), recompute=False)
    await store.upsert_feature_gap_mention(_gap("globex", "SSO", "t3", days_ago=5, churn_risk=True), recompute=False)
    # Below the score threshold: persisted, but not counted.
    await store.upsert_feature_gap_mention(_gap("initech", "SSO", "t4", confidence=0.2), recompute=False)
    await store.recompute_feature_gap_scores(ORG, ["SSO"])

    score = (await _scores(store))["SSO"]
    assert score["customer_count"] == 2
    assert score["mention_count"] == 3
    assert score["total_arr_at_stake"] == pytest.approx(150_000)
    assert score["top_customers"] == ["Acme", "Globex"]
    trend = score["trend"]
    assert (trend["mentions_last_30d"], trend["mentions_prev_30d"]) == (2, 1)
    assert trend["negative_share"] == pytest.approx(1 / 3, abs=1e-3)
    assert (trend["high_urgency_count"], trend["churn_risk_count"]) == (1, 1)
    assert trend["competitors"] == ["Okta"]


async def test_recompute_is_org_scoped(store: MySQLIntelligenceStore) -> None:
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "t1"))
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "t2", org=OTHER))
    assert (await _scores(store))["SSO"]["mention_count"] == 1


async def test_merge_moves_mentions_and_collapses_duplicates(store: MySQLIntelligenceStore) -> None:
    src = await store.upsert_topic(IntelligenceTopic(org_id=ORG, kind=TopicKind.FEATURE_GAP, canonical_name="SAML login"))
    dst = await store.upsert_topic(IntelligenceTopic(org_id=ORG, kind=TopicKind.FEATURE_GAP, canonical_name="SSO"))
    await store.upsert_feature_gap_mention(_gap("acme", "SAML login", "t1", confidence=0.95))
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "t1", confidence=0.7))
    await store.upsert_feature_gap_mention(_gap("globex", "SAML login", "t2"))

    merged = await store.merge_topics(ORG, src.id, dst.id)

    assert merged is not None and "SAML login" in merged.aliases
    async with store.engine.begin() as conn:
        rows = (await conn.execute(select(feature_gap_mentions).order_by(feature_gap_mentions.c.external_event_id))).mappings().all()
    assert [(r["feature_name"], r["external_event_id"], r["confidence"]) for r in rows] == [
        ("SSO", "t1", 0.95),
        ("SSO", "t2", 0.9),
    ]
    assert all(r["topic_id"] == dst.id for r in rows)
    assert (await _scores(store))["SSO"]["customer_count"] == 2
    assert [t.canonical_name for t in await store.list_topics(ORG, TopicKind.FEATURE_GAP)] == ["SSO"]


async def test_topic_upsert_never_overwrites_curated_fields(store: MySQLIntelligenceStore) -> None:
    topic = await store.upsert_topic(IntelligenceTopic(org_id=ORG, kind=TopicKind.FEATURE_GAP, canonical_name="SSO"))
    await store.update_topic_guidance(
        ORG, topic.id, TopicGuidanceUpdate(guidance="exclude: MFA", status=TopicStatus.PLANNED, updated_by="pm@x")
    )
    again = await store.upsert_topic(IntelligenceTopic(org_id=ORG, kind=TopicKind.FEATURE_GAP, canonical_name="SSO"))
    assert (again.guidance, again.status, again.updated_by) == ("exclude: MFA", TopicStatus.PLANNED, "pm@x")


async def test_add_alias_is_case_insensitive_noop_for_known_names(store: MySQLIntelligenceStore) -> None:
    topic = await store.upsert_topic(IntelligenceTopic(org_id=ORG, kind=TopicKind.FEATURE_GAP, canonical_name="SSO"))
    await store.add_topic_alias(ORG, topic.id, "sso")
    await store.add_topic_alias(ORG, topic.id, "Single sign-on")
    await store.add_topic_alias(ORG, topic.id, "single SIGN-ON")
    assert (await store.get_topic(ORG, topic.id)).aliases == ["Single sign-on"]


async def test_embedding_cache_round_trip(store: MySQLIntelligenceStore) -> None:
    await store.upsert_topic_embedding(ORG, 7, "m1", "h1", [0.1, 0.2])
    await store.upsert_topic_embedding(ORG, 7, "m1", "h2", [0.3, 0.4])
    await store.upsert_topic_embedding(ORG, 7, "m2", "h1", [9.0])
    assert await store.get_topic_embeddings(ORG, "m1") == {7: ("h2", [0.3, 0.4])}
    assert await store.get_topic_embeddings(OTHER, "m1") == {}


async def test_erase_customer_removes_everything_and_rescores(store: MySQLIntelligenceStore) -> None:
    await _revenue(store, "acme", 100_000)
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "t1"))
    await store.upsert_feature_gap_mention(_gap("globex", "SSO", "t2"))
    await store.upsert_pain_point_mention(
        PainPointMentionRecord(
            org_id=ORG, external_customer_id="acme", topic_name="Login pain", summary="Login pain",
            confidence=0.8, excerpt="x", source_connector="zammad",
            source_type=SignalSourceType.SUPPORT_TICKET, external_event_id="t1", occurred_at=utcnow(),
        )
    )

    result = await store.erase_customer(ORG, "acme")

    assert (result.customers, result.feature_gap_mentions, result.pain_point_mentions, result.revenue_snapshots) == (1, 1, 1, 1)
    score = (await _scores(store))["SSO"]
    assert (score["customer_count"], score["total_arr_at_stake"]) == (1, 0.0)
    assert ("acme", "Acme") not in await store.list_customer_names(ORG)


async def test_erase_source_record_matches_new_and_legacy_rows(store: MySQLIntelligenceStore) -> None:
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "evt-1", source_record_id="rec-9"))
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "rec-9:row:3"))  # pre-provenance row
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "rec-90"))  # different record, same prefix
    result = await store.erase_source_record(ORG, "rec-9")
    assert result.feature_gap_mentions == 2
    assert (await _scores(store))["SSO"]["mention_count"] == 1


async def test_purge_before_cutoff(store: MySQLIntelligenceStore) -> None:
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "old", days_ago=400))
    await store.upsert_feature_gap_mention(_gap("acme", "SSO", "new", days_ago=1))
    result = await store.purge_mentions_before(ORG, utcnow() - timedelta(days=365))
    assert result.feature_gap_mentions == 1
    assert (await _scores(store))["SSO"]["mention_count"] == 1


async def test_audit_log_is_org_scoped_newest_first(store: MySQLIntelligenceStore) -> None:
    for i in range(3):
        await store.record_audit(
            AuditEntry(org_id=ORG, actor="pm@x", action=f"a{i}", target_type="topic", target_id=str(i),
                       created_at=datetime(2026, 1, 1 + i))
        )
    await store.record_audit(AuditEntry(org_id=OTHER, action="x", target_type="topic", target_id="9"))
    entries, total = await store.list_audit(ORG, limit=2)
    assert total == 3
    assert [e.action for e in entries] == ["a2", "a1"]


def test_ensure_schema_adds_missing_nullable_columns_and_indexes() -> None:
    engine = create_engine("sqlite://")
    old = MetaData()
    Table("widgets", old, Column("id", Integer, primary_key=True), Column("name", String(10)))
    old.create_all(engine)

    new = MetaData()
    widgets = Table(
        "widgets", new,
        Column("id", Integer, primary_key=True),
        Column("name", String(10)),
        Column("colour", String(10), nullable=True),
        Column("weight", Integer, nullable=False),
    )
    from sqlalchemy import Index
    Index("ix_widgets_colour", widgets.c.colour)

    with engine.begin() as conn:
        applied = ensure_schema(conn, new, LOG)
    with engine.begin() as conn:
        assert ensure_schema(conn, new, LOG) == []

    cols = {c["name"] for c in inspect(engine).get_columns("widgets")}
    assert "colour" in cols and "weight" not in cols
    assert applied == ["widgets.colour", "index ix_widgets_colour"]
