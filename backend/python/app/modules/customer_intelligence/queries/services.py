"""Query services for the Customer Feature Intelligence portal.

One service per bounded view (overview / feature gaps / customers). Each
depends only on ``IIntelligenceQueryRepository`` and returns API schemas, so
routers stay declarative and the repository stays free of pagination and
presentation concerns.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.api.schemas.intelligence_portal import (
    CustomerDetailResponse,
    CustomerResponse,
    FeatureGapDetailResponse,
    FeatureGapResponse,
    OverviewResponse,
    Page,
    PainPointDetailResponse,
    PainPointResponse,
    SourceConnectorsResponse,
    TopicResponse,
)
from app.models.intelligence import (
    CustomerFilter,
    FeatureGapFilter,
    MentionFilter,
    PainPointFilter,
    TopicGuidanceUpdate,
    TopicKind,
)
from app.modules.customer_intelligence.queries import mappers

if TYPE_CHECKING:
    from app.services.intelligence_store.interface.intelligence_query_repository import (
        IIntelligenceQueryRepository,
    )
    from app.services.intelligence_store.interface.intelligence_store import (
        IIntelligenceStore,
    )

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class Pagination:
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0

    def clamped(self) -> "Pagination":
        return Pagination(limit=max(1, min(self.limit, MAX_PAGE_SIZE)), offset=max(0, self.offset))


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


class OverviewQueryService:
    def __init__(self, repository: IIntelligenceQueryRepository, *, top_n: int = 5) -> None:
        self._repo = repository
        self._top_n = top_n

    async def get_overview(self, org_id: str, *, top_n: Optional[int] = None) -> OverviewResponse:
        n = self._top_n if top_n is None else max(1, min(top_n, 50))
        return mappers.overview_response(await self._repo.get_overview(org_id, top_n=n))

    async def list_source_connectors(self, org_id: str) -> SourceConnectorsResponse:
        return SourceConnectorsResponse(source_connectors=await self._repo.list_source_connectors(org_id))


class FeatureGapQueryService:
    def __init__(self, repository: IIntelligenceQueryRepository) -> None:
        self._repo = repository

    async def search(
        self,
        org_id: str,
        *,
        query: Optional[str] = None,
        min_arr: Optional[float] = None,
        source_connector: Optional[str] = None,
        external_customer_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
        pagination: Pagination = Pagination(),
    ) -> Page[FeatureGapResponse]:
        page = pagination.clamped()
        filters = FeatureGapFilter(
            query=_clean(query),
            min_arr=min_arr,
            source_connector=_clean(source_connector),
            external_customer_id=_clean(external_customer_id),
            min_confidence=min_confidence,
        )
        items, total = await self._repo.search_feature_gaps(org_id, filters, limit=page.limit, offset=page.offset)
        return mappers.page_of(
            [mappers.feature_gap_response(s) for s in items], total, limit=page.limit, offset=page.offset
        )

    async def get(
        self,
        org_id: str,
        feature_name: str,
        *,
        external_customer_id: Optional[str] = None,
        source_connector: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> Optional[FeatureGapDetailResponse]:
        mention_filter = MentionFilter(
            external_customer_id=_clean(external_customer_id),
            source_connector=_clean(source_connector),
            min_confidence=min_confidence,
        )
        detail = await self._repo.get_feature_gap(org_id, feature_name, mention_filter)
        return mappers.feature_gap_detail_response(detail) if detail else None


class PainPointQueryService:
    def __init__(self, repository: IIntelligenceQueryRepository) -> None:
        self._repo = repository

    async def search(
        self,
        org_id: str,
        *,
        query: Optional[str] = None,
        source_connector: Optional[str] = None,
        external_customer_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
        pagination: Pagination = Pagination(),
    ) -> Page[PainPointResponse]:
        page = pagination.clamped()
        filters = PainPointFilter(
            query=_clean(query),
            source_connector=_clean(source_connector),
            external_customer_id=_clean(external_customer_id),
            min_confidence=min_confidence,
        )
        items, total = await self._repo.search_pain_points(
            org_id, filters, limit=page.limit, offset=page.offset
        )
        return mappers.page_of(
            [mappers.pain_point_response(s) for s in items],
            total,
            limit=page.limit,
            offset=page.offset,
        )

    async def get(
        self,
        org_id: str,
        topic_name: str,
        *,
        external_customer_id: Optional[str] = None,
        source_connector: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> Optional[PainPointDetailResponse]:
        mention_filter = MentionFilter(
            external_customer_id=_clean(external_customer_id),
            source_connector=_clean(source_connector),
            min_confidence=min_confidence,
        )
        detail = await self._repo.get_pain_point(org_id, topic_name, mention_filter)
        return mappers.pain_point_detail_response(detail) if detail else None


class TopicService:
    """Read + write taxonomy topics (guidance / aliases / merge)."""

    def __init__(self, store: "IIntelligenceStore") -> None:
        self._store = store

    async def list_topics(
        self, org_id: str, *, kind: Optional[str] = None
    ) -> list[TopicResponse]:
        topic_kind = TopicKind(kind) if kind else None
        topics = await self._store.list_topics(org_id, topic_kind)
        return [mappers.topic_response(t) for t in topics]

    async def get_topic(self, org_id: str, topic_id: int) -> Optional[TopicResponse]:
        topic = await self._store.get_topic(org_id, topic_id)
        return mappers.topic_response(topic) if topic else None

    async def update_topic(
        self,
        org_id: str,
        topic_id: int,
        *,
        guidance: Optional[str] = None,
        aliases: Optional[list[str]] = None,
        canonical_name: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> Optional[TopicResponse]:
        topic = await self._store.update_topic_guidance(
            org_id,
            topic_id,
            TopicGuidanceUpdate(
                guidance=guidance,
                aliases=aliases,
                canonical_name=canonical_name,
                updated_by=updated_by,
            ),
        )
        return mappers.topic_response(topic) if topic else None

    async def merge_topics(
        self, org_id: str, source_id: int, target_id: int
    ) -> Optional[TopicResponse]:
        topic = await self._store.merge_topics(org_id, source_id, target_id)
        return mappers.topic_response(topic) if topic else None


class CustomerQueryService:
    def __init__(self, repository: IIntelligenceQueryRepository, *, top_insights: int = 3) -> None:
        self._repo = repository
        self._top_insights = top_insights

    async def search(
        self,
        org_id: str,
        *,
        query: Optional[str] = None,
        min_arr: Optional[float] = None,
        source_connector: Optional[str] = None,
        pagination: Pagination = Pagination(),
    ) -> Page[CustomerResponse]:
        page = pagination.clamped()
        filters = CustomerFilter(query=_clean(query), min_arr=min_arr, source_connector=_clean(source_connector))
        items, total = await self._repo.search_customers(
            org_id, filters, limit=page.limit, offset=page.offset, top_insights=self._top_insights
        )
        return mappers.page_of(
            [mappers.customer_response(c) for c in items], total, limit=page.limit, offset=page.offset
        )

    async def get(
        self,
        org_id: str,
        external_customer_id: str,
        *,
        source_connector: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> Optional[CustomerDetailResponse]:
        detail = await self._repo.get_customer(
            org_id,
            external_customer_id,
            MentionFilter(
                source_connector=_clean(source_connector),
                min_confidence=min_confidence,
            ),
        )
        return mappers.customer_detail_response(detail) if detail else None
