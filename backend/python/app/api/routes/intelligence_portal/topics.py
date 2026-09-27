"""Taxonomy topic routes for the intelligence portal (guidance / aliases / merge)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.middlewares.auth import require_scopes
from app.api.routes.intelligence_portal.dependencies import org_id
from app.api.schemas.intelligence_portal import (
    TopicMergeRequestBody,
    TopicResponse,
    TopicUpdateRequest,
)
from app.config.constants.service import OAuthScopes

if TYPE_CHECKING:
    from app.modules.customer_intelligence.queries.services import TopicService

router = APIRouter(prefix="/topics", tags=["intelligence-portal: topics"])


async def topic_service(request: Request) -> "TopicService":
    return await request.app.container.topic_service()


@router.get(
    "",
    response_model=list[TopicResponse],
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def list_topics(
    kind: Optional[str] = Query(None, pattern="^(pain_point|feature_gap)$"),
    org: str = Depends(org_id),
    service: TopicService = Depends(topic_service),
) -> list[TopicResponse]:
    return await service.list_topics(org, kind=kind)


@router.get(
    "/{topic_id}",
    response_model=TopicResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_READ))],
)
async def get_topic(
    topic_id: int,
    org: str = Depends(org_id),
    service: TopicService = Depends(topic_service),
) -> TopicResponse:
    topic = await service.get_topic(org, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found.")
    return topic


@router.patch(
    "/{topic_id}",
    response_model=TopicResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_WRITE))],
)
async def update_topic(
    topic_id: int,
    body: TopicUpdateRequest,
    request: Request,
    org: str = Depends(org_id),
    service: TopicService = Depends(topic_service),
) -> TopicResponse:
    user = getattr(request.state, "user", {}) or {}
    updated_by = user.get("userId") or user.get("email")
    topic = await service.update_topic(
        org,
        topic_id,
        guidance=body.guidance,
        aliases=body.aliases,
        canonical_name=body.canonical_name,
        updated_by=updated_by,
    )
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found.")
    return topic


@router.post(
    "/{topic_id}/merge",
    response_model=TopicResponse,
    dependencies=[Depends(require_scopes(OAuthScopes.INTELLIGENCE_WRITE))],
)
async def merge_topic(
    topic_id: int,
    body: TopicMergeRequestBody,
    org: str = Depends(org_id),
    service: TopicService = Depends(topic_service),
) -> TopicResponse:
    try:
        topic = await service.merge_topics(org, topic_id, body.target_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found.")
    return topic
