"""Domain read-model -> API schema mapping.

Single place where the wire contract is derived from storage-side models, so
neither the repository nor the routers need to know about the other's shapes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.schemas.intelligence_portal import (
    AffectedCustomerResponse,
    AuditEntryResponse,
    CustomerDetailResponse,
    CustomerHealthResponse,
    CustomerResponse,
    ErasureResponse,
    FeatureGapDetailResponse,
    FeatureGapResponse,
    InsightResponse,
    MentionResponse,
    OverviewResponse,
    Page,
    PageMeta,
    PainPointDetailResponse,
    PainPointInsightResponse,
    PainPointMentionResponse,
    PainPointResponse,
    RevenueResponse,
    TopicResponse,
    TrendResponse,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.models.intelligence import (
        AffectedCustomer,
        AuditEntry,
        CustomerDetail,
        CustomerHealth,
        CustomerInsight,
        CustomerSummary,
        ErasureResult,
        FeatureGapDetail,
        FeatureGapMentionRecord,
        FeatureGapScore,
        IntelligenceOverview,
        IntelligenceTopic,
        PainPointDetail,
        PainPointInsight,
        PainPointMentionRecord,
        PainPointScore,
        RevenueSummary,
        TopicTrend,
    )


def page_of(items: Sequence, total: int, *, limit: int, offset: int) -> Page:
    return Page(
        items=list(items),
        page=PageMeta(total=total, limit=limit, offset=offset, has_more=offset + len(items) < total),
    )


def revenue_response(r: RevenueSummary | None) -> RevenueResponse | None:
    return RevenueResponse(**r.model_dump()) if r else None


def insight_response(i: CustomerInsight) -> InsightResponse:
    return InsightResponse(**i.model_dump())


def _value(v: object) -> str:
    return str(getattr(v, "value", v))


def _evidence(m: FeatureGapMentionRecord | PainPointMentionRecord) -> dict:
    return {
        "sentiment": m.sentiment,
        "tone": _value(m.tone),
        "urgency": _value(m.urgency),
        "intent": _value(m.intent),
        "speaker_role": _value(m.speaker_role),
        "product_area": m.product_area,
        "business_impact": m.business_impact,
        "workaround": m.workaround,
        "competitor": m.competitor,
        "churn_risk": m.churn_risk,
        "source_record_id": m.source_record_id,
        "extraction_model": m.extraction_model,
        "prompt_version": m.prompt_version,
    }


def trend_response(t: TopicTrend | None) -> TrendResponse | None:
    return TrendResponse(**t.model_dump()) if t else None


def health_response(h: CustomerHealth | None) -> CustomerHealthResponse | None:
    return CustomerHealthResponse(**h.model_dump(), at_risk=h.at_risk) if h else None


def mention_response(m: FeatureGapMentionRecord) -> MentionResponse:
    return MentionResponse(
        **_evidence(m),
        external_customer_id=m.external_customer_id,
        feature_name=m.feature_name,
        description=m.description,
        confidence=m.confidence,
        excerpt=m.excerpt,
        source_connector=m.source_connector,
        source_type=_value(m.source_type),
        external_event_id=m.external_event_id,
        citation_url=m.citation_url,
        occurred_at=m.occurred_at,
    )


def feature_gap_response(s: FeatureGapScore) -> FeatureGapResponse:
    return FeatureGapResponse(
        feature_name=s.feature_name,
        total_arr_at_stake=s.total_arr_at_stake,
        total_mrr_at_stake=s.total_mrr_at_stake,
        customer_count=s.customer_count,
        mention_count=s.mention_count,
        score=s.score,
        top_customers=s.top_customers,
        max_confidence=s.max_confidence,
        avg_confidence=s.avg_confidence,
        low_confidence_count=s.low_confidence_count,
        status=_value(s.status),
        trend=trend_response(s.trend),
    )


def affected_customer_response(c: AffectedCustomer) -> AffectedCustomerResponse:
    return AffectedCustomerResponse(**c.model_dump())


def feature_gap_detail_response(d: FeatureGapDetail) -> FeatureGapDetailResponse:
    return FeatureGapDetailResponse(
        **feature_gap_response(d.score).model_dump(),
        affected_customers=[affected_customer_response(c) for c in d.affected_customers],
        mentions=[mention_response(m) for m in d.mentions],
    )


def pain_point_mention_response(m: PainPointMentionRecord) -> PainPointMentionResponse:
    return PainPointMentionResponse(
        **_evidence(m),
        external_customer_id=m.external_customer_id,
        topic_name=m.topic_name,
        summary=m.summary,
        confidence=m.confidence,
        excerpt=m.excerpt,
        source_connector=m.source_connector,
        source_type=_value(m.source_type),
        external_event_id=m.external_event_id,
        citation_url=m.citation_url,
        occurred_at=m.occurred_at,
    )


def pain_point_response(s: PainPointScore) -> PainPointResponse:
    return PainPointResponse(
        topic_name=s.topic_name,
        customer_count=s.customer_count,
        mention_count=s.mention_count,
        max_confidence=s.max_confidence,
        avg_confidence=s.avg_confidence,
        low_confidence_count=s.low_confidence_count,
        top_customers=s.top_customers,
        status=_value(s.status),
        trend=trend_response(s.trend),
    )


def pain_point_detail_response(d: PainPointDetail) -> PainPointDetailResponse:
    return PainPointDetailResponse(
        **pain_point_response(d.score).model_dump(),
        affected_customers=[affected_customer_response(c) for c in d.affected_customers],
        mentions=[pain_point_mention_response(m) for m in d.mentions],
    )


def pain_point_insight_response(i: PainPointInsight) -> PainPointInsightResponse:
    return PainPointInsightResponse(**i.model_dump())


def topic_response(t: IntelligenceTopic) -> TopicResponse:
    return TopicResponse(
        id=t.id or 0,
        kind=_value(t.kind),
        canonical_name=t.canonical_name,
        aliases=t.aliases or [],
        guidance=t.guidance,
        description=t.description,
        status=_value(t.status),
        merged_into_id=t.merged_into_id,
        updated_by=t.updated_by,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def customer_response(c: CustomerSummary) -> CustomerResponse:
    return CustomerResponse(
        external_customer_id=c.external_customer_id,
        customer_name=c.customer_name,
        latest_revenue=revenue_response(c.latest_revenue),
        feature_gap_count=c.feature_gap_count,
        pain_point_count=c.pain_point_count,
        mention_count=c.mention_count,
        top_insights=[insight_response(i) for i in c.top_insights],
        health=health_response(c.health),
    )


def customer_detail_response(d: CustomerDetail) -> CustomerDetailResponse:
    return CustomerDetailResponse(
        **customer_response(d).model_dump(),
        insights=[insight_response(i) for i in d.insights],
        pain_point_insights=[pain_point_insight_response(i) for i in d.pain_point_insights],
        mentions=[mention_response(m) for m in d.mentions],
        pain_point_mentions=[pain_point_mention_response(m) for m in d.pain_point_mentions],
    )


def overview_response(o: IntelligenceOverview) -> OverviewResponse:
    return OverviewResponse(
        total_arr_at_stake=o.total_arr_at_stake,
        total_mrr_at_stake=o.total_mrr_at_stake,
        feature_gap_count=o.feature_gap_count,
        customer_count=o.customer_count,
        mention_count=o.mention_count,
        source_connectors=o.source_connectors,
        top_feature_gaps=[feature_gap_response(s) for s in o.top_feature_gaps],
        top_customers=[customer_response(c) for c in o.top_customers],
        last_mention_at=o.last_mention_at,
        pain_point_count=o.pain_point_count,
        emerging_feature_gaps=[feature_gap_response(s) for s in o.emerging_feature_gaps],
        at_risk_customers=[customer_response(c) for c in o.at_risk_customers],
        intent_mix=o.intent_mix,
        tone_mix=o.tone_mix,
    )


def erasure_response(r: ErasureResult) -> ErasureResponse:
    return ErasureResponse(**r.model_dump())


def audit_entry_response(e: AuditEntry) -> AuditEntryResponse:
    return AuditEntryResponse(**e.model_dump(exclude={"org_id"}))
