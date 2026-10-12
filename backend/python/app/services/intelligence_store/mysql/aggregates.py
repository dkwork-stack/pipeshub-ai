"""Set-based topic roll-ups (trend, tone/urgency mix) shared by the write and read sides."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import and_, case, func, select

from app.models.intelligence import TopicTrend, Urgency

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection

# Keeps IN (...) lists well under every driver's parameter limit.
CHUNK = 500
TREND_WINDOW = timedelta(days=30)
_HIGH_URGENCY = (Urgency.HIGH.value, Urgency.CRITICAL.value)


def chunked(items: list[str], size: int = CHUNK) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def topic_trends(
    conn: "AsyncConnection",
    table: "Table",
    name_column: str,
    org_id: str,
    names: list[str],
    *,
    now: datetime,
    min_confidence: Optional[float] = None,
) -> dict[str, TopicTrend]:
    """One TopicTrend per topic name, from four grouped queries per chunk."""
    if not names:
        return {}
    name_col = table.c[name_column]
    occurred = table.c.occurred_at
    last_start = now - TREND_WINDOW
    prev_start = now - 2 * TREND_WINDOW

    trends: dict[str, TopicTrend] = {}
    tones: dict[str, dict[str, int]] = defaultdict(dict)
    urgencies: dict[str, dict[str, int]] = defaultdict(dict)
    competitors: dict[str, list[str]] = defaultdict(list)

    for chunk in chunked(names):
        conds = [table.c.org_id == org_id, name_col.in_(chunk)]
        if min_confidence is not None:
            conds.append(table.c.confidence >= min_confidence)

        summary = await conn.execute(
            select(
                name_col.label("name"),
                func.min(occurred).label("first_seen"),
                func.max(occurred).label("last_seen"),
                func.count().label("total"),
                func.sum(case((occurred >= last_start, 1), else_=0)).label("last_30"),
                func.sum(case((and_(occurred >= prev_start, occurred < last_start), 1), else_=0)).label("prev_30"),
                func.sum(case((table.c.sentiment == "Negative", 1), else_=0)).label("negative"),
                func.sum(case((table.c.urgency.in_(_HIGH_URGENCY), 1), else_=0)).label("high_urgency"),
                func.sum(case((table.c.churn_risk.is_(True), 1), else_=0)).label("churn"),
            )
            .where(*conds)
            .group_by(name_col)
        )
        for r in summary.mappings():
            total = int(r["total"] or 0)
            trends[r["name"]] = TopicTrend(
                first_seen_at=r["first_seen"],
                last_seen_at=r["last_seen"],
                mentions_last_30d=int(r["last_30"] or 0),
                mentions_prev_30d=int(r["prev_30"] or 0),
                negative_share=round(int(r["negative"] or 0) / total, 3) if total else 0.0,
                high_urgency_count=int(r["high_urgency"] or 0),
                churn_risk_count=int(r["churn"] or 0),
            )

        for column, sink in ((table.c.tone, tones), (table.c.urgency, urgencies)):
            rows = await conn.execute(
                select(name_col, column, func.count())
                .where(*conds, column.is_not(None))
                .group_by(name_col, column)
            )
            for name, value, count in rows:
                sink[name][value] = int(count)

        rows = await conn.execute(
            select(name_col, table.c.competitor)
            .where(*conds, table.c.competitor.is_not(None))
            .group_by(name_col, table.c.competitor)
        )
        for name, competitor in rows:
            competitors[name].append(competitor)

    for name, trend in trends.items():
        trend.tones = tones.get(name, {})
        trend.urgencies = urgencies.get(name, {})
        trend.competitors = sorted(competitors.get(name, []))[:10]
    return trends
