"""Customer Feature Intelligence domain models.

These models are the common, connector-agnostic contract for the Customer
Feature Intelligence capability: any connector (existing or future) maps its
source-specific payload onto ``CustomerSignalEvent`` / ``CustomerRevenueSnapshot``
and posts it to the intake API (see ``app/api/routes/intelligence.py``). Nothing
downstream of the intake API depends on which connector produced the data.
"""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema


class SignalSourceType(str, Enum):
    """The kind of customer touchpoint a CustomerSignalEvent originated from."""

    SUPPORT_TICKET = "support_ticket"
    CRM_NOTE = "crm_note"
    CALL_TRANSCRIPT = "call_transcript"
    DOCUMENT_UPLOAD = "document_upload"
    EMAIL = "email"
    CHAT = "chat"


class SpeakerRole(str, Enum):
    """Who said a piece of text in a conversation (ticket thread, call)."""

    CUSTOMER = "customer"
    AGENT = "agent"
    UNKNOWN = "unknown"


class Tone(str, Enum):
    FRUSTRATED = "frustrated"
    ANGRY = "angry"
    ANXIOUS = "anxious"
    NEUTRAL = "neutral"
    APPRECIATIVE = "appreciative"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AskIntent(str, Enum):
    FEATURE_REQUEST = "feature_request"
    BUG = "bug"
    USABILITY = "usability"
    PERFORMANCE = "performance"
    INTEGRATION = "integration"
    PRICING = "pricing"
    COMPLIANCE_SECURITY = "compliance_security"
    OTHER = "other"


class TopicStatus(str, Enum):
    """Product lifecycle of a feature-gap / pain-point topic, set by PMs."""

    OPEN = "open"
    UNDER_REVIEW = "under_review"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    SHIPPED = "shipped"
    DECLINED = "declined"


_SENTIMENTS = {"positive": "Positive", "neutral": "Neutral", "negative": "Negative"}


def _coerce_enum(enum_cls: type[Enum], value: Any, default: Enum) -> Enum:  # noqa: ANN401
    """LLM output drifts ("High", "very urgent", "feature-request"); never fail a whole extraction over it."""
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    key = re.sub(r"[^a-z]+", "_", str(value).strip().lower()).strip("_")
    for member in enum_cls:
        if key == member.value or key == member.name.lower():
            return member
    for member in enum_cls:
        if member.value in key:
            return member
    return default


def normalize_sentiment(value: Any) -> str:  # noqa: ANN401
    return _SENTIMENTS.get(str(value or "").strip().lower(), "Neutral")


class SignalAttributes(BaseModel):
    """Qualitative attributes inferred for one pain point / ask; stored on every mention."""

    sentiment: str = Field(default="Neutral", description="Positive | Neutral | Negative")
    tone: Tone = Field(default=Tone.NEUTRAL)
    urgency: Urgency = Field(default=Urgency.MEDIUM)
    intent: AskIntent = Field(default=AskIntent.FEATURE_REQUEST)
    speaker_role: SpeakerRole = Field(default=SpeakerRole.CUSTOMER)
    product_area: Optional[str] = Field(default=None, description="Product area the item concerns, e.g. 'Reporting'")
    business_impact: Optional[str] = Field(default=None, description="Stated consequence, e.g. 'blocking rollout to 300 seats'")
    workaround: Optional[str] = Field(default=None, description="How the customer copes today, if stated")
    competitor: Optional[str] = Field(default=None, description="Competitor named in connection with this item")
    churn_risk: bool = Field(default=False, description="Customer signals cancellation / non-renewal over this item")

    @field_validator("sentiment", mode="before")
    @classmethod
    def _sentiment(cls, v: Any) -> str:  # noqa: ANN401
        return normalize_sentiment(v)

    @field_validator("tone", mode="before")
    @classmethod
    def _tone(cls, v: Any) -> Tone:  # noqa: ANN401
        return _coerce_enum(Tone, v, Tone.NEUTRAL)

    @field_validator("urgency", mode="before")
    @classmethod
    def _urgency(cls, v: Any) -> Urgency:  # noqa: ANN401
        return _coerce_enum(Urgency, v, Urgency.MEDIUM)

    @field_validator("intent", mode="before")
    @classmethod
    def _intent(cls, v: Any) -> AskIntent:  # noqa: ANN401
        return _coerce_enum(AskIntent, v, AskIntent.OTHER)

    @field_validator("speaker_role", mode="before")
    @classmethod
    def _speaker(cls, v: Any) -> SpeakerRole:  # noqa: ANN401
        return _coerce_enum(SpeakerRole, v, SpeakerRole.UNKNOWN)

    @field_validator("product_area", "business_impact", "workaround", "competitor", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Optional[str]:  # noqa: ANN401
        if v is None:
            return None
        text = str(v).strip()
        return None if text.lower() in {"", "none", "null", "n/a", "na", "unknown"} else text[:1000]

    def attributes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in SignalAttributes.model_fields}


class ConversationTurn(BaseModel):
    """One message in a thread or one speaker segment of a transcript."""

    role: SpeakerRole = SpeakerRole.UNKNOWN
    author: Optional[str] = None
    text: str
    at: Optional[datetime] = None

    def render(self) -> str:
        label = self.role.value.capitalize()
        return f"[{label} · {self.author}]: {self.text}" if self.author else f"[{label}]: {self.text}"


def render_turns(turns: list[ConversationTurn]) -> str:
    """Single-speaker sources (rows, documents) render as plain text, threads as labelled turns."""
    if len(turns) == 1 and turns[0].role == SpeakerRole.UNKNOWN and not turns[0].author:
        return turns[0].text
    return "\n\n".join(t.render() for t in turns if t.text.strip())


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
    text: str = Field(default="", description="Raw text content to run pain-point/feature-gap inference on; rendered from ``turns`` when empty")
    turns: list[ConversationTurn] = Field(
        default_factory=list,
        description="Optional conversation structure (ticket replies, call segments) so asks are attributed to the customer, not the agent",
    )
    source_record_id: Optional[str] = Field(default=None, description="PipesHub record id the event was derived from; lineage + erasure key")
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    citation_url: Optional[str] = Field(default=None, description="Deep link back to the source record, shown as evidence")
    metadata: dict = Field(default_factory=dict, description="Source-specific extra fields kept for debugging/audit only")

    @model_validator(mode="after")
    def _text_from_turns(self) -> "CustomerSignalEvent":
        if not self.text.strip() and self.turns:
            self.text = render_turns(self.turns)
        if not self.text.strip():
            raise ValueError("CustomerSignalEvent needs non-empty text or turns")
        return self


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


class TopicKind(str, Enum):
    """Discriminates pain-point vs feature-gap topics in the org taxonomy."""

    PAIN_POINT = "pain_point"
    FEATURE_GAP = "feature_gap"


class PainPoint(SignalAttributes):
    """A single inferred customer pain point, with evidence."""

    summary: str = Field(..., description="Concise statement of the pain point")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    excerpt: str = Field(..., description="Verbatim excerpt from the source text supporting this pain point")
    topic_id: Optional[str] = Field(
        default=None,
        description="Id of a known taxonomy topic when the item matches one; null for a new proposal",
    )


class FeatureGapCandidate(SignalAttributes):
    """A single inferred product feature gap / request, with evidence."""

    feature_name: str = Field(..., description="Normalized, short feature name, e.g. 'Bulk CSV export'")
    description: str = Field(..., description="What the customer is asking for and why")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    excerpt: str = Field(..., description="Verbatim excerpt from the source text supporting this feature gap")
    topic_id: Optional[str] = Field(
        default=None,
        description="Id of a known taxonomy topic when the item matches one; null for a new proposal",
    )


class TaxonomyHint(BaseModel):
    """Compact topic hint injected into the extraction prompt."""

    id: str
    kind: TopicKind
    name: str
    aliases: list[str] = Field(default_factory=list)
    guidance: Optional[str] = None


class FeatureIntelligenceExtractionResult(BaseModel):
    """LLM output for a single CustomerSignalEvent: structured, evidence-backed."""

    pain_points: list[PainPoint] = Field(default_factory=list)
    feature_gaps: list[FeatureGapCandidate] = Field(default_factory=list)
    customer_name: Optional[str] = Field(
        default=None,
        description="Customer/account the text is about, inferred only when the caller asked for it (uploads have no customer attached)",
    )
    # Provenance, set by the extractor — hidden from the LLM's output schema.
    model: SkipJsonSchema[Optional[str]] = None
    prompt_version: SkipJsonSchema[Optional[str]] = None


class MentionProvenance(BaseModel):
    """Lineage carried by every stored mention (reproducibility, erasure, model audits)."""

    source_record_id: Optional[str] = None
    topic_id: Optional[int] = None
    extraction_model: Optional[str] = None
    prompt_version: Optional[str] = None


class FeatureGapMentionRecord(SignalAttributes, MentionProvenance):
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


class PainPointMentionRecord(SignalAttributes, MentionProvenance):
    """A stored, citation-carrying link between one customer and one pain point."""

    org_id: str
    external_customer_id: str
    topic_name: str
    summary: str
    confidence: float
    excerpt: str
    source_connector: str
    source_type: SignalSourceType
    external_event_id: str
    citation_url: Optional[str] = None
    occurred_at: datetime


class IntelligenceTopic(BaseModel):
    """Org-scoped taxonomy entry for a pain point or feature gap."""

    id: Optional[int] = None
    org_id: str
    kind: TopicKind
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    guidance: Optional[str] = None
    description: Optional[str] = None
    status: TopicStatus = TopicStatus.OPEN
    merged_into_id: Optional[int] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TopicGuidanceUpdate(BaseModel):
    """Partial update for a topic's guidance and aliases."""

    guidance: Optional[str] = None
    aliases: Optional[list[str]] = None
    canonical_name: Optional[str] = None
    status: Optional[TopicStatus] = None
    updated_by: Optional[str] = None


class TopicMergeRequest(BaseModel):
    """Merge ``source`` topic into ``target`` (target keeps the canonical name)."""

    target_id: int


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
    max_confidence: Optional[float] = None
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    trend: Optional["TopicTrend"] = None
    status: TopicStatus = TopicStatus.OPEN


class TopicTrend(BaseModel):
    """Recency + qualitative mix for one topic, computed from its mentions."""

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


class AuditEntry(BaseModel):
    """Append-only record of a privileged action (SOC 2 CC7.2 / GDPR Art. 30)."""

    org_id: str
    actor: Optional[str] = None
    action: str
    target_type: str
    target_id: str
    details: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class ErasureResult(BaseModel):
    """Rows removed by a right-to-erasure or retention request."""

    customers: int = 0
    feature_gap_mentions: int = 0
    pain_point_mentions: int = 0
    revenue_snapshots: int = 0


# ---------------------------------------------------------------------------
# Read models — consumed by the intelligence portal service (app.intelligence_main)
# through IIntelligenceQueryRepository. Kept connector-agnostic like the write
# models above.
# ---------------------------------------------------------------------------


class FeatureGapFilter(BaseModel):
    """Filter/search criteria for feature-gap listings."""

    query: Optional[str] = Field(default=None, description="Case-insensitive substring match on feature name")
    min_arr: Optional[float] = Field(default=None, ge=0, description="Only gaps with at least this much ARR at stake")
    source_connector: Optional[str] = Field(default=None, description="Only gaps with a mention from this connector")
    external_customer_id: Optional[str] = Field(default=None, description="Only gaps mentioned by this customer")
    min_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Only gaps/mentions with at least this confidence"
    )
    status: Optional[TopicStatus] = Field(default=None, description="Only gaps in this lifecycle status")
    intent: Optional[AskIntent] = Field(default=None, description="Only gaps with a mention of this intent")


class PainPointFilter(BaseModel):
    """Filter/search criteria for pain-point listings."""

    query: Optional[str] = Field(default=None, description="Case-insensitive substring match on topic name")
    source_connector: Optional[str] = Field(default=None)
    external_customer_id: Optional[str] = Field(default=None)
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Optional[TopicStatus] = Field(default=None)


class CustomerFilter(BaseModel):
    """Filter/search criteria for customer listings."""

    query: Optional[str] = Field(default=None, description="Case-insensitive substring match on customer name / id")
    min_arr: Optional[float] = Field(default=None, ge=0, description="Only customers whose latest ARR is at least this")
    source_connector: Optional[str] = Field(default=None, description="Only customers with a mention from this connector")
    at_risk: bool = Field(default=False, description="Only customers with churn-risk mentions or mostly negative sentiment")


class MentionFilter(BaseModel):
    """Narrows the citation list on detail views."""

    external_customer_id: Optional[str] = None
    source_connector: Optional[str] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RevenueSummary(BaseModel):
    """Latest revenue snapshot for one customer, flattened for read APIs."""

    source_connector: str
    mrr: float = 0.0
    arr: float = 0.0
    seats_used: Optional[int] = None
    seats_licensed: Optional[int] = None
    consumed_features: list[str] = Field(default_factory=list)
    renewal_date: Optional[datetime] = None
    snapshot_at: datetime


class CustomerInsight(BaseModel):
    """One feature gap as seen from a single customer (aggregated over its mentions)."""

    feature_name: str
    mention_count: int
    max_confidence: float
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    last_mentioned_at: datetime
    source_connectors: list[str] = Field(default_factory=list)


class PainPointInsight(BaseModel):
    """One pain point as seen from a single customer (aggregated over its mentions)."""

    topic_name: str
    mention_count: int
    max_confidence: float
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    last_mentioned_at: datetime
    source_connectors: list[str] = Field(default_factory=list)
    sentiments: list[str] = Field(default_factory=list)


class PainPointScore(BaseModel):
    """Org-level roll-up for one pain-point topic."""

    org_id: str
    topic_name: str
    customer_count: int
    mention_count: int
    max_confidence: float
    avg_confidence: Optional[float] = None
    low_confidence_count: int = 0
    top_customers: list[str] = Field(default_factory=list)
    trend: Optional[TopicTrend] = None
    status: TopicStatus = TopicStatus.OPEN


class PainPointDetail(BaseModel):
    """Pain-point detail: score + affected customers + evidence."""

    score: PainPointScore
    affected_customers: list["AffectedCustomer"] = Field(default_factory=list)
    mentions: list[PainPointMentionRecord] = Field(default_factory=list)


class CustomerSummary(BaseModel):
    """Customer list row: identity + latest revenue + top insights."""

    external_customer_id: str
    customer_name: str
    latest_revenue: Optional[RevenueSummary] = None
    feature_gap_count: int = 0
    pain_point_count: int = 0
    mention_count: int = 0
    top_insights: list[CustomerInsight] = Field(default_factory=list)
    health: Optional["CustomerHealth"] = None


class CustomerHealth(BaseModel):
    """Signals from a customer's own mentions; drives the at-risk view."""

    negative_share: float = 0.0
    churn_risk_count: int = 0
    high_urgency_count: int = 0
    last_touch_at: Optional[datetime] = None
    competitors: list[str] = Field(default_factory=list)

    @property
    def at_risk(self) -> bool:
        return self.churn_risk_count > 0 or self.negative_share >= 0.5


class CustomerDetail(CustomerSummary):
    """Customer detail: everything in the summary plus all insights and citations."""

    insights: list[CustomerInsight] = Field(default_factory=list)
    pain_point_insights: list[PainPointInsight] = Field(default_factory=list)
    mentions: list[FeatureGapMentionRecord] = Field(default_factory=list)
    pain_point_mentions: list[PainPointMentionRecord] = Field(default_factory=list)


class AffectedCustomer(BaseModel):
    """A customer that mentioned a given feature gap, with its revenue weight."""

    external_customer_id: str
    customer_name: str
    arr: float = 0.0
    mrr: float = 0.0
    mention_count: int = 0


class FeatureGapDetail(BaseModel):
    """Feature gap detail: score + affected customers + evidence."""

    score: FeatureGapScore
    affected_customers: list[AffectedCustomer] = Field(default_factory=list)
    mentions: list[FeatureGapMentionRecord] = Field(default_factory=list)


class IntelligenceOverview(BaseModel):
    """Org-level roll-up shown on the portal landing page."""

    total_arr_at_stake: float = 0.0
    total_mrr_at_stake: float = 0.0
    feature_gap_count: int = 0
    customer_count: int = 0
    mention_count: int = 0
    source_connectors: list[str] = Field(default_factory=list)
    top_feature_gaps: list[FeatureGapScore] = Field(default_factory=list)
    top_customers: list[CustomerSummary] = Field(default_factory=list)
    last_mention_at: Optional[datetime] = None
    pain_point_count: int = 0
    emerging_feature_gaps: list[FeatureGapScore] = Field(default_factory=list)
    at_risk_customers: list[CustomerSummary] = Field(default_factory=list)
    intent_mix: dict[str, int] = Field(default_factory=dict)
    tone_mix: dict[str, int] = Field(default_factory=dict)


FeatureGapScore.model_rebuild()
CustomerSummary.model_rebuild()
