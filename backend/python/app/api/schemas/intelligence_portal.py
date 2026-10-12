"""Response schemas for the Customer Feature Intelligence portal API.

These are the wire contract consumed by the portal UI (and any AI agent). They
are deliberately separate from the domain read models in
``app/models/intelligence.py`` so the storage shape can evolve without
breaking clients — the query services do the mapping.
"""
from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

from app.models.intelligence import TopicStatus

T = TypeVar("T")


class PageMeta(BaseModel):
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    has_more: bool


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: PageMeta


class RevenueResponse(BaseModel):
    source_connector: str
    mrr: float
    arr: float
    seats_used: Optional[int] = None
    seats_licensed: Optional[int] = None
    consumed_features: list[str] = Field(default_factory=list)
    renewal_date: Optional[datetime] = None
    snapshot_at: datetime


class TrendResponse(BaseModel):
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    mentions_last_30d: int = 0
    mentions_prev_30d: int = 0
    negative_share: float = 0.0
    high_urgency_count: int = 0
    churn_risk_count: int = 0
    competitors: list[str] = Field(default_factory=list)
    tones: dict[str, int] = Field(default_factory=dict)
    urgencies: dict[str, int] = Field(default_factory=dict)


class EvidenceAttributes(BaseModel):
    """What the customer said beyond the quote: tone, urgency, impact, provenance."""

    sentiment: str = "Neutral"
    tone: str = "neutral"
    urgency: str = "medium"
    intent: str = "other"
    speaker_role: str = "customer"
    product_area: Optional[str] = None
    business_impact: Optional[str] = None
    workaround: Optional[str] = None
    competitor: Optional[str] = None
    churn_risk: bool = False
    source_record_id: Optional[str] = None
    extraction_model: Optional[str] = None
    prompt_version: Optional[str] = None


class CustomerHealthResponse(BaseModel):
    negative_share: float = 0.0
    churn_risk_count: int = 0
    high_urgency_count: int = 0
    last_touch_at: Optional[datetime] = None
    competitors: list[str] = Field(default_factory=list)
    at_risk: bool = False


class InsightResponse(BaseModel):
    feature_name: str
    mention_count: int
    max_confidence: float
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    last_mentioned_at: datetime
    source_connectors: list[str] = Field(default_factory=list)


class PainPointInsightResponse(BaseModel):
    topic_name: str
    mention_count: int
    max_confidence: float
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    last_mentioned_at: datetime
    source_connectors: list[str] = Field(default_factory=list)
    sentiments: list[str] = Field(default_factory=list)


class MentionResponse(EvidenceAttributes):
    """One piece of evidence: what the customer said, where, and a deep link."""

    external_customer_id: str
    feature_name: str
    description: str
    confidence: float
    excerpt: str
    source_connector: str
    source_type: str
    external_event_id: str
    citation_url: Optional[str] = None
    occurred_at: datetime


class PainPointMentionResponse(EvidenceAttributes):
    external_customer_id: str
    topic_name: str
    summary: str
    confidence: float
    excerpt: str
    source_connector: str
    source_type: str
    external_event_id: str
    citation_url: Optional[str] = None
    occurred_at: datetime


class FeatureGapResponse(BaseModel):
    feature_name: str
    total_arr_at_stake: float
    total_mrr_at_stake: float
    customer_count: int
    mention_count: int
    score: float
    top_customers: list[str] = Field(default_factory=list)
    max_confidence: Optional[float] = None
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    status: str = "open"
    trend: Optional[TrendResponse] = None


class AffectedCustomerResponse(BaseModel):
    external_customer_id: str
    customer_name: str
    arr: float
    mrr: float
    mention_count: int


class FeatureGapDetailResponse(FeatureGapResponse):
    affected_customers: list[AffectedCustomerResponse] = Field(default_factory=list)
    mentions: list[MentionResponse] = Field(default_factory=list)


class PainPointResponse(BaseModel):
    topic_name: str
    customer_count: int
    mention_count: int
    max_confidence: float
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    top_customers: list[str] = Field(default_factory=list)
    status: str = "open"
    trend: Optional[TrendResponse] = None


class PainPointDetailResponse(PainPointResponse):
    affected_customers: list[AffectedCustomerResponse] = Field(default_factory=list)
    mentions: list[PainPointMentionResponse] = Field(default_factory=list)


class CustomerResponse(BaseModel):
    external_customer_id: str
    customer_name: str
    latest_revenue: Optional[RevenueResponse] = None
    feature_gap_count: int
    pain_point_count: int = 0
    mention_count: int
    top_insights: list[InsightResponse] = Field(default_factory=list)
    health: Optional[CustomerHealthResponse] = None


class CustomerDetailResponse(CustomerResponse):
    insights: list[InsightResponse] = Field(default_factory=list)
    pain_point_insights: list[PainPointInsightResponse] = Field(default_factory=list)
    mentions: list[MentionResponse] = Field(default_factory=list)
    pain_point_mentions: list[PainPointMentionResponse] = Field(default_factory=list)


class TopicResponse(BaseModel):
    id: int
    kind: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    guidance: Optional[str] = None
    description: Optional[str] = None
    status: str = "open"
    merged_into_id: Optional[int] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TopicUpdateRequest(BaseModel):
    guidance: Optional[str] = Field(default=None, max_length=4000)
    aliases: Optional[list[str]] = Field(default=None, max_length=100)
    canonical_name: Optional[str] = Field(default=None, min_length=1, max_length=191)
    status: Optional[TopicStatus] = None


class TopicMergeRequestBody(BaseModel):
    target_id: int


class OverviewResponse(BaseModel):
    total_arr_at_stake: float
    total_mrr_at_stake: float
    feature_gap_count: int
    customer_count: int
    mention_count: int
    source_connectors: list[str] = Field(default_factory=list)
    top_feature_gaps: list[FeatureGapResponse] = Field(default_factory=list)
    top_customers: list[CustomerResponse] = Field(default_factory=list)
    last_mention_at: Optional[datetime] = None
    pain_point_count: int = 0
    emerging_feature_gaps: list[FeatureGapResponse] = Field(default_factory=list)
    at_risk_customers: list[CustomerResponse] = Field(default_factory=list)
    intent_mix: dict[str, int] = Field(default_factory=dict)
    tone_mix: dict[str, int] = Field(default_factory=dict)


class SourceConnectorsResponse(BaseModel):
    source_connectors: list[str] = Field(default_factory=list)


class ErasureResponse(BaseModel):
    """Rows removed by a GDPR erasure request (also written to the audit log)."""

    customers: int = 0
    feature_gap_mentions: int = 0
    pain_point_mentions: int = 0
    revenue_snapshots: int = 0


class AuditEntryResponse(BaseModel):
    actor: Optional[str] = None
    action: str
    target_type: str
    target_id: str
    details: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
