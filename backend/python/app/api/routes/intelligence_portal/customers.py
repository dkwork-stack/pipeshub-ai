"""Customer routes for the intelligence portal."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.middlewares.auth import require_scopes
from app.api.routes.intelligence_portal.dependencies import (
    actor,
    compliance_service,
    customer_service,
    org_id,
    pagination,
)
from app.api.schemas.intelligence_portal import (
    CustomerDetailResponse,
    CustomerResponse,
    ErasureResponse,
    Page,
)
from app.config.constants.service import OAuthScopes

if TYPE_CHECKING:
    from app.modules.customer_intelligence.queries.services import (
        ComplianceService,
        CustomerQueryService,
        Pagination,
    )

router = APIRouter(prefix="/customers", tags=["intelligence-portal: customers"])


@router.get(
    "",
    response_model=Page[CustomerResponse],
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def search_customers(
    q: Optional[str] = Query(None, max_length=256, description="Substring match on customer name or id"),
    min_arr: Optional[float] = Query(None, ge=0),
    source_connector: Optional[str] = Query(None, max_length=64),
    at_risk: bool = Query(  # noqa: FBT001 - query parameter
        False, description="Only customers with churn-risk or mostly negative evidence"
    ),
    page: Pagination = Depends(pagination),
    org: str = Depends(org_id),
    service: CustomerQueryService = Depends(customer_service),
) -> Page[CustomerResponse]:
    return await service.search(
        org, query=q, min_arr=min_arr, source_connector=source_connector, at_risk=at_risk, pagination=page
    )


@router.delete(
    "/{external_customer_id:path}",
    response_model=ErasureResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_WRITE))],
    summary="GDPR erasure: delete a customer with all its evidence and revenue (audited)",
)
async def erase_customer(
    external_customer_id: str,
    org: str = Depends(org_id),
    who: Optional[str] = Depends(actor),
    service: ComplianceService = Depends(compliance_service),
) -> ErasureResponse:
    result = await service.erase_customer(org, external_customer_id, actor=who)
    if not any(result.model_dump().values()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return result


@router.get(
    "/{external_customer_id:path}",
    response_model=CustomerDetailResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def get_customer(
    external_customer_id: str,
    source_connector: Optional[str] = Query(None, max_length=64),
    org: str = Depends(org_id),
    service: CustomerQueryService = Depends(customer_service),
) -> CustomerDetailResponse:
    detail = await service.get(org, external_customer_id, source_connector=source_connector)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return detail
