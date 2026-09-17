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


class InsightResponse(BaseModel):
    feature_name: str
    mention_count: int
    max_confidence: float
    last_mentioned_at: datetime
    source_connectors: list[str] = Field(default_factory=list)


class MentionResponse(BaseModel):
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


class FeatureGapResponse(BaseModel):
    feature_name: str
    total_arr_at_stake: float
    total_mrr_at_stake: float
    customer_count: int
    mention_count: int
    score: float
    top_customers: list[str] = Field(default_factory=list)


class AffectedCustomerResponse(BaseModel):
    external_customer_id: str
    customer_name: str
    arr: float
    mrr: float
    mention_count: int


class FeatureGapDetailResponse(FeatureGapResponse):
    affected_customers: list[AffectedCustomerResponse] = Field(default_factory=list)
    mentions: list[MentionResponse] = Field(default_factory=list)


class CustomerResponse(BaseModel):
    external_customer_id: str
    customer_name: str
    latest_revenue: Optional[RevenueResponse] = None
    feature_gap_count: int
    mention_count: int
    top_insights: list[InsightResponse] = Field(default_factory=list)


class CustomerDetailResponse(CustomerResponse):
    insights: list[InsightResponse] = Field(default_factory=list)
    mentions: list[MentionResponse] = Field(default_factory=list)


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


class SourceConnectorsResponse(BaseModel):
    source_connectors: list[str] = Field(default_factory=list)
