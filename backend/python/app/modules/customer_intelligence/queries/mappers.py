"""Domain read-model -> API schema mapping.

Single place where the wire contract is derived from storage-side models, so
neither the repository nor the routers need to know about the other's shapes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.schemas.intelligence_portal import (
    AffectedCustomerResponse,
    CustomerDetailResponse,
    CustomerResponse,
    FeatureGapDetailResponse,
    FeatureGapResponse,
    InsightResponse,
    MentionResponse,
    OverviewResponse,
    Page,
    PageMeta,
    RevenueResponse,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.models.intelligence import (
        AffectedCustomer,
        CustomerDetail,
        CustomerInsight,
        CustomerSummary,
        FeatureGapDetail,
        FeatureGapMentionRecord,
        FeatureGapScore,
        IntelligenceOverview,
        RevenueSummary,
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


def mention_response(m: FeatureGapMentionRecord) -> MentionResponse:
    return MentionResponse(
        external_customer_id=m.external_customer_id,
        feature_name=m.feature_name,
        description=m.description,
        confidence=m.confidence,
        excerpt=m.excerpt,
        source_connector=m.source_connector,
        source_type=m.source_type.value if hasattr(m.source_type, "value") else str(m.source_type),
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
    )


def affected_customer_response(c: AffectedCustomer) -> AffectedCustomerResponse:
    return AffectedCustomerResponse(**c.model_dump())


def feature_gap_detail_response(d: FeatureGapDetail) -> FeatureGapDetailResponse:
    return FeatureGapDetailResponse(
        **feature_gap_response(d.score).model_dump(),
        affected_customers=[affected_customer_response(c) for c in d.affected_customers],
        mentions=[mention_response(m) for m in d.mentions],
    )


def customer_response(c: CustomerSummary) -> CustomerResponse:
    return CustomerResponse(
        external_customer_id=c.external_customer_id,
        customer_name=c.customer_name,
        latest_revenue=revenue_response(c.latest_revenue),
        feature_gap_count=c.feature_gap_count,
        mention_count=c.mention_count,
        top_insights=[insight_response(i) for i in c.top_insights],
    )


def customer_detail_response(d: CustomerDetail) -> CustomerDetailResponse:
    return CustomerDetailResponse(
        **customer_response(d).model_dump(),
        insights=[insight_response(i) for i in d.insights],
        mentions=[mention_response(m) for m in d.mentions],
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
    )
