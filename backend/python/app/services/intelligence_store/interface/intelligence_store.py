"""IIntelligenceStore: abstraction over the Customer Feature Intelligence backing store.

Mirrors the pattern used by ``IGraphDBProvider`` / ``IVectorDBService``
(see AGENTS.md): feature code depends only on this interface, never on a raw
MySQL client. This keeps the store swappable (e.g. Postgres later) without
touching ``app/modules/customer_intelligence`` or the intake API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.intelligence import (
    CustomerRevenueSnapshot,
    FeatureGapMentionRecord,
    FeatureGapScore,
)


class IIntelligenceStore(ABC):
    """Async CRUD + query surface for customers, revenue, and feature-gap intelligence."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish the connection pool / run startup checks."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release the connection pool."""
        ...

    @abstractmethod
    async def upsert_customer(
        self, org_id: str, external_customer_id: str, customer_name: str
    ) -> None:
        """Create or rename a customer record."""
        ...

    @abstractmethod
    async def upsert_revenue_snapshot(self, snapshot: CustomerRevenueSnapshot) -> None:
        """Insert a new revenue snapshot for a customer (append-only history)."""
        ...

    @abstractmethod
    async def upsert_feature_gap_mention(self, mention: FeatureGapMentionRecord) -> None:
        """Idempotently record one (customer, feature_gap, source event) mention."""
        ...

    @abstractmethod
    async def recompute_feature_gap_scores(self, org_id: str, feature_names: Optional[list[str]] = None) -> None:
        """Recompute revenue-weighted scores for the given feature gaps (or all, if None)."""
        ...

    @abstractmethod
    async def list_feature_gap_scores(
        self, org_id: str, limit: int = 50, offset: int = 0
    ) -> list[FeatureGapScore]:
        """List feature gaps ranked by score, descending."""
        ...

    @abstractmethod
    async def get_feature_gap_detail(
        self, org_id: str, feature_name: str
    ) -> tuple[FeatureGapScore | None, list[FeatureGapMentionRecord]]:
        """Return the score plus every citation-carrying mention for one feature gap."""
        ...

    @abstractmethod
    async def get_customer_detail(self, org_id: str, external_customer_id: str) -> dict:
        """Return customer profile: latest revenue snapshot + its feature-gap mentions."""
        ...

    @abstractmethod
    async def list_customers(self, org_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """List customers with their latest revenue snapshot."""
        ...
