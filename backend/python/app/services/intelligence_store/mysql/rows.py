"""Row <-> domain-model mapping shared by the write store and the query repository."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from app.models.intelligence import (
    FeatureGapMentionRecord,
    IntelligenceTopic,
    PainPointMentionRecord,
    SignalAttributes,
    TopicKind,
    TopicStatus,
    TopicTrend,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

# Mention names share a 191-char column (utf8mb4 unique-key budget, see schema.py).
NAME_MAX = 191


def clamp_name(name: str) -> str:
    return (name or "").strip()[:NAME_MAX]


def attribute_values(item: SignalAttributes) -> dict[str, Any]:
    """Column values for the qualitative attributes of a mention."""
    return {
        "sentiment": item.sentiment,
        "tone": item.tone.value,
        "urgency": item.urgency.value,
        "intent": item.intent.value,
        "speaker_role": item.speaker_role.value,
        "product_area": item.product_area,
        "business_impact": item.business_impact,
        "workaround": item.workaround,
        "competitor": item.competitor,
        "churn_risk": item.churn_risk,
    }


def provenance_values(mention: FeatureGapMentionRecord | PainPointMentionRecord) -> dict[str, Any]:
    return {
        "topic_id": mention.topic_id,
        "source_record_id": mention.source_record_id,
        "extraction_model": mention.extraction_model,
        "prompt_version": mention.prompt_version,
    }


def _attributes_from_row(m: "RowMapping") -> dict[str, Any]:
    # Rows written before these columns existed hold NULLs; the model's
    # validators turn those into neutral defaults.
    return {
        "sentiment": m.get("sentiment"),
        "tone": m.get("tone"),
        "urgency": m.get("urgency"),
        "intent": m.get("intent"),
        "speaker_role": m.get("speaker_role") or "customer",
        "product_area": m.get("product_area"),
        "business_impact": m.get("business_impact"),
        "workaround": m.get("workaround"),
        "competitor": m.get("competitor"),
        "churn_risk": bool(m.get("churn_risk")),
        "topic_id": m.get("topic_id"),
        "source_record_id": m.get("source_record_id"),
        "extraction_model": m.get("extraction_model"),
        "prompt_version": m.get("prompt_version"),
    }


def mention_from_row(m: "RowMapping") -> FeatureGapMentionRecord:
    return FeatureGapMentionRecord(
        org_id=m["org_id"],
        external_customer_id=m["external_customer_id"],
        feature_name=m["feature_name"],
        description=m["description"] or "",
        confidence=m["confidence"],
        excerpt=m["excerpt"] or "",
        source_connector=m["source_connector"],
        source_type=m["source_type"],
        external_event_id=m["external_event_id"],
        citation_url=m["citation_url"],
        occurred_at=m["occurred_at"],
        **_attributes_from_row(m),
    )


def pain_mention_from_row(m: "RowMapping") -> PainPointMentionRecord:
    attrs = _attributes_from_row(m)
    attrs["intent"] = m.get("intent") or "other"
    return PainPointMentionRecord(
        org_id=m["org_id"],
        external_customer_id=m["external_customer_id"],
        topic_name=m["topic_name"],
        summary=m["summary"] or m["topic_name"],
        confidence=m["confidence"],
        excerpt=m["excerpt"] or "",
        source_connector=m["source_connector"],
        source_type=m["source_type"],
        external_event_id=m["external_event_id"],
        citation_url=m["citation_url"],
        occurred_at=m["occurred_at"],
        **attrs,
    )


def topic_from_row(r: "RowMapping") -> IntelligenceTopic:
    return IntelligenceTopic(
        id=r["id"],
        org_id=r["org_id"],
        kind=TopicKind(r["kind"]),
        canonical_name=r["canonical_name"],
        aliases=list(r["aliases"] or []),
        guidance=r["guidance"],
        description=r.get("description"),
        status=TopicStatus(r.get("status") or TopicStatus.OPEN.value),
        merged_into_id=r["merged_into_id"],
        updated_by=r["updated_by"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def trend_from_json(raw: Optional[dict]) -> Optional[TopicTrend]:
    return TopicTrend.model_validate(raw) if raw else None
