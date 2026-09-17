"""Overview + filter-option routes for the intelligence portal."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, Query

from app.api.middlewares.auth import require_scopes
from app.api.routes.intelligence_portal.dependencies import org_id, overview_service
from app.api.schemas.intelligence_portal import (
    OverviewResponse,
    SourceConnectorsResponse,
)
from app.config.constants.service import OAuthScopes

if TYPE_CHECKING:
    from app.modules.customer_intelligence.queries.services import OverviewQueryService

router = APIRouter(tags=["intelligence-portal: overview"])


@router.get(
    "/overview",
    response_model=OverviewResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def get_overview(
    org: str = Depends(org_id),
    service: OverviewQueryService = Depends(overview_service),
    top_n: Optional[int] = Query(default=None, ge=1, le=50),
) -> OverviewResponse:
    return await service.get_overview(org, top_n=top_n)


@router.get(
    "/filters/source-connectors",
    response_model=SourceConnectorsResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def list_source_connectors(
    org: str = Depends(org_id),
    service: OverviewQueryService = Depends(overview_service),
) -> SourceConnectorsResponse:
    return await service.list_source_connectors(org)
