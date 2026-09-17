"""Feature-gap routes for the intelligence portal."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.middlewares.auth import require_scopes
from app.api.routes.intelligence_portal.dependencies import (
    feature_gap_service,
    org_id,
    pagination,
)
from app.api.schemas.intelligence_portal import (
    FeatureGapDetailResponse,
    FeatureGapResponse,
    Page,
)
from app.config.constants.service import OAuthScopes

if TYPE_CHECKING:
    from app.modules.customer_intelligence.queries.services import (
        FeatureGapQueryService,
        Pagination,
    )

router = APIRouter(prefix="/feature-gaps", tags=["intelligence-portal: feature gaps"])


@router.get(
    "",
    response_model=Page[FeatureGapResponse],
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def search_feature_gaps(
    q: Optional[str] = Query(None, max_length=256, description="Substring match on feature name"),
    min_arr: Optional[float] = Query(None, ge=0),
    source_connector: Optional[str] = Query(None, max_length=64),
    customer_id: Optional[str] = Query(None, max_length=255, description="external_customer_id"),
    page: Pagination = Depends(pagination),
    org: str = Depends(org_id),
    service: FeatureGapQueryService = Depends(feature_gap_service),
) -> Page[FeatureGapResponse]:
    return await service.search(
        org,
        query=q,
        min_arr=min_arr,
        source_connector=source_connector,
        external_customer_id=customer_id,
        pagination=page,
    )


@router.get(
    "/{feature_name:path}",
    response_model=FeatureGapDetailResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def get_feature_gap(
    feature_name: str,
    customer_id: Optional[str] = Query(None, max_length=255),
    source_connector: Optional[str] = Query(None, max_length=64),
    org: str = Depends(org_id),
    service: FeatureGapQueryService = Depends(feature_gap_service),
) -> FeatureGapDetailResponse:
    detail = await service.get(
        org, feature_name, external_customer_id=customer_id, source_connector=source_connector
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature gap not found.")
    return detail
