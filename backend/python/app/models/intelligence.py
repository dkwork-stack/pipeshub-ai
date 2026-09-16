"""Customer Feature Intelligence domain models.

These models are the common, connector-agnostic contract for the Customer
Feature Intelligence capability: any connector (existing or future) maps its
source-specific payload onto ``CustomerSignalEvent`` / ``CustomerRevenueSnapshot``
and posts it to the intake API (see ``app/api/routes/intelligence.py``). Nothing
downstream of the intake API depends on which connector produced the data.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SignalSourceType(str, Enum):
    """The kind of customer touchpoint a CustomerSignalEvent originated from."""

    SUPPORT_TICKET = "support_ticket"
    CRM_NOTE = "crm_note"
    CALL_TRANSCRIPT = "call_transcript"
    DOCUMENT_UPLOAD = "document_upload"


class CustomerSignalEvent(BaseModel):
    """Normalized unit of customer-facing text from any connector.

    One event == one ticket, one CRM note/case, one call transcript, or one
    uploaded document/row. ``org_id`` scopes every event to a tenant so the
    MySQL intelligence store can be multi-tenant-ready even though the rest of
    the pipeshub fork is not yet.
    """

    org_id: str = Field(..., description="Tenant/organization identifier")
    source_connector: str = Field(..., description="e.g. 'freshdesk', 'salesforce', 'gong', 'file_upload'")
    source_type: SignalSourceType
    external_customer_id: str = Field(..., description="Stable customer identifier in the source system (or CRM account id used as the join key)")
    customer_name: str = Field(..., description="Human-readable customer/account name")
    external_event_id: str = Field(..., description="Ticket id / note id / call id / row id — used for idempotent upsert")
    text: str = Field(..., description="Raw text content to run pain-point/feature-gap inference on")
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    citation_url: Optional[str] = Field(default=None, description="Deep link back to the source record, shown as evidence")
    metadata: dict = Field(default_factory=dict, description="Source-specific extra fields kept for debugging/audit only")


class CustomerRevenueSnapshot(BaseModel):
    """A point-in-time revenue/subscription snapshot for a customer (e.g. from Chargebee)."""

    org_id: str
    source_connector: str = Field(default="chargebee")
    external_customer_id: str
    customer_name: str
    mrr: float = Field(default=0.0, description="Monthly recurring revenue")
    arr: float = Field(default=0.0, description="Annual recurring revenue")
    seats_used: Optional[int] = None
    seats_licensed: Optional[int] = None
    consumed_features: list[str] = Field(default_factory=list)
    renewal_date: Optional[datetime] = None
    snapshot_at: datetime = Field(default_factory=datetime.utcnow)


class PainPoint(BaseModel):
    """A single inferred customer pain point, with evidence."""

    summary: str = Field(..., description="Concise statement of the pain point")
    sentiment: str = Field(default="Neutral", description="Positive | Neutral | Negative")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    excerpt: str = Field(..., description="Verbatim excerpt from the source text supporting this pain point")


class FeatureGapCandidate(BaseModel):
    """A single inferred product feature gap / request, with evidence."""

    feature_name: str = Field(..., description="Normalized, short feature name, e.g. 'Bulk CSV export'")
    description: str = Field(..., description="What the customer is asking for and why")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    excerpt: str = Field(..., description="Verbatim excerpt from the source text supporting this feature gap")


class FeatureIntelligenceExtractionResult(BaseModel):
    """LLM output for a single CustomerSignalEvent: structured, evidence-backed."""

    pain_points: list[PainPoint] = Field(default_factory=list)
    feature_gaps: list[FeatureGapCandidate] = Field(default_factory=list)


class FeatureGapMentionRecord(BaseModel):
    """A stored, citation-carrying link between one customer and one feature gap."""

    org_id: str
    external_customer_id: str
    feature_name: str
    description: str
    confidence: float
    excerpt: str
    source_connector: str
    source_type: SignalSourceType
    external_event_id: str
    citation_url: Optional[str] = None
    occurred_at: datetime


class FeatureGapScore(BaseModel):
    """Revenue-weighted priority score for one feature gap, for CPO/PM consumption."""

    org_id: str
    feature_name: str
    total_arr_at_stake: float
    total_mrr_at_stake: float
    customer_count: int
    mention_count: int
    score: float
    top_customers: list[str] = Field(default_factory=list)
