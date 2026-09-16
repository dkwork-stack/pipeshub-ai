"""Customer Feature Intelligence API.

Mounted on the indexing service (where the MySQL intelligence store lives).

Write side (``/events``, ``/revenue-snapshots``) is the connector-agnostic
intake surface: any connector adapter — existing or future — maps its data
onto ``CustomerSignalEvent`` / ``CustomerRevenueSnapshot`` and posts here.

Read side (``/feature-gaps``, ``/customers``) is what the future standalone
UI/service consumes.

Every route is scoped to the caller's ``orgId`` from the verified access
token (``request.state.user``), never a client-supplied body/query field —
see AGENTS.md "never trust client-supplied org/user IDs".
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.middlewares.auth import require_scopes
from app.config.constants.service import OAuthScopes
from app.models.intelligence import CustomerRevenueSnapshot, CustomerSignalEvent

if TYPE_CHECKING:
    from app.modules.customer_intelligence.ingestion_service import (
        CustomerIntelligenceIngestionService,
    )
    from app.services.intelligence_store.interface.intelligence_store import (
        IIntelligenceStore,
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


async def _get_intelligence_store(request: Request) -> "IIntelligenceStore":
    return await request.app.container.intelligence_store()


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
    except Exception as exc:
        logger.exception("Failed to ingest revenue snapshot for org '%s'", org_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": str(exc)},
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content={"success": True})


# ---------------------------------------------------------------------------
# Read — for the future standalone UI/service
# ---------------------------------------------------------------------------


@router.get(
    "/feature-gaps",
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
    summary="List feature gaps ranked by revenue-weighted score",
)
async def list_feature_gaps(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    org_id = _org_id(request)
    store = await _get_intelligence_store(request)
    scores = await store.list_feature_gap_scores(org_id, limit=limit, offset=offset)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "feature_gaps": [s.model_dump() for s in scores]},
    )


@router.get(
    "/feature-gaps/{feature_name}",
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
    summary="Feature gap detail: score plus every citation-carrying mention",
)
async def get_feature_gap_detail(request: Request, feature_name: str) -> JSONResponse:
    org_id = _org_id(request)
    store = await _get_intelligence_store(request)
    score, mentions = await store.get_feature_gap_detail(org_id, feature_name)
    if score is None:
        raise HTTPException(status_code=404, detail=f"Feature gap '{feature_name}' not found")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "score": score.model_dump(),
            "mentions": jsonable_encoder([m.model_dump(mode="json") for m in mentions]),
        },
    )


@router.get(
    "/customers",
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
    summary="List customers with their latest revenue snapshot",
)
async def list_customers(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    org_id = _org_id(request)
    store = await _get_intelligence_store(request)
    customers: list[dict[str, Any]] = await store.list_customers(org_id, limit=limit, offset=offset)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder({"success": True, "customers": customers}))


@router.get(
    "/customers/{external_customer_id}",
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
    summary="Customer detail: latest revenue snapshot plus its feature-gap mentions",
)
async def get_customer_detail(request: Request, external_customer_id: str) -> JSONResponse:
    org_id = _org_id(request)
    store = await _get_intelligence_store(request)
    detail = await store.get_customer_detail(org_id, external_customer_id)
    if detail.get("customer") is None:
        raise HTTPException(status_code=404, detail=f"Customer '{external_customer_id}' not found")
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder({"success": True, **detail}))
