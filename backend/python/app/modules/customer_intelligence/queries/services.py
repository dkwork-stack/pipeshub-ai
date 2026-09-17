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
    SourceConnectorsResponse,
)
from app.models.intelligence import CustomerFilter, FeatureGapFilter, MentionFilter
from app.modules.customer_intelligence.queries import mappers

if TYPE_CHECKING:
    from app.services.intelligence_store.interface.intelligence_query_repository import (
        IIntelligenceQueryRepository,
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
        pagination: Pagination = Pagination(),
    ) -> Page[FeatureGapResponse]:
        page = pagination.clamped()
        filters = FeatureGapFilter(
            query=_clean(query),
            min_arr=min_arr,
            source_connector=_clean(source_connector),
            external_customer_id=_clean(external_customer_id),
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
    ) -> Optional[FeatureGapDetailResponse]:
        mention_filter = MentionFilter(
            external_customer_id=_clean(external_customer_id),
            source_connector=_clean(source_connector),
        )
        detail = await self._repo.get_feature_gap(org_id, feature_name, mention_filter)
        return mappers.feature_gap_detail_response(detail) if detail else None


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
    ) -> Optional[CustomerDetailResponse]:
        detail = await self._repo.get_customer(
            org_id, external_customer_id, MentionFilter(source_connector=_clean(source_connector))
        )
        return mappers.customer_detail_response(detail) if detail else None
