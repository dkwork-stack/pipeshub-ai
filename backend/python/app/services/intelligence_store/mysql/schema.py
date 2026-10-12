"""SQLAlchemy Core table definitions for the Customer Feature Intelligence MySQL store.

Every table carries ``org_id`` so this store is multi-tenant-ready even though
the rest of the pipeshub fork is not yet (see AGENTS.md). All queries in
``mysql_intelligence_store.py`` filter on it.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

# SQLite only autoincrements INTEGER primary keys; MySQL keeps BIGINT. Lets the
# same table definitions back the in-memory SQLite engine used by unit tests.
PrimaryKeyInt = BigInteger().with_variant(Integer, "sqlite")


def _signal_attribute_columns() -> list[Column]:
    """Qualitative attributes + provenance shared by both mention tables.

    All nullable: ``migrations.add_missing_columns`` can only add nullable
    columns to tables that already hold rows.
    """
    return [
        Column("tone", String(32), nullable=True),
        Column("urgency", String(16), nullable=True),
        Column("intent", String(32), nullable=True),
        Column("speaker_role", String(16), nullable=True),
        Column("product_area", String(191), nullable=True),
        Column("business_impact", Text, nullable=True),
        Column("workaround", Text, nullable=True),
        Column("competitor", String(191), nullable=True),
        Column("churn_risk", Boolean, nullable=True),
        Column("topic_id", BigInteger, nullable=True),
        Column("source_record_id", String(191), nullable=True),
        Column("extraction_model", String(191), nullable=True),
        Column("prompt_version", String(32), nullable=True),
    ]

customers = Table(
    "customers",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("external_customer_id", String(255), nullable=False),
    Column("customer_name", String(512), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("org_id", "external_customer_id", name="uq_customers_org_external"),
    Index("ix_customers_org_name", "org_id", "customer_name"),
)

revenue_snapshots = Table(
    "revenue_snapshots",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("external_customer_id", String(255), nullable=False),
    Column("source_connector", String(64), nullable=False),
    Column("mrr", Float, nullable=False, default=0.0),
    Column("arr", Float, nullable=False, default=0.0),
    Column("seats_used", Integer, nullable=True),
    Column("seats_licensed", Integer, nullable=True),
    Column("consumed_features", JSON, nullable=True),
    Column("renewal_date", DateTime, nullable=True),
    Column("snapshot_at", DateTime, nullable=False),
    Index("ix_revenue_org_customer_snapshot", "org_id", "external_customer_id", "snapshot_at"),
)

feature_gaps = Table(
    "feature_gaps",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("feature_name", String(512), nullable=False),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("org_id", "feature_name", name="uq_feature_gaps_org_name"),
)

feature_gap_mentions = Table(
    "feature_gap_mentions",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    # Kept short (vs. customers.customer_name/feature_gaps.feature_name) so the
    # 4-column unique key below stays under MySQL's 3072-byte utf8mb4 index
    # limit: (128+191+191+191)*4 bytes ~= 2804 < 3072.
    Column("external_customer_id", String(191), nullable=False),
    Column("feature_name", String(191), nullable=False),
    Column("description", Text, nullable=True),
    Column("confidence", Float, nullable=False, default=0.5),
    Column("excerpt", Text, nullable=True),
    Column("source_connector", String(64), nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("external_event_id", String(191), nullable=False),
    Column("citation_url", String(2048), nullable=True),
    Column("occurred_at", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("sentiment", String(32), nullable=True),
    *_signal_attribute_columns(),
    # Idempotent upsert key: re-processing the same source event never
    # duplicates a mention.
    UniqueConstraint(
        "org_id", "external_customer_id", "feature_name", "external_event_id",
        name="uq_mentions_org_customer_feature_event",
    ),
    Index("ix_mentions_org_feature", "org_id", "feature_name"),
    Index("ix_mentions_org_customer", "org_id", "external_customer_id"),
    Index("ix_mentions_org_source_record", "org_id", "source_record_id"),
    Index("ix_mentions_org_occurred", "org_id", "occurred_at"),
)


feature_gap_scores = Table(
    "feature_gap_scores",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("feature_name", String(512), nullable=False),
    Column("total_arr_at_stake", Float, nullable=False, default=0.0),
    Column("total_mrr_at_stake", Float, nullable=False, default=0.0),
    Column("customer_count", Integer, nullable=False, default=0),
    Column("mention_count", Integer, nullable=False, default=0),
    Column("score", Float, nullable=False, default=0.0),
    Column("top_customers", JSON, nullable=True),
    Column("updated_at", DateTime, nullable=False),
    # TopicTrend roll-up (first/last seen, 30-day windows, tone/urgency mix).
    Column("trend", JSON, nullable=True),
    UniqueConstraint("org_id", "feature_name", name="uq_scores_org_feature"),
    Index("ix_scores_org_score", "org_id", "score"),
)

# Org taxonomy for pain points and feature gaps. New table only — create_all
# never ALTERs existing tables.
intelligence_topics = Table(
    "intelligence_topics",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("kind", String(32), nullable=False),  # pain_point | feature_gap
    Column("canonical_name", String(512), nullable=False),
    Column("aliases", JSON, nullable=True),
    Column("guidance", Text, nullable=True),
    Column("description", Text, nullable=True),
    Column("status", String(32), nullable=True),
    Column("merged_into_id", BigInteger, nullable=True),
    Column("updated_by", String(255), nullable=True),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("org_id", "kind", "canonical_name", name="uq_topics_org_kind_name"),
    Index("ix_topics_org_kind", "org_id", "kind"),
)

pain_point_mentions = Table(
    "pain_point_mentions",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("external_customer_id", String(191), nullable=False),
    Column("topic_name", String(191), nullable=False),
    Column("summary", Text, nullable=True),
    Column("sentiment", String(32), nullable=False, default="Neutral"),
    Column("confidence", Float, nullable=False, default=0.5),
    Column("excerpt", Text, nullable=True),
    Column("source_connector", String(64), nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("external_event_id", String(191), nullable=False),
    Column("citation_url", String(2048), nullable=True),
    Column("occurred_at", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False),
    *_signal_attribute_columns(),
    UniqueConstraint(
        "org_id", "external_customer_id", "topic_name", "external_event_id",
        name="uq_pain_mentions_org_customer_topic_event",
    ),
    Index("ix_pain_mentions_org_topic", "org_id", "topic_name"),
    Index("ix_pain_mentions_org_topic_confidence", "org_id", "topic_name", "confidence"),
    Index("ix_pain_mentions_org_customer", "org_id", "external_customer_id"),
    Index("ix_pain_mentions_org_source_record", "org_id", "source_record_id"),
)

# Cached topic vectors for semantic matching, keyed by embedding model so a
# model change re-embeds lazily instead of comparing incompatible spaces.
intelligence_topic_embeddings = Table(
    "intelligence_topic_embeddings",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("topic_id", BigInteger, nullable=False),
    Column("model", String(191), nullable=False),
    Column("text_hash", String(64), nullable=False),
    Column("vector", JSON, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("org_id", "topic_id", "model", name="uq_topic_embeddings_org_topic_model"),
    Index("ix_topic_embeddings_org_model", "org_id", "model"),
)

# Append-only trail of privileged actions: topic edits/merges, erasure,
# retention purges.
intelligence_audit_log = Table(
    "intelligence_audit_log",
    metadata,
    Column("id", PrimaryKeyInt, primary_key=True, autoincrement=True),
    Column("org_id", String(128), nullable=False),
    Column("actor", String(255), nullable=True),
    Column("action", String(64), nullable=False),
    Column("target_type", String(32), nullable=False),
    Column("target_id", String(255), nullable=False),
    Column("details", JSON, nullable=True),
    Column("created_at", DateTime, nullable=False),
    Index("ix_audit_org_created", "org_id", "created_at"),
)
