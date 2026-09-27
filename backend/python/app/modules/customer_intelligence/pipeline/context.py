"""Post-extraction pipeline context for Customer Feature Intelligence."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.intelligence import (
    FeatureIntelligenceExtractionResult,
    IntelligenceTopic,
    TaxonomyHint,
)


class DropReasonCode(str, Enum):
    UNGROUNDED_EXCERPT = "ungrounded_excerpt"
    EMPTY_NAME = "empty_name"
    DUPLICATE_WITHIN_EVENT = "duplicate_within_event"
    GUIDANCE_EXCLUDED = "guidance_excluded"


class DropReason(BaseModel):
    code: DropReasonCode
    kind: str  # pain_point | feature_gap
    name: str
    detail: Optional[str] = None


class ExtractionContext(BaseModel):
    """Mutable bag passed through pipeline stages."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    org_id: str
    text: str
    result: FeatureIntelligenceExtractionResult
    taxonomy: list[IntelligenceTopic] = Field(default_factory=list)
    taxonomy_hints: list[TaxonomyHint] = Field(default_factory=list)
    known_customers: list[tuple[str, str]] = Field(
        default_factory=list,
        description="(external_customer_id, customer_name) pairs already in the store",
    )
    # Populated by ResolveCustomer / CanonicalizeToTopic
    resolved_customer_id: Optional[str] = None
    resolved_customer_name: Optional[str] = None
    dropped: list[DropReason] = Field(default_factory=list)
