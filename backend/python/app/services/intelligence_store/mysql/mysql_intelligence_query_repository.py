"""MySQL implementation of IIntelligenceQueryRepository (read side).

Shares the SQLAlchemy async engine with ``MySQLIntelligenceStore`` (the write
side) but exposes only queries. Every statement filters on ``org_id`` — the
portal must never leak one tenant's customers into another's view.

Designed to stay O(1) round-trips per page: latest revenue is resolved with a
window function and per-customer insights with a single GROUP BY over the
page's customer ids, instead of one query per row.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Select, and_, case, exists, func, literal, or_, select, union_all

from app.models.intelligence import (
    AffectedCustomer,
    CustomerDetail,
    CustomerFilter,
    CustomerHealth,
    CustomerInsight,
    CustomerSummary,
    FeatureGapDetail,
    FeatureGapFilter,
    FeatureGapScore,
    IntelligenceOverview,
    MentionFilter,
    PainPointDetail,
    PainPointFilter,
    PainPointInsight,
    PainPointScore,
    RevenueSummary,
    TopicKind,
    TopicStatus,
    TopicTrend,
    Urgency,
)
from app.services.intelligence_store.interface.intelligence_query_repository import (
    IIntelligenceQueryRepository,
)
from app.services.intelligence_store.mysql.aggregates import (
    TREND_WINDOW,
    chunked,
    topic_trends,
)
from app.services.intelligence_store.mysql.rows import (
    mention_from_row,
    pain_mention_from_row,
    trend_from_json,
)
from app.services.intelligence_store.mysql.schema import (
    customers,
    feature_gap_mentions,
    feature_gap_scores,
    intelligence_topics,
    pain_point_mentions,
    revenue_snapshots,
)
from app.services.intelligence_store.mysql.sql import utcnow

_LOW_CONFIDENCE = float(os.getenv("INTELLIGENCE_SCORE_MIN_CONFIDENCE", "0.5"))

if TYPE_CHECKING:
    from logging import Logger

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
    from sqlalchemy.sql import ColumnElement, Subquery


def _like_pattern(query: str) -> str:
    escaped = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _score_from_row(
    r: "RowMapping", *, conf: Optional[dict] = None, status: TopicStatus = TopicStatus.OPEN
) -> FeatureGapScore:
    return FeatureGapScore(
        org_id=r["org_id"],
        feature_name=r["feature_name"],
        total_arr_at_stake=r["total_arr_at_stake"],
        total_mrr_at_stake=r["total_mrr_at_stake"],
        customer_count=r["customer_count"],
        mention_count=r["mention_count"],
        score=r["score"],
        top_customers=r["top_customers"] or [],
        max_confidence=(conf or {}).get("max_confidence"),
        avg_confidence=(conf or {}).get("avg_confidence"),
        low_confidence_count=(conf or {}).get("low_confidence_count", 0),
        trend=trend_from_json(r.get("trend")),
        status=status,
    )


_HIGH_URGENCY = (Urgency.HIGH.value, Urgency.CRITICAL.value)


def _growth(trend: Optional[TopicTrend]) -> float:
    """Emerging = recent volume that outpaces the prior window (new asks rank by volume)."""
    if trend is None or trend.mentions_last_30d == 0:
        return 0.0
    return (trend.mentions_last_30d - trend.mentions_prev_30d) + trend.mentions_last_30d / (1 + trend.mentions_prev_30d)


def _revenue_from_row(r: Optional["RowMapping"], prefix: str = "") -> Optional[RevenueSummary]:
    if r is None or r.get(f"{prefix}snapshot_at") is None:
        return None
    return RevenueSummary(
        source_connector=r[f"{prefix}source_connector"],
        mrr=r[f"{prefix}mrr"] or 0.0,
        arr=r[f"{prefix}arr"] or 0.0,
        seats_used=r.get(f"{prefix}seats_used"),
        seats_licensed=r.get(f"{prefix}seats_licensed"),
        consumed_features=r.get(f"{prefix}consumed_features") or [],
        renewal_date=r.get(f"{prefix}renewal_date"),
        snapshot_at=r[f"{prefix}snapshot_at"],
    )


class MySQLIntelligenceQueryRepository(IIntelligenceQueryRepository):
    def __init__(self, logger: Logger, engine: AsyncEngine) -> None:
        self.logger = logger
        self._engine = engine

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _latest_snapshots(org_id: str) -> Subquery:
        """Subquery: one row per customer — its most recent revenue snapshot."""
        rn = (
            func.row_number()
            .over(
                partition_by=revenue_snapshots.c.external_customer_id,
                order_by=[revenue_snapshots.c.snapshot_at.desc(), revenue_snapshots.c.id.desc()],
            )
            .label("rn")
        )
        ranked = (
            select(revenue_snapshots, rn)
            .where(revenue_snapshots.c.org_id == org_id)
            .subquery("ranked_snapshots")
        )
        return select(ranked).where(ranked.c.rn == 1).subquery("latest_snapshots")

    @staticmethod
    def _mention_exists(
        org_id: str,
        *,
        feature_name_col: Optional[ColumnElement] = None,
        customer_col: Optional[ColumnElement] = None,
        source_connector: Optional[str] = None,
        external_customer_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> ColumnElement:
        conds = [feature_gap_mentions.c.org_id == org_id]
        if feature_name_col is not None:
            conds.append(feature_gap_mentions.c.feature_name == feature_name_col)
        if customer_col is not None:
            conds.append(feature_gap_mentions.c.external_customer_id == customer_col)
        if source_connector:
            conds.append(feature_gap_mentions.c.source_connector == source_connector)
        if external_customer_id:
            conds.append(feature_gap_mentions.c.external_customer_id == external_customer_id)
        if min_confidence is not None:
            conds.append(feature_gap_mentions.c.confidence >= min_confidence)
        return exists(select(literal(1)).where(and_(*conds)))

    @staticmethod
    def _mention_conditions(
        org_id: str, mention_filter: MentionFilter, *extra: ColumnElement
    ) -> list[ColumnElement]:
        conds = [feature_gap_mentions.c.org_id == org_id, *extra]
        if mention_filter.external_customer_id:
            conds.append(feature_gap_mentions.c.external_customer_id == mention_filter.external_customer_id)
        if mention_filter.source_connector:
            conds.append(feature_gap_mentions.c.source_connector == mention_filter.source_connector)
        if mention_filter.min_confidence is not None:
            conds.append(feature_gap_mentions.c.confidence >= mention_filter.min_confidence)
        return conds

    @staticmethod
    def _pain_mention_conditions(
        org_id: str, mention_filter: MentionFilter, *extra: ColumnElement
    ) -> list[ColumnElement]:
        conds = [pain_point_mentions.c.org_id == org_id, *extra]
        if mention_filter.external_customer_id:
            conds.append(pain_point_mentions.c.external_customer_id == mention_filter.external_customer_id)
        if mention_filter.source_connector:
            conds.append(pain_point_mentions.c.source_connector == mention_filter.source_connector)
        if mention_filter.min_confidence is not None:
            conds.append(pain_point_mentions.c.confidence >= mention_filter.min_confidence)
        return conds

    @staticmethod
    async def _status_by_name(
        conn: AsyncConnection, org_id: str, kind: TopicKind, names: list[str]
    ) -> dict[str, TopicStatus]:
        out: dict[str, TopicStatus] = {}
        for chunk in chunked(names):
            rows = await conn.execute(
                select(intelligence_topics.c.canonical_name, intelligence_topics.c.status).where(
                    intelligence_topics.c.org_id == org_id,
                    intelligence_topics.c.kind == kind.value,
                    intelligence_topics.c.merged_into_id.is_(None),
                    intelligence_topics.c.canonical_name.in_(chunk),
                )
            )
            for name, status in rows:
                out[name] = TopicStatus(status or TopicStatus.OPEN.value)
        return out

    @staticmethod
    def _topic_status_condition(name_col: ColumnElement, org_id: str, kind: TopicKind, status: TopicStatus) -> ColumnElement:
        topic_match = select(literal(1)).where(
            intelligence_topics.c.org_id == org_id,
            intelligence_topics.c.kind == kind.value,
            intelligence_topics.c.merged_into_id.is_(None),
            intelligence_topics.c.canonical_name == name_col,
            func.coalesce(intelligence_topics.c.status, TopicStatus.OPEN.value) == status.value,
        )
        if status == TopicStatus.OPEN:
            # Topics never curated have no row status yet; they are open.
            no_topic = ~exists(
                select(literal(1)).where(
                    intelligence_topics.c.org_id == org_id,
                    intelligence_topics.c.kind == kind.value,
                    intelligence_topics.c.canonical_name == name_col,
                )
            )
            return or_(exists(topic_match), no_topic)
        return exists(topic_match)

    @staticmethod
    def _all_mentions(org_id: str) -> Subquery:
        """Both mention tables as one relation, for per-customer health roll-ups."""
        cols = lambda t: [  # noqa: E731
            t.c.external_customer_id, t.c.sentiment, t.c.urgency, t.c.churn_risk,
            t.c.competitor, t.c.occurred_at,
        ]
        return union_all(
            select(*cols(feature_gap_mentions)).where(feature_gap_mentions.c.org_id == org_id),
            select(*cols(pain_point_mentions)).where(pain_point_mentions.c.org_id == org_id),
        ).subquery("all_mentions")

    def _risk_by_customer(self, org_id: str) -> Subquery:
        m = self._all_mentions(org_id)
        return (
            select(
                m.c.external_customer_id,
                func.count().label("total"),
                func.sum(case((m.c.sentiment == "Negative", 1), else_=0)).label("negative"),
                func.sum(case((m.c.churn_risk.is_(True), 1), else_=0)).label("churn"),
                func.sum(case((m.c.urgency.in_(_HIGH_URGENCY), 1), else_=0)).label("high_urgency"),
                func.max(m.c.occurred_at).label("last_touch_at"),
            )
            .group_by(m.c.external_customer_id)
            .subquery("customer_risk")
        )

    async def _health_by_customer(
        self, conn: AsyncConnection, org_id: str, customer_ids: list[str]
    ) -> dict[str, CustomerHealth]:
        if not customer_ids:
            return {}
        risk = self._risk_by_customer(org_id)
        rows = (
            await conn.execute(select(risk).where(risk.c.external_customer_id.in_(customer_ids)))
        ).mappings().all()
        m = self._all_mentions(org_id)
        competitor_rows = await conn.execute(
            select(m.c.external_customer_id, m.c.competitor)
            .where(m.c.external_customer_id.in_(customer_ids), m.c.competitor.is_not(None))
            .group_by(m.c.external_customer_id, m.c.competitor)
        )
        competitors: dict[str, list[str]] = defaultdict(list)
        for cid, competitor in competitor_rows:
            competitors[cid].append(competitor)
        out: dict[str, CustomerHealth] = {}
        for r in rows:
            total = int(r["total"] or 0)
            out[r["external_customer_id"]] = CustomerHealth(
                negative_share=round(int(r["negative"] or 0) / total, 3) if total else 0.0,
                churn_risk_count=int(r["churn"] or 0),
                high_urgency_count=int(r["high_urgency"] or 0),
                last_touch_at=r["last_touch_at"],
                competitors=sorted(competitors.get(r["external_customer_id"], []))[:5],
            )
        return out

    async def _pain_counts_by_customer(
        self, conn: AsyncConnection, org_id: str, customer_ids: list[str]
    ) -> dict[str, int]:
        if not customer_ids:
            return {}
        rows = await conn.execute(
            select(pain_point_mentions.c.external_customer_id, func.count(pain_point_mentions.c.topic_name.distinct()))
            .where(pain_point_mentions.c.org_id == org_id, pain_point_mentions.c.external_customer_id.in_(customer_ids))
            .group_by(pain_point_mentions.c.external_customer_id)
        )
        return {cid: int(n) for cid, n in rows}

    async def _confidence_by_feature(
        self, conn: AsyncConnection, org_id: str, feature_names: list[str]
    ) -> dict[str, dict]:
        if not feature_names:
            return {}
        rows = (
            await conn.execute(
                select(
                    feature_gap_mentions.c.feature_name,
                    func.max(feature_gap_mentions.c.confidence).label("max_confidence"),
                    func.avg(feature_gap_mentions.c.confidence).label("avg_confidence"),
                    func.sum(
                        case(
                            (feature_gap_mentions.c.confidence < _LOW_CONFIDENCE, 1),
                            else_=0,
                        )
                    ).label("low_confidence_count"),
                )
                .where(
                    feature_gap_mentions.c.org_id == org_id,
                    feature_gap_mentions.c.feature_name.in_(feature_names),
                )
                .group_by(feature_gap_mentions.c.feature_name)
            )
        ).mappings().all()
        out: dict[str, dict] = {}
        for r in rows:
            out[r["feature_name"]] = {
                "max_confidence": float(r["max_confidence"]) if r["max_confidence"] is not None else None,
                "avg_confidence": float(r["avg_confidence"]) if r["avg_confidence"] is not None else None,
                "low_confidence_count": int(r["low_confidence_count"] or 0),
            }
        return out

    async def _insights_by_customer(
        self, conn: AsyncConnection, org_id: str, customer_ids: list[str]
    ) -> dict[str, list[CustomerInsight]]:
        """One GROUP BY for the whole page: customer -> insights sorted by weight."""
        if not customer_ids:
            return {}
        rows = (
            await conn.execute(
                select(
                    feature_gap_mentions.c.external_customer_id,
                    feature_gap_mentions.c.feature_name,
                    func.count().label("mention_count"),
                    func.max(feature_gap_mentions.c.confidence).label("max_confidence"),
                    func.avg(feature_gap_mentions.c.confidence).label("avg_confidence"),
                    func.sum(
                        case(
                            (feature_gap_mentions.c.confidence < _LOW_CONFIDENCE, 1),
                            else_=0,
                        )
                    ).label("low_confidence_count"),
                    func.max(feature_gap_mentions.c.occurred_at).label("last_mentioned_at"),
                    func.group_concat(feature_gap_mentions.c.source_connector.distinct()).label("connectors"),
                )
                .where(
                    feature_gap_mentions.c.org_id == org_id,
                    feature_gap_mentions.c.external_customer_id.in_(customer_ids),
                )
                .group_by(
                    feature_gap_mentions.c.external_customer_id,
                    feature_gap_mentions.c.feature_name,
                )
            )
        ).mappings().all()

        grouped: dict[str, list[CustomerInsight]] = defaultdict(list)
        for r in rows:
            connectors = sorted({c for c in (r["connectors"] or "").split(",") if c})
            grouped[r["external_customer_id"]].append(
                CustomerInsight(
                    feature_name=r["feature_name"],
                    mention_count=r["mention_count"],
                    max_confidence=r["max_confidence"] if r["max_confidence"] is not None else 0.0,
                    avg_confidence=float(r["avg_confidence"]) if r["avg_confidence"] is not None else None,
                    low_confidence_count=int(r["low_confidence_count"] or 0),
                    last_mentioned_at=r["last_mentioned_at"],
                    source_connectors=connectors,
                )
            )
        for insights in grouped.values():
            insights.sort(key=lambda i: (i.mention_count, i.max_confidence, i.last_mentioned_at), reverse=True)
        return grouped

    async def _pain_insights_by_customer(
        self, conn: AsyncConnection, org_id: str, customer_ids: list[str]
    ) -> dict[str, list[PainPointInsight]]:
        if not customer_ids:
            return {}
        rows = (
            await conn.execute(
                select(
                    pain_point_mentions.c.external_customer_id,
                    pain_point_mentions.c.topic_name,
                    func.count().label("mention_count"),
                    func.max(pain_point_mentions.c.confidence).label("max_confidence"),
                    func.avg(pain_point_mentions.c.confidence).label("avg_confidence"),
                    func.sum(
                        case(
                            (pain_point_mentions.c.confidence < _LOW_CONFIDENCE, 1),
                            else_=0,
                        )
                    ).label("low_confidence_count"),
                    func.max(pain_point_mentions.c.occurred_at).label("last_mentioned_at"),
                    func.group_concat(pain_point_mentions.c.source_connector.distinct()).label("connectors"),
                    func.group_concat(pain_point_mentions.c.sentiment.distinct()).label("sentiments"),
                )
                .where(
                    pain_point_mentions.c.org_id == org_id,
                    pain_point_mentions.c.external_customer_id.in_(customer_ids),
                )
                .group_by(
                    pain_point_mentions.c.external_customer_id,
                    pain_point_mentions.c.topic_name,
                )
            )
        ).mappings().all()

        grouped: dict[str, list[PainPointInsight]] = defaultdict(list)
        for r in rows:
            connectors = sorted({c for c in (r["connectors"] or "").split(",") if c})
            sentiments = sorted({s for s in (r["sentiments"] or "").split(",") if s})
            grouped[r["external_customer_id"]].append(
                PainPointInsight(
                    topic_name=r["topic_name"],
                    mention_count=r["mention_count"],
                    max_confidence=r["max_confidence"] if r["max_confidence"] is not None else 0.0,
                    avg_confidence=float(r["avg_confidence"]) if r["avg_confidence"] is not None else None,
                    low_confidence_count=int(r["low_confidence_count"] or 0),
                    last_mentioned_at=r["last_mentioned_at"],
                    source_connectors=connectors,
                    sentiments=sentiments,
                )
            )
        for insights in grouped.values():
            insights.sort(key=lambda i: (i.mention_count, i.max_confidence, i.last_mentioned_at), reverse=True)
        return grouped

    def _customer_base_query(self, org_id: str, filters: CustomerFilter) -> tuple[Select, Subquery]:
        latest = self._latest_snapshots(org_id)
        # Only customers.id here: the page query swaps in labelled columns via
        # with_only_columns, and the count query wraps this as a subquery where
        # duplicate column names (org_id on both tables) would be rejected.
        stmt = (
            select(customers.c.id)
            .select_from(
                customers.outerjoin(
                    latest,
                    and_(
                        latest.c.external_customer_id == customers.c.external_customer_id,
                        latest.c.org_id == customers.c.org_id,
                    ),
                )
            )
            .where(customers.c.org_id == org_id)
        )
        if filters.query:
            pattern = _like_pattern(filters.query)
            stmt = stmt.where(
                or_(
                    func.lower(customers.c.customer_name).like(pattern, escape="\\"),
                    func.lower(customers.c.external_customer_id).like(pattern, escape="\\"),
                )
            )
        if filters.min_arr is not None:
            stmt = stmt.where(func.coalesce(latest.c.arr, 0.0) >= filters.min_arr)
        if filters.source_connector:
            stmt = stmt.where(
                self._mention_exists(
                    org_id,
                    customer_col=customers.c.external_customer_id,
                    source_connector=filters.source_connector,
                )
            )
        if filters.at_risk:
            risk = self._risk_by_customer(org_id)
            stmt = stmt.where(
                customers.c.external_customer_id.in_(
                    select(risk.c.external_customer_id).where(
                        or_(risk.c.churn > 0, risk.c.negative * 2 >= risk.c.total)
                    )
                )
            )
        return stmt, latest

    async def _summaries(
        self, conn: AsyncConnection, org_id: str, rows: list[RowMapping], top_insights: int
    ) -> list[CustomerSummary]:
        ids = [r["external_customer_id"] for r in rows]
        insights_by_customer = await self._insights_by_customer(conn, org_id, ids)
        health = await self._health_by_customer(conn, org_id, ids)
        pain_counts = await self._pain_counts_by_customer(conn, org_id, ids)
        summaries: list[CustomerSummary] = []
        for r in rows:
            cid = r["external_customer_id"]
            insights = insights_by_customer.get(cid, [])
            summaries.append(
                CustomerSummary(
                    external_customer_id=cid,
                    customer_name=r["customer_name"],
                    latest_revenue=_revenue_from_row(r, prefix="latest_"),
                    feature_gap_count=len(insights),
                    pain_point_count=pain_counts.get(cid, 0),
                    mention_count=sum(i.mention_count for i in insights),
                    top_insights=insights[:top_insights],
                    health=health.get(cid),
                )
            )
        return summaries

    @staticmethod
    def _select_with_prefixed_snapshot(stmt: Select, latest: Subquery) -> Select:
        """Re-label snapshot columns so they don't collide with customers.* names."""
        cols = [
            customers.c.external_customer_id,
            customers.c.customer_name,
            latest.c.source_connector.label("latest_source_connector"),
            latest.c.mrr.label("latest_mrr"),
            latest.c.arr.label("latest_arr"),
            latest.c.seats_used.label("latest_seats_used"),
            latest.c.seats_licensed.label("latest_seats_licensed"),
            latest.c.consumed_features.label("latest_consumed_features"),
            latest.c.renewal_date.label("latest_renewal_date"),
            latest.c.snapshot_at.label("latest_snapshot_at"),
        ]
        return stmt.with_only_columns(*cols)

    # ------------------------------------------------------------------ overview

    async def get_overview(self, org_id: str, *, top_n: int = 5) -> IntelligenceOverview:
        latest = self._latest_snapshots(org_id)
        # Customers with >=1 mention, joined to their latest revenue: ARR at
        # stake is counted once per customer, not once per gap.
        engaged = (
            select(feature_gap_mentions.c.external_customer_id)
            .where(feature_gap_mentions.c.org_id == org_id)
            .distinct()
            .subquery("engaged_customers")
        )
        totals_stmt = select(
            func.coalesce(func.sum(latest.c.arr), 0.0).label("arr"),
            func.coalesce(func.sum(latest.c.mrr), 0.0).label("mrr"),
        ).select_from(engaged.join(latest, latest.c.external_customer_id == engaged.c.external_customer_id))

        counts_stmt = select(
            func.count().label("mention_count"),
            func.count(feature_gap_mentions.c.external_customer_id.distinct()).label("customer_count"),
            func.count(feature_gap_mentions.c.feature_name.distinct()).label("feature_gap_count"),
            # Ingestion time, not source-event occurred_at — otherwise an upload of
            # historical tickets makes "Last evidence" look stale.
            func.max(feature_gap_mentions.c.created_at).label("last_mention_at"),
        ).where(feature_gap_mentions.c.org_id == org_id)

        pain_last_stmt = select(
            func.max(pain_point_mentions.c.created_at).label("last_pain_at"),
        ).where(pain_point_mentions.c.org_id == org_id)

        async with self._engine.connect() as conn:
            totals = (await conn.execute(totals_stmt)).mappings().first()
            counts = (await conn.execute(counts_stmt)).mappings().first()
            pain_last = (await conn.execute(pain_last_stmt)).mappings().first()
            connectors = [
                r[0]
                for r in (
                    await conn.execute(
                        select(feature_gap_mentions.c.source_connector)
                        .where(feature_gap_mentions.c.org_id == org_id)
                        .distinct()
                        .order_by(feature_gap_mentions.c.source_connector)
                    )
                ).all()
            ]
            top_gap_rows = (
                await conn.execute(
                    select(feature_gap_scores)
                    .where(feature_gap_scores.c.org_id == org_id)
                    .order_by(feature_gap_scores.c.score.desc(), feature_gap_scores.c.feature_name)
                    .limit(top_n)
                )
            ).mappings().all()
            # Emerging: recent activity only, ranked by growth over the prior window.
            recent_gap_rows = (
                await conn.execute(
                    select(feature_gap_scores).where(
                        feature_gap_scores.c.org_id == org_id,
                        feature_gap_scores.c.feature_name.in_(
                            select(feature_gap_mentions.c.feature_name)
                            .where(
                                feature_gap_mentions.c.org_id == org_id,
                                feature_gap_mentions.c.occurred_at >= utcnow() - TREND_WINDOW,
                            )
                            .distinct()
                        ),
                    )
                )
            ).mappings().all()
            emerging_rows = sorted(
                (r for r in recent_gap_rows if _growth(trend_from_json(r.get("trend"))) > 0),
                key=lambda r: (-_growth(trend_from_json(r.get("trend"))), -r["score"]),
            )[:top_n]
            statuses = await self._status_by_name(
                conn, org_id, TopicKind.FEATURE_GAP,
                [r["feature_name"] for r in (*top_gap_rows, *emerging_rows)],
            )
            pain_count = (
                await conn.execute(
                    select(func.count(pain_point_mentions.c.topic_name.distinct())).where(
                        pain_point_mentions.c.org_id == org_id
                    )
                )
            ).scalar_one()
            intent_mix = {
                k: int(v)
                for k, v in await conn.execute(
                    select(feature_gap_mentions.c.intent, func.count())
                    .where(feature_gap_mentions.c.org_id == org_id, feature_gap_mentions.c.intent.is_not(None))
                    .group_by(feature_gap_mentions.c.intent)
                )
            }
            m = self._all_mentions(org_id)
            tone_mix = {
                k: int(v)
                for k, v in await conn.execute(
                    select(m.c.sentiment, func.count()).where(m.c.sentiment.is_not(None)).group_by(m.c.sentiment)
                )
            }

        top_customers, _ = await self.search_customers(
            org_id, CustomerFilter(), limit=top_n, offset=0, top_insights=3
        )
        at_risk_customers, _ = await self.search_customers(
            org_id, CustomerFilter(at_risk=True), limit=top_n, offset=0, top_insights=3
        )

        fg_last = counts["last_mention_at"] if counts else None
        pp_last = pain_last["last_pain_at"] if pain_last else None
        if fg_last and pp_last:
            last_mention_at = max(fg_last, pp_last)
        else:
            last_mention_at = fg_last or pp_last

        return IntelligenceOverview(
            total_arr_at_stake=float(totals["arr"] or 0.0) if totals else 0.0,
            total_mrr_at_stake=float(totals["mrr"] or 0.0) if totals else 0.0,
            feature_gap_count=counts["feature_gap_count"] if counts else 0,
            customer_count=counts["customer_count"] if counts else 0,
            mention_count=counts["mention_count"] if counts else 0,
            source_connectors=connectors,
            top_feature_gaps=[
                _score_from_row(r, status=statuses.get(r["feature_name"], TopicStatus.OPEN)) for r in top_gap_rows
            ],
            top_customers=top_customers,
            last_mention_at=last_mention_at,
            pain_point_count=int(pain_count or 0),
            emerging_feature_gaps=[
                _score_from_row(r, status=statuses.get(r["feature_name"], TopicStatus.OPEN)) for r in emerging_rows
            ],
            at_risk_customers=at_risk_customers,
            intent_mix=intent_mix,
            tone_mix=tone_mix,
        )

    # -------------------------------------------------------------- feature gaps

    def _feature_gap_base_query(self, org_id: str, filters: FeatureGapFilter) -> Select:
        stmt = select(feature_gap_scores).where(feature_gap_scores.c.org_id == org_id)
        if filters.query:
            stmt = stmt.where(
                func.lower(feature_gap_scores.c.feature_name).like(_like_pattern(filters.query), escape="\\")
            )
        if filters.min_arr is not None:
            stmt = stmt.where(feature_gap_scores.c.total_arr_at_stake >= filters.min_arr)
        if filters.source_connector or filters.external_customer_id or filters.min_confidence is not None:
            stmt = stmt.where(
                self._mention_exists(
                    org_id,
                    feature_name_col=feature_gap_scores.c.feature_name,
                    source_connector=filters.source_connector,
                    external_customer_id=filters.external_customer_id,
                    min_confidence=filters.min_confidence,
                )
            )
        if filters.intent is not None:
            stmt = stmt.where(
                exists(
                    select(literal(1)).where(
                        feature_gap_mentions.c.org_id == org_id,
                        feature_gap_mentions.c.feature_name == feature_gap_scores.c.feature_name,
                        feature_gap_mentions.c.intent == filters.intent.value,
                    )
                )
            )
        if filters.status is not None:
            stmt = stmt.where(
                self._topic_status_condition(feature_gap_scores.c.feature_name, org_id, TopicKind.FEATURE_GAP, filters.status)
            )
        return stmt

    async def search_feature_gaps(
        self, org_id: str, filters: FeatureGapFilter, *, limit: int, offset: int
    ) -> tuple[list[FeatureGapScore], int]:
        base = self._feature_gap_base_query(org_id, filters)
        count_stmt = select(func.count()).select_from(base.subquery())
        page_stmt = (
            base.order_by(feature_gap_scores.c.score.desc(), feature_gap_scores.c.feature_name)
            .limit(limit)
            .offset(offset)
        )
        async with self._engine.connect() as conn:
            total = (await conn.execute(count_stmt)).scalar_one()
            rows = (await conn.execute(page_stmt)).mappings().all()
            names = [r["feature_name"] for r in rows]
            conf = await self._confidence_by_feature(conn, org_id, names)
            statuses = await self._status_by_name(conn, org_id, TopicKind.FEATURE_GAP, names)
        return [
            _score_from_row(r, conf=conf.get(r["feature_name"]), status=statuses.get(r["feature_name"], TopicStatus.OPEN))
            for r in rows
        ], int(total)

    async def get_feature_gap(
        self, org_id: str, feature_name: str, mention_filter: MentionFilter
    ) -> Optional[FeatureGapDetail]:
        latest = self._latest_snapshots(org_id)
        per_customer = (
            select(
                feature_gap_mentions.c.external_customer_id,
                func.count().label("mention_count"),
            )
            .where(
                feature_gap_mentions.c.org_id == org_id,
                feature_gap_mentions.c.feature_name == feature_name,
            )
            .group_by(feature_gap_mentions.c.external_customer_id)
            .subquery("per_customer")
        )
        affected_stmt = (
            select(
                per_customer.c.external_customer_id,
                per_customer.c.mention_count,
                customers.c.customer_name,
                latest.c.arr,
                latest.c.mrr,
            )
            .select_from(
                per_customer.outerjoin(
                    customers,
                    and_(
                        customers.c.org_id == org_id,
                        customers.c.external_customer_id == per_customer.c.external_customer_id,
                    ),
                ).outerjoin(latest, latest.c.external_customer_id == per_customer.c.external_customer_id)
            )
            .order_by(func.coalesce(latest.c.arr, 0.0).desc(), per_customer.c.mention_count.desc())
        )
        mentions_stmt = (
            select(feature_gap_mentions)
            .where(
                *self._mention_conditions(
                    org_id, mention_filter, feature_gap_mentions.c.feature_name == feature_name
                )
            )
            .order_by(feature_gap_mentions.c.occurred_at.desc(), feature_gap_mentions.c.id.desc())
        )

        async with self._engine.connect() as conn:
            score_row = (
                await conn.execute(
                    select(feature_gap_scores).where(
                        feature_gap_scores.c.org_id == org_id,
                        feature_gap_scores.c.feature_name == feature_name,
                    )
                )
            ).mappings().first()
            if score_row is None:
                return None
            affected_rows = (await conn.execute(affected_stmt)).mappings().all()
            mention_rows = (await conn.execute(mentions_stmt)).mappings().all()
            conf = await self._confidence_by_feature(conn, org_id, [feature_name])
            statuses = await self._status_by_name(conn, org_id, TopicKind.FEATURE_GAP, [feature_name])

        return FeatureGapDetail(
            score=_score_from_row(
                score_row, conf=conf.get(feature_name), status=statuses.get(feature_name, TopicStatus.OPEN)
            ),
            affected_customers=[
                AffectedCustomer(
                    external_customer_id=r["external_customer_id"],
                    customer_name=r["customer_name"] or r["external_customer_id"],
                    arr=r["arr"] or 0.0,
                    mrr=r["mrr"] or 0.0,
                    mention_count=r["mention_count"],
                )
                for r in affected_rows
            ],
            mentions=[mention_from_row(m) for m in mention_rows],
        )

    async def search_pain_points(
        self, org_id: str, filters: PainPointFilter, *, limit: int, offset: int
    ) -> tuple[list[PainPointScore], int]:
        # Aggregate scores on the fly from mentions (no separate scores table yet).
        conds = [pain_point_mentions.c.org_id == org_id]
        if filters.query:
            conds.append(
                func.lower(pain_point_mentions.c.topic_name).like(_like_pattern(filters.query), escape="\\")
            )
        if filters.source_connector:
            conds.append(pain_point_mentions.c.source_connector == filters.source_connector)
        if filters.external_customer_id:
            conds.append(pain_point_mentions.c.external_customer_id == filters.external_customer_id)
        if filters.min_confidence is not None:
            conds.append(pain_point_mentions.c.confidence >= filters.min_confidence)
        if filters.status is not None:
            conds.append(
                self._topic_status_condition(pain_point_mentions.c.topic_name, org_id, TopicKind.PAIN_POINT, filters.status)
            )

        grouped = (
            select(
                pain_point_mentions.c.topic_name,
                func.count().label("mention_count"),
                func.count(pain_point_mentions.c.external_customer_id.distinct()).label("customer_count"),
                func.max(pain_point_mentions.c.confidence).label("max_confidence"),
                func.avg(pain_point_mentions.c.confidence).label("avg_confidence"),
                func.sum(
                    case((pain_point_mentions.c.confidence < _LOW_CONFIDENCE, 1), else_=0)
                ).label("low_confidence_count"),
            )
            .where(*conds)
            .group_by(pain_point_mentions.c.topic_name)
            .subquery("pain_scores")
        )
        count_stmt = select(func.count()).select_from(grouped)
        page_stmt = (
            select(grouped)
            .order_by(grouped.c.mention_count.desc(), grouped.c.topic_name)
            .limit(limit)
            .offset(offset)
        )
        async with self._engine.connect() as conn:
            total = (await conn.execute(count_stmt)).scalar_one()
            rows = (await conn.execute(page_stmt)).mappings().all()
            names = [r["topic_name"] for r in rows]
            top = await self._top_customers_by_pain_topic(conn, org_id, names)
            trends = await topic_trends(conn, pain_point_mentions, "topic_name", org_id, names, now=utcnow())
            statuses = await self._status_by_name(conn, org_id, TopicKind.PAIN_POINT, names)
        scores = [
            PainPointScore(
                org_id=org_id,
                topic_name=r["topic_name"],
                customer_count=r["customer_count"],
                mention_count=r["mention_count"],
                max_confidence=float(r["max_confidence"] or 0.0),
                avg_confidence=float(r["avg_confidence"]) if r["avg_confidence"] is not None else None,
                low_confidence_count=int(r["low_confidence_count"] or 0),
                top_customers=top.get(r["topic_name"], []),
                trend=trends.get(r["topic_name"]),
                status=statuses.get(r["topic_name"], TopicStatus.OPEN),
            )
            for r in rows
        ]
        return scores, int(total)

    @staticmethod
    async def _top_customers_by_pain_topic(
        conn: AsyncConnection, org_id: str, names: list[str], limit: int = 5
    ) -> dict[str, list[str]]:
        """One grouped query for the whole page instead of one per topic."""
        out: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for chunk in chunked(names):
            rows = await conn.execute(
                select(
                    pain_point_mentions.c.topic_name,
                    func.coalesce(customers.c.customer_name, pain_point_mentions.c.external_customer_id),
                    func.count(),
                )
                .select_from(
                    pain_point_mentions.outerjoin(
                        customers,
                        and_(
                            customers.c.org_id == org_id,
                            customers.c.external_customer_id == pain_point_mentions.c.external_customer_id,
                        ),
                    )
                )
                .where(pain_point_mentions.c.org_id == org_id, pain_point_mentions.c.topic_name.in_(chunk))
                .group_by(pain_point_mentions.c.topic_name, customers.c.customer_name, pain_point_mentions.c.external_customer_id)
            )
            for topic, name, n in rows:
                out[topic].append((int(n), name))
        return {t: [n for _, n in sorted(v, key=lambda p: (-p[0], p[1]))[:limit]] for t, v in out.items()}

    async def get_pain_point(
        self, org_id: str, topic_name: str, mention_filter: MentionFilter
    ) -> Optional[PainPointDetail]:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(
                        func.count().label("mention_count"),
                        func.count(pain_point_mentions.c.external_customer_id.distinct()).label(
                            "customer_count"
                        ),
                        func.max(pain_point_mentions.c.confidence).label("max_confidence"),
                        func.avg(pain_point_mentions.c.confidence).label("avg_confidence"),
                        func.sum(
                            case(
                                (pain_point_mentions.c.confidence < _LOW_CONFIDENCE, 1),
                                else_=0,
                            )
                        ).label("low_confidence_count"),
                    ).where(
                        pain_point_mentions.c.org_id == org_id,
                        pain_point_mentions.c.topic_name == topic_name,
                    )
                )
            ).mappings().first()
            if not row or not row["mention_count"]:
                return None

            trends = await topic_trends(conn, pain_point_mentions, "topic_name", org_id, [topic_name], now=utcnow())
            statuses = await self._status_by_name(conn, org_id, TopicKind.PAIN_POINT, [topic_name])
            top = await self._top_customers_by_pain_topic(conn, org_id, [topic_name])
            score = PainPointScore(
                org_id=org_id,
                topic_name=topic_name,
                customer_count=row["customer_count"],
                mention_count=row["mention_count"],
                max_confidence=float(row["max_confidence"] or 0.0),
                avg_confidence=float(row["avg_confidence"]) if row["avg_confidence"] is not None else None,
                low_confidence_count=int(row["low_confidence_count"] or 0),
                top_customers=top.get(topic_name, []),
                trend=trends.get(topic_name),
                status=statuses.get(topic_name, TopicStatus.OPEN),
            )
            latest = self._latest_snapshots(org_id)
            per_customer = (
                select(
                    pain_point_mentions.c.external_customer_id,
                    func.count().label("mention_count"),
                )
                .where(
                    pain_point_mentions.c.org_id == org_id,
                    pain_point_mentions.c.topic_name == topic_name,
                )
                .group_by(pain_point_mentions.c.external_customer_id)
                .subquery("pain_per_customer")
            )
            affected_stmt = (
                select(
                    per_customer.c.external_customer_id,
                    per_customer.c.mention_count,
                    customers.c.customer_name,
                    latest.c.arr,
                    latest.c.mrr,
                )
                .select_from(
                    per_customer.outerjoin(
                        customers,
                        and_(
                            customers.c.org_id == org_id,
                            customers.c.external_customer_id == per_customer.c.external_customer_id,
                        ),
                    ).outerjoin(
                        latest, latest.c.external_customer_id == per_customer.c.external_customer_id
                    )
                )
                .order_by(
                    func.coalesce(latest.c.arr, 0.0).desc(),
                    per_customer.c.mention_count.desc(),
                )
            )
            mentions_stmt = (
                select(pain_point_mentions)
                .where(
                    *self._pain_mention_conditions(
                        org_id, mention_filter, pain_point_mentions.c.topic_name == topic_name
                    )
                )
                .order_by(pain_point_mentions.c.occurred_at.desc(), pain_point_mentions.c.id.desc())
            )
            affected_rows = (await conn.execute(affected_stmt)).mappings().all()
            mention_rows = (await conn.execute(mentions_stmt)).mappings().all()

        return PainPointDetail(
            score=score,
            affected_customers=[
                AffectedCustomer(
                    external_customer_id=r["external_customer_id"],
                    customer_name=r["customer_name"] or r["external_customer_id"],
                    arr=r["arr"] or 0.0,
                    mrr=r["mrr"] or 0.0,
                    mention_count=r["mention_count"],
                )
                for r in affected_rows
            ],
            mentions=[pain_mention_from_row(m) for m in mention_rows],
        )

    # ----------------------------------------------------------------- customers

    async def search_customers(
        self, org_id: str, filters: CustomerFilter, *, limit: int, offset: int, top_insights: int = 3
    ) -> tuple[list[CustomerSummary], int]:
        base, latest = self._customer_base_query(org_id, filters)
        count_stmt = select(func.count()).select_from(base.subquery())
        page_stmt = (
            self._select_with_prefixed_snapshot(base, latest)
            .order_by(func.coalesce(latest.c.arr, 0.0).desc(), customers.c.customer_name)
            .limit(limit)
            .offset(offset)
        )
        async with self._engine.connect() as conn:
            total = (await conn.execute(count_stmt)).scalar_one()
            rows = (await conn.execute(page_stmt)).mappings().all()
            summaries = await self._summaries(conn, org_id, rows, top_insights)
        return summaries, int(total)

    async def get_customer(
        self, org_id: str, external_customer_id: str, mention_filter: MentionFilter
    ) -> Optional[CustomerDetail]:
        base, latest = self._customer_base_query(org_id, CustomerFilter())
        row_stmt = self._select_with_prefixed_snapshot(base, latest).where(
            customers.c.external_customer_id == external_customer_id
        )
        mentions_stmt = (
            select(feature_gap_mentions)
            .where(
                *self._mention_conditions(
                    org_id,
                    mention_filter,
                    feature_gap_mentions.c.external_customer_id == external_customer_id,
                )
            )
            .order_by(feature_gap_mentions.c.occurred_at.desc(), feature_gap_mentions.c.id.desc())
        )
        pain_mentions_stmt = (
            select(pain_point_mentions)
            .where(
                *self._pain_mention_conditions(
                    org_id,
                    mention_filter,
                    pain_point_mentions.c.external_customer_id == external_customer_id,
                )
            )
            .order_by(pain_point_mentions.c.occurred_at.desc(), pain_point_mentions.c.id.desc())
        )
        async with self._engine.connect() as conn:
            row = (await conn.execute(row_stmt)).mappings().first()
            if row is None:
                return None
            insights = (await self._insights_by_customer(conn, org_id, [external_customer_id])).get(
                external_customer_id, []
            )
            pain_insights = (
                await self._pain_insights_by_customer(conn, org_id, [external_customer_id])
            ).get(external_customer_id, [])
            mention_rows = (await conn.execute(mentions_stmt)).mappings().all()
            pain_mention_rows = (await conn.execute(pain_mentions_stmt)).mappings().all()
            summary = (await self._summaries(conn, org_id, [row], top_insights=3))[0]

        return CustomerDetail(
            **summary.model_dump(),
            insights=insights,
            pain_point_insights=pain_insights,
            mentions=[mention_from_row(m) for m in mention_rows],
            pain_point_mentions=[pain_mention_from_row(m) for m in pain_mention_rows],
        )

    async def list_source_connectors(self, org_id: str) -> list[str]:
        async with self._engine.connect() as conn:
            fg = (
                await conn.execute(
                    select(feature_gap_mentions.c.source_connector)
                    .where(feature_gap_mentions.c.org_id == org_id)
                    .distinct()
                )
            ).all()
            pp = (
                await conn.execute(
                    select(pain_point_mentions.c.source_connector)
                    .where(pain_point_mentions.c.org_id == org_id)
                    .distinct()
                )
            ).all()
        return sorted({r[0] for r in list(fg) + list(pp) if r[0]})
