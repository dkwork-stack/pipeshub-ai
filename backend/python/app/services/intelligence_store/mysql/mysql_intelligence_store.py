"""MySQL implementation of IIntelligenceStore, via SQLAlchemy async core + aiomysql.

Uses Core (not the ORM) so the table definitions in ``schema.py`` stay the
single source of truth and queries stay explicit/auditable — this store is a
thin, replaceable adapter, not a place for business logic (that lives in
``app/modules/customer_intelligence``).
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from logging import Logger
from typing import Dict, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.models.intelligence import (
    CustomerRevenueSnapshot,
    FeatureGapMentionRecord,
    FeatureGapScore,
    IntelligenceTopic,
    PainPointMentionRecord,
    TopicGuidanceUpdate,
    TopicKind,
)
from app.modules.customer_intelligence.scoring import compute_feature_gap_score
from app.services.intelligence_store.interface.intelligence_store import (
    IIntelligenceStore,
)
from app.services.intelligence_store.mysql.schema import (
    customers,
    feature_gap_mentions,
    feature_gap_scores,
    feature_gaps,
    intelligence_topics,
    metadata,
    pain_point_mentions,
    revenue_snapshots,
)

# Mentions below this confidence still persist and remain visible in the UI,
# but they do not contribute to revenue-weighted feature-gap scores.
_SCORE_MIN_CONFIDENCE = float(__import__("os").getenv("INTELLIGENCE_SCORE_MIN_CONFIDENCE", "0.5"))


def _topic_from_row(r) -> IntelligenceTopic:
    return IntelligenceTopic(
        id=r["id"],
        org_id=r["org_id"],
        kind=TopicKind(r["kind"]),
        canonical_name=r["canonical_name"],
        aliases=list(r["aliases"] or []),
        guidance=r["guidance"],
        merged_into_id=r["merged_into_id"],
        updated_by=r["updated_by"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class MySQLIntelligenceStore(IIntelligenceStore):
    def __init__(self, logger: Logger, dsn: str, pool_size: int = 10, max_overflow: int = 10) -> None:
        self.logger = logger
        self.dsn = dsn
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        # aiomysql / SQLAlchemy async pools bind to the loop that created them.
        # Indexing creates the store on the uvicorn loop, then runs ingestion on
        # the consumer worker-thread loop — one shared engine raises
        # "Future attached to a different loop". Mirror QdrantService: one
        # engine per running loop, created lazily after connect().
        self._engines: Dict[asyncio.AbstractEventLoop, AsyncEngine] = {}
        self._engines_lock = threading.Lock()
        self._connected = False

    def _create_engine(self) -> AsyncEngine:
        return create_async_engine(
            self.dsn,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_pre_ping=True,
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
                await conn.run_sync(metadata.create_all)
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

    async def upsert_customer(
        self, org_id: str, external_customer_id: str, customer_name: str
    ) -> None:
        now = datetime.utcnow()
        stmt = mysql_insert(customers).values(
            org_id=org_id,
            external_customer_id=external_customer_id,
            customer_name=customer_name,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_duplicate_key_update(
            customer_name=stmt.inserted.customer_name, updated_at=now
        )
        async with self.engine.begin() as conn:
            await conn.execute(stmt)

    async def upsert_revenue_snapshot(self, snapshot: CustomerRevenueSnapshot) -> None:
        async with self.engine.begin() as conn:
            await self.upsert_customer(
                snapshot.org_id, snapshot.external_customer_id, snapshot.customer_name
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

    async def upsert_feature_gap_mention(self, mention: FeatureGapMentionRecord) -> None:
        now = datetime.utcnow()
        async with self.engine.begin() as conn:
            fg_stmt = mysql_insert(feature_gaps).values(
                org_id=mention.org_id, feature_name=mention.feature_name, created_at=now
            )
            fg_stmt = fg_stmt.on_duplicate_key_update(feature_name=fg_stmt.inserted.feature_name)
            await conn.execute(fg_stmt)

            mention_stmt = mysql_insert(feature_gap_mentions).values(
                org_id=mention.org_id,
                external_customer_id=mention.external_customer_id,
                feature_name=mention.feature_name,
                description=mention.description,
                confidence=mention.confidence,
                excerpt=mention.excerpt,
                source_connector=mention.source_connector,
                source_type=mention.source_type.value,
                external_event_id=mention.external_event_id,
                citation_url=mention.citation_url,
                occurred_at=mention.occurred_at,
                created_at=now,
            )
            # Re-processing the same source event keeps the higher confidence.
            mention_stmt = mention_stmt.on_duplicate_key_update(
                description=mention_stmt.inserted.description,
                confidence=func.greatest(
                    feature_gap_mentions.c.confidence, mention_stmt.inserted.confidence
                ),
                excerpt=mention_stmt.inserted.excerpt,
            )
            await conn.execute(mention_stmt)

        await self.recompute_feature_gap_scores(mention.org_id, [mention.feature_name])

    async def upsert_pain_point_mention(self, mention: PainPointMentionRecord) -> None:
        now = datetime.utcnow()
        async with self.engine.begin() as conn:
            topic = IntelligenceTopic(
                org_id=mention.org_id,
                kind=TopicKind.PAIN_POINT,
                canonical_name=mention.topic_name,
            )
            await self._upsert_topic_conn(conn, topic)

            mention_stmt = mysql_insert(pain_point_mentions).values(
                org_id=mention.org_id,
                external_customer_id=mention.external_customer_id,
                topic_name=mention.topic_name[:191],
                summary=mention.summary,
                sentiment=mention.sentiment,
                confidence=mention.confidence,
                excerpt=mention.excerpt,
                source_connector=mention.source_connector,
                source_type=mention.source_type.value,
                external_event_id=mention.external_event_id,
                citation_url=mention.citation_url,
                occurred_at=mention.occurred_at,
                created_at=now,
            )
            mention_stmt = mention_stmt.on_duplicate_key_update(
                summary=mention_stmt.inserted.summary,
                sentiment=mention_stmt.inserted.sentiment,
                confidence=func.greatest(
                    pain_point_mentions.c.confidence, mention_stmt.inserted.confidence
                ),
                excerpt=mention_stmt.inserted.excerpt,
            )
            await conn.execute(mention_stmt)

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
        return [_topic_from_row(r) for r in rows]

    async def get_topic(self, org_id: str, topic_id: int) -> Optional[IntelligenceTopic]:
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    select(intelligence_topics).where(
                        intelligence_topics.c.org_id == org_id,
                        intelligence_topics.c.id == topic_id,
                    )
                )
            ).mappings().first()
        return _topic_from_row(row) if row else None

    async def upsert_topic(self, topic: IntelligenceTopic) -> IntelligenceTopic:
        async with self.engine.begin() as conn:
            return await self._upsert_topic_conn(conn, topic)

    async def _upsert_topic_conn(self, conn, topic: IntelligenceTopic) -> IntelligenceTopic:
        now = datetime.utcnow()
        stmt = mysql_insert(intelligence_topics).values(
            org_id=topic.org_id,
            kind=topic.kind.value if isinstance(topic.kind, TopicKind) else topic.kind,
            canonical_name=topic.canonical_name,
            aliases=topic.aliases or [],
            guidance=topic.guidance,
            merged_into_id=topic.merged_into_id,
            updated_by=topic.updated_by,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_duplicate_key_update(
            aliases=stmt.inserted.aliases,
            guidance=func.coalesce(stmt.inserted.guidance, intelligence_topics.c.guidance),
            updated_by=func.coalesce(stmt.inserted.updated_by, intelligence_topics.c.updated_by),
            updated_at=now,
        )
        await conn.execute(stmt)
        row = (
            await conn.execute(
                select(intelligence_topics).where(
                    intelligence_topics.c.org_id == topic.org_id,
                    intelligence_topics.c.kind == (
                        topic.kind.value if isinstance(topic.kind, TopicKind) else topic.kind
                    ),
                    intelligence_topics.c.canonical_name == topic.canonical_name,
                )
            )
        ).mappings().first()
        return _topic_from_row(row)

    async def update_topic_guidance(
        self, org_id: str, topic_id: int, update_payload: TopicGuidanceUpdate
    ) -> Optional[IntelligenceTopic]:
        values: dict = {"updated_at": datetime.utcnow()}
        if update_payload.guidance is not None:
            values["guidance"] = update_payload.guidance
        if update_payload.aliases is not None:
            values["aliases"] = update_payload.aliases
        if update_payload.canonical_name is not None:
            values["canonical_name"] = update_payload.canonical_name
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
            row = (
                await conn.execute(
                    select(intelligence_topics).where(
                        intelligence_topics.c.org_id == org_id,
                        intelligence_topics.c.id == topic_id,
                    )
                )
            ).mappings().first()
        return _topic_from_row(row) if row else None

    async def merge_topics(
        self, org_id: str, source_id: int, target_id: int
    ) -> Optional[IntelligenceTopic]:
        if source_id == target_id:
            return await self.get_topic(org_id, target_id)

        async with self.engine.begin() as conn:
            source = (
                await conn.execute(
                    select(intelligence_topics).where(
                        intelligence_topics.c.org_id == org_id,
                        intelligence_topics.c.id == source_id,
                    )
                )
            ).mappings().first()
            target = (
                await conn.execute(
                    select(intelligence_topics).where(
                        intelligence_topics.c.org_id == org_id,
                        intelligence_topics.c.id == target_id,
                    )
                )
            ).mappings().first()
            if not source or not target:
                return None
            if source["kind"] != target["kind"]:
                raise ValueError("Cannot merge topics of different kinds")

            source_name = source["canonical_name"]
            target_name = target["canonical_name"]
            kind = source["kind"]

            if kind == TopicKind.FEATURE_GAP.value:
                await self._rewrite_feature_gap_mentions(conn, org_id, source_name, target_name)
            else:
                await self._rewrite_pain_point_mentions(conn, org_id, source_name, target_name)

            aliases = list(target["aliases"] or [])
            if source_name not in aliases:
                aliases.append(source_name)
            for alias in source["aliases"] or []:
                if alias not in aliases and alias != target_name:
                    aliases.append(alias)

            await conn.execute(
                update(intelligence_topics)
                .where(intelligence_topics.c.id == target_id)
                .values(aliases=aliases, updated_at=datetime.utcnow())
            )
            await conn.execute(
                update(intelligence_topics)
                .where(intelligence_topics.c.id == source_id)
                .values(merged_into_id=target_id, updated_at=datetime.utcnow())
            )

        if kind == TopicKind.FEATURE_GAP.value:
            await self.recompute_feature_gap_scores(org_id, [source_name, target_name])

        return await self.get_topic(org_id, target_id)

    async def _rewrite_feature_gap_mentions(self, conn, org_id: str, source_name: str, target_name: str) -> None:
        rows = (
            await conn.execute(
                select(feature_gap_mentions).where(
                    feature_gap_mentions.c.org_id == org_id,
                    feature_gap_mentions.c.feature_name == source_name,
                )
            )
        ).mappings().all()
        now = datetime.utcnow()
        fg_stmt = mysql_insert(feature_gaps).values(
            org_id=org_id, feature_name=target_name, created_at=now
        )
        fg_stmt = fg_stmt.on_duplicate_key_update(feature_name=fg_stmt.inserted.feature_name)
        await conn.execute(fg_stmt)

        for row in rows:
            insert_stmt = mysql_insert(feature_gap_mentions).values(
                org_id=row["org_id"],
                external_customer_id=row["external_customer_id"],
                feature_name=target_name[:191],
                description=row["description"],
                confidence=row["confidence"],
                excerpt=row["excerpt"],
                source_connector=row["source_connector"],
                source_type=row["source_type"],
                external_event_id=row["external_event_id"],
                citation_url=row["citation_url"],
                occurred_at=row["occurred_at"],
                created_at=row["created_at"],
            )
            insert_stmt = insert_stmt.on_duplicate_key_update(
                confidence=func.greatest(
                    feature_gap_mentions.c.confidence, insert_stmt.inserted.confidence
                ),
            )
            await conn.execute(insert_stmt)
            await conn.execute(
                feature_gap_mentions.delete().where(feature_gap_mentions.c.id == row["id"])
            )

    async def _rewrite_pain_point_mentions(self, conn, org_id: str, source_name: str, target_name: str) -> None:
        rows = (
            await conn.execute(
                select(pain_point_mentions).where(
                    pain_point_mentions.c.org_id == org_id,
                    pain_point_mentions.c.topic_name == source_name,
                )
            )
        ).mappings().all()
        for row in rows:
            insert_stmt = mysql_insert(pain_point_mentions).values(
                org_id=row["org_id"],
                external_customer_id=row["external_customer_id"],
                topic_name=target_name[:191],
                summary=row["summary"],
                sentiment=row["sentiment"],
                confidence=row["confidence"],
                excerpt=row["excerpt"],
                source_connector=row["source_connector"],
                source_type=row["source_type"],
                external_event_id=row["external_event_id"],
                citation_url=row["citation_url"],
                occurred_at=row["occurred_at"],
                created_at=row["created_at"],
            )
            insert_stmt = insert_stmt.on_duplicate_key_update(
                confidence=func.greatest(
                    pain_point_mentions.c.confidence, insert_stmt.inserted.confidence
                ),
            )
            await conn.execute(insert_stmt)
            await conn.execute(
                pain_point_mentions.delete().where(pain_point_mentions.c.id == row["id"])
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

    async def recompute_feature_gap_scores(
        self, org_id: str, feature_names: Optional[list[str]] = None
    ) -> None:
        async with self.engine.begin() as conn:
            if feature_names is None:
                rows = (
                    await conn.execute(
                        select(feature_gaps.c.feature_name).where(feature_gaps.c.org_id == org_id)
                    )
                ).all()
                feature_names = [r[0] for r in rows]

            for feature_name in feature_names:
                # Distinct customers + mention count — only score-eligible confidence.
                mention_rows = (
                    await conn.execute(
                        select(
                            feature_gap_mentions.c.external_customer_id,
                            func.count().label("mentions"),
                        )
                        .where(
                            feature_gap_mentions.c.org_id == org_id,
                            feature_gap_mentions.c.feature_name == feature_name,
                            feature_gap_mentions.c.confidence >= _SCORE_MIN_CONFIDENCE,
                        )
                        .group_by(feature_gap_mentions.c.external_customer_id)
                    )
                ).all()
                customer_ids = [r[0] for r in mention_rows]
                mention_count = sum(r[1] for r in mention_rows)
                customer_count = len(customer_ids)

                total_arr = 0.0
                total_mrr = 0.0
                top_customer_names: list[tuple[str, float]] = []
                for external_customer_id in customer_ids:
                    latest = (
                        await conn.execute(
                            select(revenue_snapshots.c.arr, revenue_snapshots.c.mrr)
                            .where(
                                revenue_snapshots.c.org_id == org_id,
                                revenue_snapshots.c.external_customer_id == external_customer_id,
                            )
                            .order_by(revenue_snapshots.c.snapshot_at.desc())
                            .limit(1)
                        )
                    ).first()
                    arr = latest.arr if latest else 0.0
                    mrr = latest.mrr if latest else 0.0
                    total_arr += arr
                    total_mrr += mrr

                    name_row = (
                        await conn.execute(
                            select(customers.c.customer_name).where(
                                customers.c.org_id == org_id,
                                customers.c.external_customer_id == external_customer_id,
                            )
                        )
                    ).first()
                    top_customer_names.append((name_row.customer_name if name_row else external_customer_id, arr))

                top_customer_names.sort(key=lambda t: t[1], reverse=True)
                score = compute_feature_gap_score(total_arr, customer_count, mention_count)

                stmt = mysql_insert(feature_gap_scores).values(
                    org_id=org_id,
                    feature_name=feature_name,
                    total_arr_at_stake=total_arr,
                    total_mrr_at_stake=total_mrr,
                    customer_count=customer_count,
                    mention_count=mention_count,
                    score=score,
                    top_customers=[n for n, _ in top_customer_names[:5]],
                    updated_at=datetime.utcnow(),
                )
                stmt = stmt.on_duplicate_key_update(
                    total_arr_at_stake=stmt.inserted.total_arr_at_stake,
                    total_mrr_at_stake=stmt.inserted.total_mrr_at_stake,
                    customer_count=stmt.inserted.customer_count,
                    mention_count=stmt.inserted.mention_count,
                    score=stmt.inserted.score,
                    top_customers=stmt.inserted.top_customers,
                    updated_at=stmt.inserted.updated_at,
                )
                await conn.execute(stmt)

    async def list_feature_gap_scores(
        self, org_id: str, limit: int = 50, offset: int = 0
    ) -> list[FeatureGapScore]:
        async with self.engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(feature_gap_scores)
                    .where(feature_gap_scores.c.org_id == org_id)
                    .order_by(feature_gap_scores.c.score.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).mappings().all()
        return [
            FeatureGapScore(
                org_id=r["org_id"],
                feature_name=r["feature_name"],
                total_arr_at_stake=r["total_arr_at_stake"],
                total_mrr_at_stake=r["total_mrr_at_stake"],
                customer_count=r["customer_count"],
                mention_count=r["mention_count"],
                score=r["score"],
                top_customers=r["top_customers"] or [],
            )
            for r in rows
        ]

    async def get_feature_gap_detail(
        self, org_id: str, feature_name: str
    ) -> tuple[FeatureGapScore | None, list[FeatureGapMentionRecord]]:
        async with self.engine.begin() as conn:
            score_row = (
                await conn.execute(
                    select(feature_gap_scores).where(
                        feature_gap_scores.c.org_id == org_id,
                        feature_gap_scores.c.feature_name == feature_name,
                    )
                )
            ).mappings().first()
            mention_rows = (
                await conn.execute(
                    select(feature_gap_mentions)
                    .where(
                        feature_gap_mentions.c.org_id == org_id,
                        feature_gap_mentions.c.feature_name == feature_name,
                    )
                    .order_by(feature_gap_mentions.c.occurred_at.desc())
                )
            ).mappings().all()

        score = (
            FeatureGapScore(
                org_id=score_row["org_id"],
                feature_name=score_row["feature_name"],
                total_arr_at_stake=score_row["total_arr_at_stake"],
                total_mrr_at_stake=score_row["total_mrr_at_stake"],
                customer_count=score_row["customer_count"],
                mention_count=score_row["mention_count"],
                score=score_row["score"],
                top_customers=score_row["top_customers"] or [],
            )
            if score_row
            else None
        )
        mentions = [
            FeatureGapMentionRecord(
                org_id=m["org_id"],
                external_customer_id=m["external_customer_id"],
                feature_name=m["feature_name"],
                description=m["description"] or "",
                confidence=m["confidence"],
                excerpt=m["excerpt"] or "",
                source_connector=m["source_connector"],
                source_type=m["source_type"],
                external_event_id=m["external_event_id"],
                citation_url=m["citation_url"],
                occurred_at=m["occurred_at"],
            )
            for m in mention_rows
        ]
        return score, mentions

    async def get_customer_detail(self, org_id: str, external_customer_id: str) -> dict:
        async with self.engine.begin() as conn:
            customer_row = (
                await conn.execute(
                    select(customers).where(
                        customers.c.org_id == org_id,
                        customers.c.external_customer_id == external_customer_id,
                    )
                )
            ).mappings().first()
            latest_snapshot = (
                await conn.execute(
                    select(revenue_snapshots)
                    .where(
                        revenue_snapshots.c.org_id == org_id,
                        revenue_snapshots.c.external_customer_id == external_customer_id,
                    )
                    .order_by(revenue_snapshots.c.snapshot_at.desc())
                    .limit(1)
                )
            ).mappings().first()
            mention_rows = (
                await conn.execute(
                    select(feature_gap_mentions)
                    .where(
                        feature_gap_mentions.c.org_id == org_id,
                        feature_gap_mentions.c.external_customer_id == external_customer_id,
                    )
                    .order_by(feature_gap_mentions.c.occurred_at.desc())
                )
            ).mappings().all()

        return {
            "customer": dict(customer_row) if customer_row else None,
            "latest_revenue_snapshot": dict(latest_snapshot) if latest_snapshot else None,
            "feature_gap_mentions": [dict(m) for m in mention_rows],
        }

    async def list_customers(self, org_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        async with self.engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(customers)
                    .where(customers.c.org_id == org_id)
                    .order_by(customers.c.customer_name)
                    .limit(limit)
                    .offset(offset)
                )
            ).mappings().all()
            result = []
            for r in rows:
                latest_snapshot = (
                    await conn.execute(
                        select(revenue_snapshots)
                        .where(
                            revenue_snapshots.c.org_id == org_id,
                            revenue_snapshots.c.external_customer_id == r["external_customer_id"],
                        )
                        .order_by(revenue_snapshots.c.snapshot_at.desc())
                        .limit(1)
                    )
                ).mappings().first()
                result.append(
                    {
                        "customer": dict(r),
                        "latest_revenue_snapshot": dict(latest_snapshot) if latest_snapshot else None,
                    }
                )
        return result
