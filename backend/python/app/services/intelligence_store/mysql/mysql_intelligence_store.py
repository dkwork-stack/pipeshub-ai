"""MySQL implementation of IIntelligenceStore, via SQLAlchemy async core + aiomysql.

Uses Core (not the ORM) so the table definitions in ``schema.py`` stay the
single source of truth and queries stay explicit/auditable — this store is a
thin, replaceable adapter, not a place for business logic (that lives in
``app/modules/customer_intelligence``). Upserts go through ``sql.upsert`` so
the same class also runs on SQLite in unit tests.
"""
from __future__ import annotations

import asyncio
import os
import threading
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.models.intelligence import (
    AuditEntry,
    CustomerRevenueSnapshot,
    ErasureResult,
    FeatureGapMentionRecord,
    IntelligenceTopic,
    PainPointMentionRecord,
    TopicGuidanceUpdate,
    TopicKind,
)
from app.modules.customer_intelligence.scoring import compute_feature_gap_score
from app.services.intelligence_store.interface.intelligence_store import (
    IIntelligenceStore,
)
from app.services.intelligence_store.mysql.aggregates import chunked, topic_trends
from app.services.intelligence_store.mysql.rows import (
    attribute_values,
    clamp_name,
    provenance_values,
    topic_from_row,
)
from app.services.intelligence_store.mysql.schema import (
    customers,
    feature_gap_mentions,
    feature_gap_scores,
    feature_gaps,
    intelligence_audit_log,
    intelligence_topic_embeddings,
    intelligence_topics,
    metadata,
    pain_point_mentions,
    revenue_snapshots,
)
from app.services.intelligence_store.mysql.sql import (
    ensure_schema,
    greatest,
    upsert,
    utcnow,
)

if TYPE_CHECKING:
    from datetime import datetime
    from logging import Logger

# Mentions below this confidence still persist and remain visible in the UI,
# but they do not contribute to revenue-weighted feature-gap scores.
_SCORE_MIN_CONFIDENCE = float(os.getenv("INTELLIGENCE_SCORE_MIN_CONFIDENCE", "0.5"))
_TOP_CUSTOMERS = 5


def _kind_value(kind: TopicKind | str) -> str:
    return kind.value if isinstance(kind, TopicKind) else kind


class MySQLIntelligenceStore(IIntelligenceStore):
    def __init__(
        self,
        logger: Logger,
        dsn: str,
        pool_size: int = 10,
        max_overflow: int = 10,
        connect_args: Optional[dict[str, Any]] = None,
    ) -> None:
        self.logger = logger
        self.dsn = dsn
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.connect_args = connect_args or {}
        # aiomysql / SQLAlchemy async pools bind to the loop that created them.
        # Indexing creates the store on the uvicorn loop, then runs ingestion on
        # the consumer worker-thread loop — one shared engine raises
        # "Future attached to a different loop". Mirror QdrantService: one
        # engine per running loop, created lazily after connect().
        self._engines: dict[asyncio.AbstractEventLoop, AsyncEngine] = {}
        self._engines_lock = threading.Lock()
        self._connected = False

    def _create_engine(self) -> AsyncEngine:
        if self.dsn.startswith("sqlite"):
            return create_async_engine(self.dsn, connect_args=self.connect_args)
        return create_async_engine(
            self.dsn,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_pre_ping=True,
            connect_args=self.connect_args,
        )

    def _engine_for_current_loop(self) -> AsyncEngine:
        if not self._connected:
            raise RuntimeError("MySQLIntelligenceStore.connect() must be called before use")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "MySQLIntelligenceStore requires a running event loop"
            ) from exc
        with self._engines_lock:
            engine = self._engines.get(loop)
            if engine is None:
                engine = self._create_engine()
                self._engines[loop] = engine
            return engine

    async def connect(self) -> bool:
        try:
            self._connected = True
            engine = self._engine_for_current_loop()
            async with engine.begin() as conn:
                await conn.run_sync(ensure_schema, metadata, self.logger)
            self.logger.info("✅ MySQLIntelligenceStore connected and schema ensured")
            return True
        except Exception as e:
            self._connected = False
            self.logger.error(f"❌ MySQLIntelligenceStore failed to connect: {e}")
            return False

    async def close(self) -> None:
        with self._engines_lock:
            engines = list(self._engines.values())
            self._engines.clear()
            self._connected = False
        for engine in engines:
            try:
                await engine.dispose()
            except Exception as exc:
                self.logger.debug("Error disposing MySQL engine: %s", exc)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine_for_current_loop()

    # ------------------------------------------------------------- customers

    async def upsert_customer(
        self, org_id: str, external_customer_id: str, customer_name: str
    ) -> None:
        async with self.engine.begin() as conn:
            await self._upsert_customer_conn(conn, org_id, external_customer_id, customer_name)

    @staticmethod
    async def _upsert_customer_conn(
        conn: AsyncConnection, org_id: str, external_customer_id: str, customer_name: str
    ) -> None:
        now = utcnow()
        await conn.execute(
            upsert(
                conn.dialect.name,
                customers,
                {
                    "org_id": org_id,
                    "external_customer_id": external_customer_id,
                    "customer_name": customer_name,
                    "created_at": now,
                    "updated_at": now,
                },
                conflict_cols=["org_id", "external_customer_id"],
                update=lambda new: {"customer_name": new.customer_name, "updated_at": now},
            )
        )

    async def upsert_revenue_snapshot(self, snapshot: CustomerRevenueSnapshot) -> None:
        async with self.engine.begin() as conn:
            await self._upsert_customer_conn(
                conn, snapshot.org_id, snapshot.external_customer_id, snapshot.customer_name
            )
            await conn.execute(
                revenue_snapshots.insert().values(
                    org_id=snapshot.org_id,
                    external_customer_id=snapshot.external_customer_id,
                    source_connector=snapshot.source_connector,
                    mrr=snapshot.mrr,
                    arr=snapshot.arr,
                    seats_used=snapshot.seats_used,
                    seats_licensed=snapshot.seats_licensed,
                    consumed_features=snapshot.consumed_features,
                    renewal_date=snapshot.renewal_date,
                    snapshot_at=snapshot.snapshot_at,
                )
            )

    async def list_customer_names(self, org_id: str, limit: int = 500) -> list[tuple[str, str]]:
        async with self.engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(customers.c.external_customer_id, customers.c.customer_name)
                    .where(customers.c.org_id == org_id)
                    .order_by(customers.c.customer_name)
                    .limit(limit)
                )
            ).all()
        return [(r[0], r[1]) for r in rows]

    async def list_org_ids(self) -> list[str]:
        async with self.engine.begin() as conn:
            rows = (await conn.execute(select(customers.c.org_id).distinct())).all()
        return [r[0] for r in rows]

    # -------------------------------------------------------------- mentions

    async def upsert_feature_gap_mention(
        self, mention: FeatureGapMentionRecord, *, recompute: bool = True
    ) -> None:
        now = utcnow()
        feature_name = clamp_name(mention.feature_name)
        async with self.engine.begin() as conn:
            dialect = conn.dialect.name
            await conn.execute(
                upsert(
                    dialect,
                    feature_gaps,
                    {"org_id": mention.org_id, "feature_name": feature_name, "created_at": now},
                    conflict_cols=["org_id", "feature_name"],
                    update=lambda new: {"feature_name": new.feature_name},
                )
            )
            await conn.execute(
                upsert(
                    dialect,
                    feature_gap_mentions,
                    {
                        "org_id": mention.org_id,
                        "external_customer_id": mention.external_customer_id,
                        "feature_name": feature_name,
                        "description": mention.description,
                        "confidence": mention.confidence,
                        "excerpt": mention.excerpt,
                        "source_connector": mention.source_connector,
                        "source_type": mention.source_type.value,
                        "external_event_id": mention.external_event_id,
                        "citation_url": mention.citation_url,
                        "occurred_at": mention.occurred_at,
                        "created_at": now,
                        **attribute_values(mention),
                        **provenance_values(mention),
                    },
                    conflict_cols=["org_id", "external_customer_id", "feature_name", "external_event_id"],
                    # Re-processing the same source event refreshes attributes
                    # and keeps the higher confidence.
                    update=lambda new: {
                        "description": new.description,
                        "confidence": greatest(dialect, feature_gap_mentions.c.confidence, new.confidence),
                        "excerpt": new.excerpt,
                        **{col: getattr(new, col) for col in (*attribute_values(mention), *provenance_values(mention))},
                    },
                )
            )

        if recompute:
            await self.recompute_feature_gap_scores(mention.org_id, [feature_name])

    async def upsert_pain_point_mention(self, mention: PainPointMentionRecord) -> None:
        now = utcnow()
        topic_name = clamp_name(mention.topic_name)
        async with self.engine.begin() as conn:
            dialect = conn.dialect.name
            if mention.topic_id is None:
                topic = await self._upsert_topic_conn(
                    conn,
                    IntelligenceTopic(org_id=mention.org_id, kind=TopicKind.PAIN_POINT, canonical_name=topic_name),
                )
                mention = mention.model_copy(update={"topic_id": topic.id})
            await conn.execute(
                upsert(
                    dialect,
                    pain_point_mentions,
                    {
                        "org_id": mention.org_id,
                        "external_customer_id": mention.external_customer_id,
                        "topic_name": topic_name,
                        "summary": mention.summary,
                        "confidence": mention.confidence,
                        "excerpt": mention.excerpt,
                        "source_connector": mention.source_connector,
                        "source_type": mention.source_type.value,
                        "external_event_id": mention.external_event_id,
                        "citation_url": mention.citation_url,
                        "occurred_at": mention.occurred_at,
                        "created_at": now,
                        **attribute_values(mention),
                        **provenance_values(mention),
                    },
                    conflict_cols=["org_id", "external_customer_id", "topic_name", "external_event_id"],
                    update=lambda new: {
                        "summary": new.summary,
                        "confidence": greatest(dialect, pain_point_mentions.c.confidence, new.confidence),
                        "excerpt": new.excerpt,
                        **{col: getattr(new, col) for col in (*attribute_values(mention), *provenance_values(mention))},
                    },
                )
            )

    # ---------------------------------------------------------------- topics

    async def list_topics(
        self, org_id: str, kind: Optional[TopicKind] = None, *, include_merged: bool = False
    ) -> list[IntelligenceTopic]:
        conds = [intelligence_topics.c.org_id == org_id]
        if kind is not None:
            conds.append(intelligence_topics.c.kind == kind.value)
        if not include_merged:
            conds.append(intelligence_topics.c.merged_into_id.is_(None))
        async with self.engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(intelligence_topics)
                    .where(*conds)
                    .order_by(intelligence_topics.c.canonical_name)
                )
            ).mappings().all()
        return [topic_from_row(r) for r in rows]

    async def get_topic(self, org_id: str, topic_id: int) -> Optional[IntelligenceTopic]:
        async with self.engine.begin() as conn:
            return await self._get_topic_conn(conn, org_id, topic_id)

    @staticmethod
    async def _get_topic_conn(
        conn: AsyncConnection, org_id: str, topic_id: int
    ) -> Optional[IntelligenceTopic]:
        row = (
            await conn.execute(
                select(intelligence_topics).where(
                    intelligence_topics.c.org_id == org_id,
                    intelligence_topics.c.id == topic_id,
                )
            )
        ).mappings().first()
        return topic_from_row(row) if row else None

    async def upsert_topic(self, topic: IntelligenceTopic) -> IntelligenceTopic:
        async with self.engine.begin() as conn:
            return await self._upsert_topic_conn(conn, topic)

    async def _upsert_topic_conn(self, conn: AsyncConnection, topic: IntelligenceTopic) -> IntelligenceTopic:
        now = utcnow()
        name = clamp_name(topic.canonical_name)
        await conn.execute(
            upsert(
                conn.dialect.name,
                intelligence_topics,
                {
                    "org_id": topic.org_id,
                    "kind": _kind_value(topic.kind),
                    "canonical_name": name,
                    "aliases": topic.aliases or [],
                    "guidance": topic.guidance,
                    "description": topic.description,
                    "status": topic.status.value,
                    "merged_into_id": topic.merged_into_id,
                    "updated_by": topic.updated_by,
                    "created_at": now,
                    "updated_at": now,
                },
                conflict_cols=["org_id", "kind", "canonical_name"],
                # Never clobber PM-curated guidance/description/status with an
                # automatic re-upsert of the same name.
                update=lambda new: {
                    "guidance": func.coalesce(intelligence_topics.c.guidance, new.guidance),
                    "description": func.coalesce(intelligence_topics.c.description, new.description),
                    "updated_by": func.coalesce(new.updated_by, intelligence_topics.c.updated_by),
                    "updated_at": now,
                },
            )
        )
        row = (
            await conn.execute(
                select(intelligence_topics).where(
                    intelligence_topics.c.org_id == topic.org_id,
                    intelligence_topics.c.kind == _kind_value(topic.kind),
                    intelligence_topics.c.canonical_name == name,
                )
            )
        ).mappings().first()
        return topic_from_row(row)

    async def add_topic_alias(self, org_id: str, topic_id: int, alias: str) -> None:
        alias = clamp_name(alias)
        async with self.engine.begin() as conn:
            topic = await self._get_topic_conn(conn, org_id, topic_id)
            if topic is None or not alias:
                return
            known = {topic.canonical_name.lower(), *(a.lower() for a in topic.aliases)}
            if alias.lower() in known:
                return
            await conn.execute(
                update(intelligence_topics)
                .where(intelligence_topics.c.org_id == org_id, intelligence_topics.c.id == topic_id)
                .values(aliases=[*topic.aliases, alias], updated_at=utcnow())
            )

    async def update_topic_guidance(
        self, org_id: str, topic_id: int, update_payload: TopicGuidanceUpdate
    ) -> Optional[IntelligenceTopic]:
        values: dict = {"updated_at": utcnow()}
        if update_payload.guidance is not None:
            values["guidance"] = update_payload.guidance
        if update_payload.aliases is not None:
            values["aliases"] = update_payload.aliases
        if update_payload.canonical_name is not None:
            values["canonical_name"] = clamp_name(update_payload.canonical_name)
        if update_payload.status is not None:
            values["status"] = update_payload.status.value
        if update_payload.updated_by is not None:
            values["updated_by"] = update_payload.updated_by
        if len(values) == 1:
            return await self.get_topic(org_id, topic_id)

        async with self.engine.begin() as conn:
            result = await conn.execute(
                update(intelligence_topics)
                .where(
                    intelligence_topics.c.org_id == org_id,
                    intelligence_topics.c.id == topic_id,
                )
                .values(**values)
            )
            if result.rowcount == 0:
                return None
            return await self._get_topic_conn(conn, org_id, topic_id)

    async def merge_topics(
        self, org_id: str, source_id: int, target_id: int
    ) -> Optional[IntelligenceTopic]:
        if source_id == target_id:
            return await self.get_topic(org_id, target_id)

        async with self.engine.begin() as conn:
            source = await self._get_topic_conn(conn, org_id, source_id)
            target = await self._get_topic_conn(conn, org_id, target_id)
            if not source or not target:
                return None
            if source.kind != target.kind:
                raise ValueError("Cannot merge topics of different kinds")

            if source.kind == TopicKind.FEATURE_GAP:
                await conn.execute(
                    upsert(
                        conn.dialect.name,
                        feature_gaps,
                        {"org_id": org_id, "feature_name": target.canonical_name, "created_at": utcnow()},
                        conflict_cols=["org_id", "feature_name"],
                        update=lambda new: {"feature_name": new.feature_name},
                    )
                )
                await self._rewrite_mentions(
                    conn, feature_gap_mentions, "feature_name", org_id, source.canonical_name, target
                )
            else:
                await self._rewrite_mentions(
                    conn, pain_point_mentions, "topic_name", org_id, source.canonical_name, target
                )

            aliases = list(target.aliases)
            for alias in (source.canonical_name, *source.aliases):
                if alias not in aliases and alias != target.canonical_name:
                    aliases.append(alias)
            now = utcnow()
            await conn.execute(
                update(intelligence_topics)
                .where(intelligence_topics.c.id == target_id)
                .values(aliases=aliases, updated_at=now)
            )
            await conn.execute(
                update(intelligence_topics)
                .where(intelligence_topics.c.id == source_id)
                .values(merged_into_id=target_id, updated_at=now)
            )

        if source.kind == TopicKind.FEATURE_GAP:
            await self.recompute_feature_gap_scores(org_id, [source.canonical_name, target.canonical_name])

        return await self.get_topic(org_id, target_id)

    @staticmethod
    async def _rewrite_mentions(
        conn: AsyncConnection,
        table: Any,  # noqa: ANN401 - one of the two mention tables
        name_column: str,
        org_id: str,
        source_name: str,
        target: IntelligenceTopic,
    ) -> None:
        """Move mentions onto ``target``; where the same customer+event already
        cites the target, keep one row with the higher confidence."""
        dialect = conn.dialect.name
        rows = (
            await conn.execute(
                select(table).where(table.c.org_id == org_id, table.c[name_column] == source_name)
            )
        ).mappings().all()
        conflict_cols = ["org_id", "external_customer_id", name_column, "external_event_id"]
        for row in rows:
            values = {k: v for k, v in row.items() if k != "id"}
            values[name_column] = target.canonical_name
            values["topic_id"] = target.id
            await conn.execute(
                upsert(
                    dialect,
                    table,
                    values,
                    conflict_cols=conflict_cols,
                    update=lambda new: {
                        "confidence": greatest(dialect, table.c.confidence, new.confidence),
                        "topic_id": new.topic_id,
                    },
                )
            )
            await conn.execute(delete(table).where(table.c.id == row["id"]))

    # ------------------------------------------------------- topic embeddings

    async def get_topic_embeddings(
        self, org_id: str, model: str
    ) -> dict[int, tuple[str, list[float]]]:
        async with self.engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        intelligence_topic_embeddings.c.topic_id,
                        intelligence_topic_embeddings.c.text_hash,
                        intelligence_topic_embeddings.c.vector,
                    ).where(
                        intelligence_topic_embeddings.c.org_id == org_id,
                        intelligence_topic_embeddings.c.model == model,
                    )
                )
            ).all()
        return {int(r[0]): (r[1], list(r[2])) for r in rows}

    async def upsert_topic_embedding(
        self, org_id: str, topic_id: int, model: str, text_hash: str, vector: list[float]
    ) -> None:
        now = utcnow()
        async with self.engine.begin() as conn:
            await conn.execute(
                upsert(
                    conn.dialect.name,
                    intelligence_topic_embeddings,
                    {
                        "org_id": org_id,
                        "topic_id": topic_id,
                        "model": model,
                        "text_hash": text_hash,
                        "vector": vector,
                        "updated_at": now,
                    },
                    conflict_cols=["org_id", "topic_id", "model"],
                    update=lambda new: {"text_hash": new.text_hash, "vector": new.vector, "updated_at": now},
                )
            )

    # ---------------------------------------------------------------- scores

    async def recompute_feature_gap_scores(
        self, org_id: str, feature_names: Optional[list[str]] = None
    ) -> None:
        """Set-based: a handful of grouped queries per 500 features, no per-customer round trips."""
        async with self.engine.begin() as conn:
            if feature_names is None:
                rows = (
                    await conn.execute(
                        select(feature_gaps.c.feature_name).where(feature_gaps.c.org_id == org_id)
                    )
                ).all()
                feature_names = [r[0] for r in rows]
            names = sorted({clamp_name(n) for n in feature_names if n})
            if not names:
                return

            latest = self._latest_revenue_subquery(org_id)
            now = utcnow()
            dialect = conn.dialect.name

            for chunk in chunked(names):
                per_customer = await conn.execute(
                    select(
                        feature_gap_mentions.c.feature_name,
                        feature_gap_mentions.c.external_customer_id,
                        func.count().label("mentions"),
                        func.coalesce(latest.c.arr, 0.0).label("arr"),
                        func.coalesce(latest.c.mrr, 0.0).label("mrr"),
                        func.coalesce(customers.c.customer_name, feature_gap_mentions.c.external_customer_id).label("name"),
                    )
                    .select_from(
                        feature_gap_mentions.outerjoin(
                            latest, latest.c.external_customer_id == feature_gap_mentions.c.external_customer_id
                        ).outerjoin(
                            customers,
                            (customers.c.org_id == feature_gap_mentions.c.org_id)
                            & (customers.c.external_customer_id == feature_gap_mentions.c.external_customer_id),
                        )
                    )
                    .where(
                        feature_gap_mentions.c.org_id == org_id,
                        feature_gap_mentions.c.feature_name.in_(chunk),
                        feature_gap_mentions.c.confidence >= _SCORE_MIN_CONFIDENCE,
                    )
                    .group_by(
                        feature_gap_mentions.c.feature_name,
                        feature_gap_mentions.c.external_customer_id,
                        latest.c.arr,
                        latest.c.mrr,
                        customers.c.customer_name,
                    )
                )
                acc: dict[str, dict[str, Any]] = defaultdict(
                    lambda: {"arr": 0.0, "mrr": 0.0, "customers": 0, "mentions": 0, "top": []}
                )
                for r in per_customer.mappings():
                    a = acc[r["feature_name"]]
                    a["arr"] += float(r["arr"])
                    a["mrr"] += float(r["mrr"])
                    a["customers"] += 1
                    a["mentions"] += int(r["mentions"])
                    a["top"].append((r["name"], float(r["arr"])))

                trends = await topic_trends(
                    conn, feature_gap_mentions, "feature_name", org_id, chunk,
                    now=now, min_confidence=_SCORE_MIN_CONFIDENCE,
                )
                for name in chunk:
                    a = acc.get(name) or {"arr": 0.0, "mrr": 0.0, "customers": 0, "mentions": 0, "top": []}
                    top = [n for n, _ in sorted(a["top"], key=lambda t: t[1], reverse=True)[:_TOP_CUSTOMERS]]
                    trend = trends.get(name)
                    await conn.execute(
                        upsert(
                            dialect,
                            feature_gap_scores,
                            {
                                "org_id": org_id,
                                "feature_name": name,
                                "total_arr_at_stake": a["arr"],
                                "total_mrr_at_stake": a["mrr"],
                                "customer_count": a["customers"],
                                "mention_count": a["mentions"],
                                "score": compute_feature_gap_score(a["arr"], a["customers"], a["mentions"]),
                                "top_customers": top,
                                "trend": trend.model_dump(mode="json") if trend else None,
                                "updated_at": now,
                            },
                            conflict_cols=["org_id", "feature_name"],
                            update=lambda new: {
                                col: getattr(new, col)
                                for col in (
                                    "total_arr_at_stake", "total_mrr_at_stake", "customer_count",
                                    "mention_count", "score", "top_customers", "trend", "updated_at",
                                )
                            },
                        )
                    )
            self.logger.debug("Recomputed %d feature-gap score(s) for org %s", len(names), org_id)

    @staticmethod
    def _latest_revenue_subquery(org_id: str) -> Any:  # noqa: ANN401 - SQLAlchemy subquery
        rn = (
            func.row_number()
            .over(
                partition_by=revenue_snapshots.c.external_customer_id,
                order_by=[revenue_snapshots.c.snapshot_at.desc(), revenue_snapshots.c.id.desc()],
            )
            .label("rn")
        )
        ranked = (
            select(revenue_snapshots.c.external_customer_id, revenue_snapshots.c.arr, revenue_snapshots.c.mrr, rn)
            .where(revenue_snapshots.c.org_id == org_id)
            .subquery("ranked_revenue")
        )
        return select(ranked).where(ranked.c.rn == 1).subquery("latest_revenue")

    # ------------------------------------------------------ audit + erasure

    async def record_audit(self, entry: AuditEntry) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                intelligence_audit_log.insert().values(
                    org_id=entry.org_id,
                    actor=entry.actor,
                    action=entry.action,
                    target_type=entry.target_type,
                    target_id=entry.target_id[:255],
                    details=entry.details or {},
                    created_at=entry.created_at or utcnow(),
                )
            )

    async def list_audit(self, org_id: str, limit: int = 50, offset: int = 0) -> tuple[list[AuditEntry], int]:
        async with self.engine.begin() as conn:
            total = (
                await conn.execute(
                    select(func.count()).select_from(intelligence_audit_log).where(
                        intelligence_audit_log.c.org_id == org_id
                    )
                )
            ).scalar_one()
            rows = (
                await conn.execute(
                    select(intelligence_audit_log)
                    .where(intelligence_audit_log.c.org_id == org_id)
                    .order_by(intelligence_audit_log.c.created_at.desc(), intelligence_audit_log.c.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).mappings().all()
        entries = [
            AuditEntry(
                org_id=r["org_id"],
                actor=r["actor"],
                action=r["action"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                details=r["details"] or {},
                created_at=r["created_at"],
            )
            for r in rows
        ]
        return entries, int(total)

    async def erase_customer(self, org_id: str, external_customer_id: str) -> ErasureResult:
        async with self.engine.begin() as conn:
            affected = await self._feature_names_where(
                conn, feature_gap_mentions.c.external_customer_id == external_customer_id, org_id
            )
            result = ErasureResult(
                feature_gap_mentions=await self._delete(
                    conn, feature_gap_mentions, org_id,
                    feature_gap_mentions.c.external_customer_id == external_customer_id,
                ),
                pain_point_mentions=await self._delete(
                    conn, pain_point_mentions, org_id,
                    pain_point_mentions.c.external_customer_id == external_customer_id,
                ),
                revenue_snapshots=await self._delete(
                    conn, revenue_snapshots, org_id,
                    revenue_snapshots.c.external_customer_id == external_customer_id,
                ),
                customers=await self._delete(
                    conn, customers, org_id, customers.c.external_customer_id == external_customer_id
                ),
            )
        await self.recompute_feature_gap_scores(org_id, affected)
        return result

    async def erase_source_record(self, org_id: str, source_record_id: str) -> ErasureResult:
        """Remove every mention derived from one PipesHub record.

        Rows written before ``source_record_id`` existed are matched by their
        event id, which was the record id (``<id>`` or ``<id>:row:<n>``).
        """
        def _match(table: Any) -> Any:  # noqa: ANN401
            return or_(
                table.c.source_record_id == source_record_id,
                table.c.external_event_id == source_record_id,
                table.c.external_event_id.like(f"{source_record_id}:%"),
            )

        async with self.engine.begin() as conn:
            affected = await self._feature_names_where(conn, _match(feature_gap_mentions), org_id)
            result = ErasureResult(
                feature_gap_mentions=await self._delete(conn, feature_gap_mentions, org_id, _match(feature_gap_mentions)),
                pain_point_mentions=await self._delete(conn, pain_point_mentions, org_id, _match(pain_point_mentions)),
            )
        await self.recompute_feature_gap_scores(org_id, affected)
        return result

    async def purge_mentions_before(self, org_id: str, cutoff: datetime) -> ErasureResult:
        async with self.engine.begin() as conn:
            affected = await self._feature_names_where(
                conn, feature_gap_mentions.c.occurred_at < cutoff, org_id
            )
            result = ErasureResult(
                feature_gap_mentions=await self._delete(
                    conn, feature_gap_mentions, org_id, feature_gap_mentions.c.occurred_at < cutoff
                ),
                pain_point_mentions=await self._delete(
                    conn, pain_point_mentions, org_id, pain_point_mentions.c.occurred_at < cutoff
                ),
            )
        await self.recompute_feature_gap_scores(org_id, affected)
        return result

    @staticmethod
    async def _feature_names_where(conn: AsyncConnection, condition: Any, org_id: str) -> list[str]:  # noqa: ANN401
        rows = await conn.execute(
            select(feature_gap_mentions.c.feature_name)
            .where(feature_gap_mentions.c.org_id == org_id, condition)
            .distinct()
        )
        return [r[0] for r in rows]

    @staticmethod
    async def _delete(conn: AsyncConnection, table: Any, org_id: str, condition: Any) -> int:  # noqa: ANN401
        result = await conn.execute(delete(table).where(table.c.org_id == org_id, condition))
        return int(result.rowcount or 0)
