"""Pain-point routes for the intelligence portal."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.middlewares.auth import require_scopes
from app.api.routes.intelligence_portal.dependencies import org_id, pagination
from app.api.schemas.intelligence_portal import Page, PainPointDetailResponse, PainPointResponse
from app.config.constants.service import OAuthScopes

if TYPE_CHECKING:
    from app.modules.customer_intelligence.queries.services import (
        PainPointQueryService,
        Pagination,
    )

router = APIRouter(prefix="/pain-points", tags=["intelligence-portal: pain points"])


async def pain_point_service(request: Request) -> "PainPointQueryService":
    return await request.app.container.pain_point_query_service()


@router.get(
    "",
    response_model=Page[PainPointResponse],
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def search_pain_points(
    q: Optional[str] = Query(None, max_length=256),
    source_connector: Optional[str] = Query(None, max_length=64),
    customer_id: Optional[str] = Query(None, max_length=255),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    page: "Pagination" = Depends(pagination),
    org: str = Depends(org_id),
    service: "PainPointQueryService" = Depends(pain_point_service),
) -> Page[PainPointResponse]:
    return await service.search(
        org,
        query=q,
        source_connector=source_connector,
        external_customer_id=customer_id,
        min_confidence=min_confidence,
        pagination=page,
    )


@router.get(
    "/{topic_name:path}",
    response_model=PainPointDetailResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def get_pain_point(
    topic_name: str,
    customer_id: Optional[str] = Query(None, max_length=255),
    source_connector: Optional[str] = Query(None, max_length=64),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    org: str = Depends(org_id),
    service: "PainPointQueryService" = Depends(pain_point_service),
) -> PainPointDetailResponse:
    detail = await service.get(
        org,
        topic_name,
        external_customer_id=customer_id,
        source_connector=source_connector,
        min_confidence=min_confidence,
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pain point not found.")
    return detail
