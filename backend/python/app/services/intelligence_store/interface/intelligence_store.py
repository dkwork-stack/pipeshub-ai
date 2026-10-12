"""IIntelligenceStore: abstraction over the Customer Feature Intelligence backing store.

Mirrors the pattern used by ``IGraphDBProvider`` / ``IVectorDBService``
(see AGENTS.md): feature code depends only on this interface, never on a raw
MySQL client. This keeps the store swappable (e.g. Postgres later) without
touching ``app/modules/customer_intelligence`` or the intake API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from datetime import datetime

    from app.models.intelligence import (
        AuditEntry,
        CustomerRevenueSnapshot,
        ErasureResult,
        FeatureGapMentionRecord,
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
    async def upsert_feature_gap_mention(
        self, mention: FeatureGapMentionRecord, *, recompute: bool = True
    ) -> None:
        """Idempotently record one (customer, feature_gap, source event) mention.

        ``recompute=False`` lets a caller writing many mentions recompute the
        touched scores once afterwards.
        """
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
    async def add_topic_alias(self, org_id: str, topic_id: int, alias: str) -> None:
        """Remember another phrasing of a topic (no-op if already known)."""
        ...

    @abstractmethod
    async def get_topic_embeddings(
        self, org_id: str, model: str
    ) -> dict[int, tuple[str, list[float]]]:
        """Cached ``topic_id -> (text_hash, vector)`` for one embedding model."""
        ...

    @abstractmethod
    async def upsert_topic_embedding(
        self, org_id: str, topic_id: int, model: str, text_hash: str, vector: list[float]
    ) -> None:
        """Cache a topic's vector for one embedding model."""
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
    async def list_org_ids(self) -> list[str]:
        """Every org with data (retention jobs iterate these)."""
        ...

    @abstractmethod
    async def record_audit(self, entry: AuditEntry) -> None:
        """Append one privileged action to the audit trail."""
        ...

    @abstractmethod
    async def list_audit(self, org_id: str, limit: int = 50, offset: int = 0) -> tuple[list[AuditEntry], int]:
        """Newest-first audit entries plus the total count."""
        ...

    @abstractmethod
    async def erase_customer(self, org_id: str, external_customer_id: str) -> ErasureResult:
        """GDPR Art. 17: delete a customer with its mentions and revenue; recompute scores."""
        ...

    @abstractmethod
    async def erase_source_record(self, org_id: str, source_record_id: str) -> ErasureResult:
        """Delete every mention derived from one source record; recompute scores."""
        ...

    @abstractmethod
    async def purge_mentions_before(self, org_id: str, cutoff: datetime) -> ErasureResult:
        """Retention: delete evidence older than ``cutoff``; recompute scores."""
        ...
