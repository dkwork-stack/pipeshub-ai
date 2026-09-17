"""SQLAlchemy Core table definitions for the Customer Feature Intelligence MySQL store.

Every table carries ``org_id`` so this store is multi-tenant-ready even though
the rest of the pipeshub fork is not yet (see AGENTS.md). All queries in
``mysql_intelligence_store.py`` filter on it.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
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
    # Idempotent upsert key: re-processing the same source event never
    # duplicates a mention.
    UniqueConstraint(
        "org_id", "external_customer_id", "feature_name", "external_event_id",
        name="uq_mentions_org_customer_feature_event",
    ),
    Index("ix_mentions_org_feature", "org_id", "feature_name"),
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
    UniqueConstraint("org_id", "feature_name", name="uq_scores_org_feature"),
    Index("ix_scores_org_score", "org_id", "score"),
)
