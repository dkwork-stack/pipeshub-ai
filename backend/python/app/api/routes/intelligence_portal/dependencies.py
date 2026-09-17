"""Shared FastAPI dependencies for the intelligence portal routers.

Org scoping always comes from the verified token on ``request.state.user``
(set by ``authMiddleware``), never from a client-supplied field.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Query, Request, status

from app.modules.customer_intelligence.queries.services import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Pagination,
)

if TYPE_CHECKING:
    from app.modules.customer_intelligence.queries.services import (
        CustomerQueryService,
        FeatureGapQueryService,
        OverviewQueryService,
    )


def org_id(request: Request) -> str:
    user = getattr(request.state, "user", {}) or {}
    value = user.get("orgId")
    if not value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return value


def pagination(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


async def overview_service(request: Request) -> OverviewQueryService:
    return await request.app.container.overview_query_service()


async def feature_gap_service(request: Request) -> FeatureGapQueryService:
    return await request.app.container.feature_gap_query_service()


async def customer_service(request: Request) -> CustomerQueryService:
    return await request.app.container.customer_query_service()
