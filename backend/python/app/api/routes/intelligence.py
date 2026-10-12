"""Customer Feature Intelligence API.

Mounted on the indexing service (where the MySQL intelligence store lives).

The connector-agnostic intake surface: any adapter — existing or future —
maps its data onto ``CustomerSignalEvent`` (optionally with conversation
``turns``) / ``CustomerRevenueSnapshot`` and posts here. Reads are served by
the intelligence portal service (``app.intelligence_main``) only.

Every route is scoped to the caller's ``orgId`` from the verified access
token (``request.state.user``), never a client-supplied body/query field —
see AGENTS.md "never trust client-supplied org/user IDs".
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.middlewares.auth import require_scopes
from app.config.constants.service import OAuthScopes
from app.models.intelligence import CustomerRevenueSnapshot, CustomerSignalEvent

if TYPE_CHECKING:
    from app.modules.customer_intelligence.ingestion_service import (
        CustomerIntelligenceIngestionService,
    )

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/intelligence", tags=["customer-feature-intelligence"])


def _org_id(request: Request) -> str:
    user = getattr(request.state, "user", {}) or {}
    org_id = user.get("orgId")
    if not org_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return org_id


async def _get_ingestion_service(request: Request) -> "CustomerIntelligenceIngestionService":
    return await request.app.container.customer_intelligence_ingestion_service()


# ---------------------------------------------------------------------------
# Intake (write) — connector-agnostic
# ---------------------------------------------------------------------------


@router.post(
    "/events",
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_WRITE))],
    summary="Ingest one customer-signal event (ticket, CRM note, call transcript, doc)",
)
async def ingest_event(request: Request, body: CustomerSignalEvent) -> JSONResponse:
    org_id = _org_id(request)
    if body.org_id != org_id:
        raise HTTPException(status_code=403, detail="org_id does not match authenticated caller")

    ingestion_service = await _get_ingestion_service(request)
    try:
        mentions_written = await ingestion_service.ingest_signal_event(body)
    except Exception as exc:
        logger.exception("Failed to ingest customer signal event for org '%s'", org_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": str(exc)},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "feature_gap_mentions_written": mentions_written},
    )


@router.post(
    "/revenue-snapshots",
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_WRITE))],
    summary="Ingest one customer revenue/subscription snapshot (e.g. from Chargebee)",
)
async def ingest_revenue_snapshot(request: Request, body: CustomerRevenueSnapshot) -> JSONResponse:
    org_id = _org_id(request)
    if body.org_id != org_id:
        raise HTTPException(status_code=403, detail="org_id does not match authenticated caller")

    ingestion_service = await _get_ingestion_service(request)
    try:
        await ingestion_service.ingest_revenue_snapshot(body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to ingest revenue snapshot for org '%s'", org_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": str(exc)},
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content={"success": True})
