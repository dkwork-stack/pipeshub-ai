"""Offline unit tests for the Customer Feature Intelligence post-extraction pipeline."""
from __future__ import annotations

import pytest

from app.models.intelligence import (
    FeatureGapCandidate,
    FeatureIntelligenceExtractionResult,
    IntelligenceTopic,
    PainPoint,
    TopicKind,
)
from app.modules.customer_intelligence.pipeline import run_pipeline
from app.modules.customer_intelligence.pipeline.context import ExtractionContext
from app.modules.customer_intelligence.pipeline.stages import (
    CanonicalizeToTopic,
    DedupeWithinEvent,
    ResolveCustomer,
    VerifyExcerpts,
    normalize_customer_name,
)


def _ctx(**kwargs) -> ExtractionContext:
    defaults = dict(
        org_id="org-1",
        text="Acme Inc cannot export bulk CSV. We need SSO / SAML support.",
        result=FeatureIntelligenceExtractionResult(),
    )
    defaults.update(kwargs)
    return ExtractionContext(**defaults)


@pytest.mark.asyncio
async def test_verify_drops_ungrounded_excerpt():
    ctx = _ctx(
        result=FeatureIntelligenceExtractionResult(
            feature_gaps=[
                FeatureGapCandidate(
                    feature_name="Bulk CSV export",
                    description="Need export",
                    confidence=0.9,
                    excerpt="cannot export bulk CSV",
                ),
                FeatureGapCandidate(
                    feature_name="Teleportation",
                    description="Made up",
                    confidence=0.95,
                    excerpt="beam me up scotty",
                ),
            ]
        )
    )
    out = await VerifyExcerpts().run(ctx)
    assert len(out.result.feature_gaps) == 1
    assert out.result.feature_gaps[0].feature_name == "Bulk CSV export"
    assert any(d.code.value == "ungrounded_excerpt" for d in out.dropped)


@pytest.mark.asyncio
async def test_verify_keeps_low_confidence():
    ctx = _ctx(
        result=FeatureIntelligenceExtractionResult(
            feature_gaps=[
                FeatureGapCandidate(
                    feature_name="Bulk CSV export",
                    description="Need export",
                    confidence=0.2,
                    excerpt="cannot export bulk CSV",
                ),
            ]
        )
    )
    out = await VerifyExcerpts().run(ctx)
    assert len(out.result.feature_gaps) == 1
    assert out.result.feature_gaps[0].confidence == 0.2


@pytest.mark.asyncio
async def test_dedupe_keeps_highest_confidence():
    ctx = _ctx(
        result=FeatureIntelligenceExtractionResult(
            feature_gaps=[
                FeatureGapCandidate(
                    feature_name="Bulk CSV export",
                    description="a",
                    confidence=0.6,
                    excerpt="cannot export bulk CSV",
                ),
                FeatureGapCandidate(
                    feature_name="bulk csv export",
                    description="b",
                    confidence=0.9,
                    excerpt="cannot export bulk CSV",
                ),
            ]
        )
    )
    out = await DedupeWithinEvent().run(ctx)
    assert len(out.result.feature_gaps) == 1
    assert out.result.feature_gaps[0].confidence == 0.9


@pytest.mark.asyncio
async def test_canonicalize_fuzzy_and_guidance_exclude():
    topics = [
        IntelligenceTopic(
            id=1,
            org_id="org-1",
            kind=TopicKind.FEATURE_GAP,
            canonical_name="SSO / SAML support",
            aliases=["SAML login"],
            guidance="exclude: generic login bugs",
        ),
        IntelligenceTopic(
            id=2,
            org_id="org-1",
            kind=TopicKind.FEATURE_GAP,
            canonical_name="Bulk CSV export",
            aliases=["CSV bulk export"],
        ),
    ]
    ctx = _ctx(
        taxonomy=topics,
        result=FeatureIntelligenceExtractionResult(
            feature_gaps=[
                FeatureGapCandidate(
                    feature_name="CSV bulk export",
                    description="export",
                    confidence=0.8,
                    excerpt="cannot export bulk CSV",
                ),
                FeatureGapCandidate(
                    feature_name="generic login bugs",
                    description="login",
                    confidence=0.7,
                    excerpt="SSO / SAML support",
                    topic_id="1",
                ),
            ]
        ),
    )
    out = await CanonicalizeToTopic().run(ctx)
    names = {g.feature_name for g in out.result.feature_gaps}
    assert "Bulk CSV export" in names
    assert "generic login bugs" not in names
    assert any(d.code.value == "guidance_excluded" for d in out.dropped)


@pytest.mark.asyncio
async def test_resolve_customer_collapses_suffix():
    assert normalize_customer_name("Acme Inc.") == normalize_customer_name("Acme")
    ctx = _ctx(
        known_customers=[("file_upload:acme", "Acme")],
        resolved_customer_name="Acme Inc.",
        result=FeatureIntelligenceExtractionResult(customer_name="Acme Inc."),
    )
    out = await ResolveCustomer().run(ctx)
    assert out.resolved_customer_id == "file_upload:acme"
    assert out.resolved_customer_name == "Acme"


@pytest.mark.asyncio
async def test_full_pipeline_dedupes_across_rows_via_taxonomy():
    topics = [
        IntelligenceTopic(
            id=10,
            org_id="org-1",
            kind=TopicKind.FEATURE_GAP,
            canonical_name="Bulk CSV export",
            aliases=["CSV bulk export"],
        ),
        IntelligenceTopic(
            id=11,
            org_id="org-1",
            kind=TopicKind.PAIN_POINT,
            canonical_name="Cannot export data in bulk",
            aliases=["unable to bulk export"],
        ),
    ]
    # Row 1
    ctx1 = await run_pipeline(
        _ctx(
            text="Customer: Acme Inc. We cannot export bulk CSV.",
            taxonomy=topics,
            known_customers=[],
            result=FeatureIntelligenceExtractionResult(
                customer_name="Acme Inc.",
                feature_gaps=[
                    FeatureGapCandidate(
                        feature_name="CSV bulk export",
                        description="need it",
                        confidence=0.8,
                        excerpt="cannot export bulk CSV",
                    )
                ],
                pain_points=[
                    PainPoint(
                        summary="unable to bulk export",
                        confidence=0.75,
                        excerpt="cannot export bulk CSV",
                    )
                ],
            ),
        )
    )
    # Row 2 — paraphrased, same customer spelling variant
    ctx2 = await run_pipeline(
        _ctx(
            text="Customer: Acme. Still cannot export bulk CSV files.",
            taxonomy=topics,
            known_customers=[("file_upload:acme-inc", "Acme Inc.")],
            result=FeatureIntelligenceExtractionResult(
                customer_name="Acme",
                feature_gaps=[
                    FeatureGapCandidate(
                        feature_name="Bulk CSV export",
                        description="need it",
                        confidence=0.85,
                        excerpt="cannot export bulk CSV",
                    )
                ],
                pain_points=[
                    PainPoint(
                        summary="Cannot export data in bulk",
                        confidence=0.8,
                        excerpt="cannot export bulk CSV",
                    )
                ],
            ),
        )
    )
    assert ctx1.result.feature_gaps[0].feature_name == "Bulk CSV export"
    assert ctx2.result.feature_gaps[0].feature_name == "Bulk CSV export"
    assert ctx2.resolved_customer_name == "Acme Inc."
    assert ctx1.result.pain_points[0].summary == "Cannot export data in bulk"
    assert ctx2.result.pain_points[0].summary == "Cannot export data in bulk"
