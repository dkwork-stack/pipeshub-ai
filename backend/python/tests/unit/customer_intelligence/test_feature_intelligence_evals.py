"""Offline scoring tests for the feature-intelligence eval harness."""
from __future__ import annotations

import pytest

from app.models.intelligence import (
    FeatureGapCandidate,
    FeatureIntelligenceExtractionResult,
    PainPoint,
)
from app.modules.customer_intelligence.evals import (
    GoldenCase,
    aggregate,
    load_golden,
    run_offline_case,
)


@pytest.mark.asyncio
async def test_golden_file_loads():
    cases = load_golden()
    assert len(cases) >= 3


@pytest.mark.asyncio
async def test_offline_scoring_paraphrase_dedupe():
    case = GoldenCase(
        id="t1",
        text="Customer: Acme Inc. We cannot export bulk CSV.",
        expected_customer="Acme Inc.",
        expected_feature_gaps=["Bulk CSV export"],
        expected_pain_points=["Cannot export data in bulk"],
        taxonomy=[
            {
                "kind": "feature_gap",
                "name": "Bulk CSV export",
                "aliases": ["CSV bulk export"],
            },
            {
                "kind": "pain_point",
                "name": "Cannot export data in bulk",
                "aliases": ["unable to bulk export"],
            },
        ],
        known_customers=["Acme Inc."],
    )
    result = FeatureIntelligenceExtractionResult(
        customer_name="Acme Inc.",
        feature_gaps=[
            FeatureGapCandidate(
                feature_name="CSV bulk export",
                description="need export",
                confidence=0.85,
                excerpt="cannot export bulk CSV",
            )
        ],
        pain_points=[
            PainPoint(
                summary="unable to bulk export",
                confidence=0.8,
                excerpt="cannot export bulk CSV",
            )
        ],
    )
    score = await run_offline_case(case, result)
    assert score["feature_precision"] == 1.0
    assert score["feature_recall"] == 1.0
    assert score["pain_precision"] == 1.0
    assert score["grounding_rate"] == 1.0
    assert score["customer_accuracy"] == 1.0

    report = aggregate([score])
    assert "0.7-0.9" in report.confidence_buckets
    assert "feature P/R" in report.render_text()
