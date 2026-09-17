"""IIntelligenceQueryRepository: read-only query surface for the intelligence portal.

Segregated from ``IIntelligenceStore`` (the write/ingestion side) so the portal
service (``app.intelligence_main``) depends only on what it needs and can never
mutate data. Same pluggable-store contract as the rest of the platform: feature
code depends on this interface, ``IntelligenceStoreFactory`` picks the backend.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.intelligence import (
        CustomerDetail,
        CustomerFilter,
        CustomerSummary,
        FeatureGapDetail,
        FeatureGapFilter,
        FeatureGapScore,
        IntelligenceOverview,
        MentionFilter,
    )


class IIntelligenceQueryRepository(ABC):
    """Read-only, org-scoped queries over customers, feature gaps and evidence."""

    @abstractmethod
    async def get_overview(self, org_id: str, *, top_n: int = 5) -> IntelligenceOverview:
        """Org-level roll-up: totals, top gaps, top customers."""
        ...

    @abstractmethod
    async def search_feature_gaps(
        self, org_id: str, filters: FeatureGapFilter, *, limit: int, offset: int
    ) -> tuple[list[FeatureGapScore], int]:
        """Ranked feature gaps matching ``filters`` plus the total match count."""
        ...

    @abstractmethod
    async def get_feature_gap(
        self, org_id: str, feature_name: str, mention_filter: MentionFilter
    ) -> Optional[FeatureGapDetail]:
        """One feature gap with affected customers and (filtered) citations; None if unknown."""
        ...

    @abstractmethod
    async def search_customers(
        self, org_id: str, filters: CustomerFilter, *, limit: int, offset: int, top_insights: int = 3
    ) -> tuple[list[CustomerSummary], int]:
        """Customers matching ``filters`` with latest revenue and top insights, plus total count."""
        ...

    @abstractmethod
    async def get_customer(
        self, org_id: str, external_customer_id: str, mention_filter: MentionFilter
    ) -> Optional[CustomerDetail]:
        """One customer with all insights and (filtered) citations; None if unknown."""
        ...

    @abstractmethod
    async def list_source_connectors(self, org_id: str) -> list[str]:
        """Distinct connectors that produced at least one mention for this org."""
        ...
