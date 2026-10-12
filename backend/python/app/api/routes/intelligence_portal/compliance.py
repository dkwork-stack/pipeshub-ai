"""Compliance routes: audit trail and erasure of everything derived from one source record.

Customer erasure lives on ``DELETE /customers/{id}``. Both require
``intelligence:write`` and are written to the audit log.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends

from app.api.middlewares.auth import require_scopes
from app.api.routes.intelligence_portal.dependencies import (
    actor,
    compliance_service,
    org_id,
    pagination,
)
from app.api.schemas.intelligence_portal import (
    AuditEntryResponse,
    ErasureResponse,
    Page,
)
from app.config.constants.service import OAuthScopes

if TYPE_CHECKING:
    from app.modules.customer_intelligence.queries.services import (
        ComplianceService,
        Pagination,
    )

router = APIRouter(tags=["intelligence-portal: compliance"])


@router.get(
    "/audit",
    response_model=Page[AuditEntryResponse],
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_WRITE))],
)
async def audit_log(
    page: Pagination = Depends(pagination),
    org: str = Depends(org_id),
    service: ComplianceService = Depends(compliance_service),
) -> Page[AuditEntryResponse]:
    return await service.audit_log(org, page)


@router.delete(
    "/records/{record_id}",
    response_model=ErasureResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_WRITE))],
    summary="Erase every mention derived from one source record (e.g. a deleted ticket or upload)",
)
async def erase_source_record(
    record_id: str,
    org: str = Depends(org_id),
    who: Optional[str] = Depends(actor),
    service: ComplianceService = Depends(compliance_service),
) -> ErasureResponse:
    return await service.erase_source_record(org, record_id, actor=who)
