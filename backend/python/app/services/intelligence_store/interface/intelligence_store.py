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
    IntelligenceTopic,
    PainPointMentionRecord,
    TopicGuidanceUpdate,
    TopicKind,
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
    async def upsert_pain_point_mention(self, mention: PainPointMentionRecord) -> None:
        """Idempotently record one (customer, pain_point, source event) mention."""
        ...

    @abstractmethod
    async def list_topics(
        self, org_id: str, kind: Optional[TopicKind] = None, *, include_merged: bool = False
    ) -> list[IntelligenceTopic]:
        """List taxonomy topics for an org, optionally filtered by kind."""
        ...

    @abstractmethod
    async def get_topic(self, org_id: str, topic_id: int) -> Optional[IntelligenceTopic]:
        """Return one taxonomy topic, or None if missing / wrong org."""
        ...

    @abstractmethod
    async def upsert_topic(self, topic: IntelligenceTopic) -> IntelligenceTopic:
        """Create or update a taxonomy topic by (org, kind, canonical_name)."""
        ...

    @abstractmethod
    async def update_topic_guidance(
        self, org_id: str, topic_id: int, update_payload: TopicGuidanceUpdate
    ) -> Optional[IntelligenceTopic]:
        """Patch guidance / aliases / canonical_name on an existing topic."""
        ...

    @abstractmethod
    async def merge_topics(self, org_id: str, source_id: int, target_id: int) -> Optional[IntelligenceTopic]:
        """Rewrite mentions from source onto target, then mark source as merged."""
        ...

    @abstractmethod
    async def list_customer_names(self, org_id: str, limit: int = 500) -> list[tuple[str, str]]:
        """Return ``(external_customer_id, customer_name)`` pairs for customer resolution."""
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
