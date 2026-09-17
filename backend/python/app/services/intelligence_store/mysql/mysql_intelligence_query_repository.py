"""MySQL implementation of IIntelligenceQueryRepository (read side).

Shares the SQLAlchemy async engine with ``MySQLIntelligenceStore`` (the write
side) but exposes only queries. Every statement filters on ``org_id`` — the
portal must never leak one tenant's customers into another's view.

Designed to stay O(1) round-trips per page: latest revenue is resolved with a
window function and per-customer insights with a single GROUP BY over the
page's customer ids, instead of one query per row.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Select, and_, exists, func, literal, or_, select

from app.models.intelligence import (
    AffectedCustomer,
    CustomerDetail,
    CustomerFilter,
    CustomerInsight,
    CustomerSummary,
    FeatureGapDetail,
    FeatureGapFilter,
    FeatureGapMentionRecord,
    FeatureGapScore,
    IntelligenceOverview,
    MentionFilter,
    RevenueSummary,
)
from app.services.intelligence_store.interface.intelligence_query_repository import (
    IIntelligenceQueryRepository,
)
from app.services.intelligence_store.mysql.schema import (
    customers,
    feature_gap_mentions,
    feature_gap_scores,
    revenue_snapshots,
)

if TYPE_CHECKING:
    from logging import Logger

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
    from sqlalchemy.sql import ColumnElement, Subquery


def _like_pattern(query: str) -> str:
    escaped = query.strip().lower().replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def _score_from_row(r: RowMapping) -> FeatureGapScore:
    return FeatureGapScore(
        org_id=r["org_id"],
        feature_name=r["feature_name"],
        total_arr_at_stake=r["total_arr_at_stake"] or 0.0,
        total_mrr_at_stake=r["total_mrr_at_stake"] or 0.0,
        customer_count=r["customer_count"] or 0,
        mention_count=r["mention_count"] or 0,
        score=r["score"] or 0.0,
        top_customers=r["top_customers"] or [],
    )


def _mention_from_row(m: RowMapping) -> FeatureGapMentionRecord:
    return FeatureGapMentionRecord(
        org_id=m["org_id"],
        external_customer_id=m["external_customer_id"],
        feature_name=m["feature_name"],
        description=m["description"] or "",
        confidence=m["confidence"] if m["confidence"] is not None else 0.5,
        excerpt=m["excerpt"] or "",
        source_connector=m["source_connector"],
        source_type=m["source_type"],
        external_event_id=m["external_event_id"],
        citation_url=m["citation_url"],
        occurred_at=m["occurred_at"],
    )


def _revenue_from_row(r: Optional[RowMapping], prefix: str = "") -> Optional[RevenueSummary]:
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
        return conds

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
                    last_mentioned_at=r["last_mentioned_at"],
                    source_connectors=connectors,
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
        return stmt, latest

    @staticmethod
    def _summaries_from_rows(
        rows: list[RowMapping], insights_by_customer: dict[str, list[CustomerInsight]], top_insights: int
    ) -> list[CustomerSummary]:
        summaries: list[CustomerSummary] = []
        for r in rows:
            insights = insights_by_customer.get(r["external_customer_id"], [])
            summaries.append(
                CustomerSummary(
                    external_customer_id=r["external_customer_id"],
                    customer_name=r["customer_name"],
                    latest_revenue=_revenue_from_row(r, prefix="latest_"),
                    feature_gap_count=len(insights),
                    mention_count=sum(i.mention_count for i in insights),
                    top_insights=insights[:top_insights],
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
            func.max(feature_gap_mentions.c.occurred_at).label("last_mention_at"),
        ).where(feature_gap_mentions.c.org_id == org_id)

        async with self._engine.connect() as conn:
            totals = (await conn.execute(totals_stmt)).mappings().first()
            counts = (await conn.execute(counts_stmt)).mappings().first()
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

        top_customers, _ = await self.search_customers(
            org_id, CustomerFilter(), limit=top_n, offset=0, top_insights=3
        )

        return IntelligenceOverview(
            total_arr_at_stake=float(totals["arr"] or 0.0) if totals else 0.0,
            total_mrr_at_stake=float(totals["mrr"] or 0.0) if totals else 0.0,
            feature_gap_count=counts["feature_gap_count"] if counts else 0,
            customer_count=counts["customer_count"] if counts else 0,
            mention_count=counts["mention_count"] if counts else 0,
            source_connectors=connectors,
            top_feature_gaps=[_score_from_row(r) for r in top_gap_rows],
            top_customers=top_customers,
            last_mention_at=counts["last_mention_at"] if counts else None,
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
        if filters.source_connector or filters.external_customer_id:
            stmt = stmt.where(
                self._mention_exists(
                    org_id,
                    feature_name_col=feature_gap_scores.c.feature_name,
                    source_connector=filters.source_connector,
                    external_customer_id=filters.external_customer_id,
                )
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
        return [_score_from_row(r) for r in rows], int(total)

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

        return FeatureGapDetail(
            score=_score_from_row(score_row),
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
            mentions=[_mention_from_row(m) for m in mention_rows],
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
            insights = await self._insights_by_customer(conn, org_id, [r["external_customer_id"] for r in rows])
        return self._summaries_from_rows(rows, insights, top_insights), int(total)

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
        async with self._engine.connect() as conn:
            row = (await conn.execute(row_stmt)).mappings().first()
            if row is None:
                return None
            insights = (await self._insights_by_customer(conn, org_id, [external_customer_id])).get(
                external_customer_id, []
            )
            mention_rows = (await conn.execute(mentions_stmt)).mappings().all()

        summary = self._summaries_from_rows([row], {external_customer_id: insights}, top_insights=3)[0]
        return CustomerDetail(
            **summary.model_dump(),
            insights=insights,
            mentions=[_mention_from_row(m) for m in mention_rows],
        )

    async def list_source_connectors(self, org_id: str) -> list[str]:
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    select(feature_gap_mentions.c.source_connector)
                    .where(feature_gap_mentions.c.org_id == org_id)
                    .distinct()
                    .order_by(feature_gap_mentions.c.source_connector)
                )
            ).all()
        return [r[0] for r in rows]
