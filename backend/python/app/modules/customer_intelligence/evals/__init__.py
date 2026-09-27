"""Golden set + scorer for Customer Feature Intelligence extraction evals.

Live harness (real LLM) is opt-in — not part of the default fast suite.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.models.intelligence import (
    FeatureGapCandidate,
    FeatureIntelligenceExtractionResult,
    IntelligenceTopic,
    PainPoint,
    TaxonomyHint,
    TopicKind,
)
from app.modules.customer_intelligence.pipeline import run_pipeline
from app.modules.customer_intelligence.pipeline.context import ExtractionContext
from app.modules.customer_intelligence.pipeline.stages import (
    excerpt_grounded,
    normalize_name,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "feature_intelligence.jsonl"


@dataclass
class GoldenCase:
    id: str
    text: str
    expected_customer: Optional[str] = None
    expected_feature_gaps: list[str] = field(default_factory=list)
    expected_pain_points: list[str] = field(default_factory=list)
    taxonomy: list[dict] = field(default_factory=list)
    known_customers: list[str] = field(default_factory=list)
    must_exclude: list[str] = field(default_factory=list)


@dataclass
class BucketStats:
    correct: int = 0
    total: int = 0

    @property
    def precision(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class EvalReport:
    cases: int = 0
    feature_precision: float = 0.0
    feature_recall: float = 0.0
    pain_precision: float = 0.0
    pain_recall: float = 0.0
    duplicate_rate: float = 0.0
    grounding_rate: float = 0.0
    customer_accuracy: float = 0.0
    guidance_adherence: float = 0.0
    confidence_buckets: dict[str, BucketStats] = field(default_factory=dict)

    def render_text(self) -> str:
        lines = [
            f"cases={self.cases}",
            f"feature P/R={self.feature_precision:.2f}/{self.feature_recall:.2f}",
            f"pain P/R={self.pain_precision:.2f}/{self.pain_recall:.2f}",
            f"duplicate_rate={self.duplicate_rate:.2f}",
            f"grounding_rate={self.grounding_rate:.2f}",
            f"customer_accuracy={self.customer_accuracy:.2f}",
            f"guidance_adherence={self.guidance_adherence:.2f}",
            "confidence calibration:",
        ]
        for name, bucket in sorted(self.confidence_buckets.items()):
            lines.append(f"  {name}: precision={bucket.precision:.2f} (n={bucket.total})")
        return "\n".join(lines)


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    if not path.exists():
        return cases
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw = json.loads(line)
        cases.append(GoldenCase(**raw))
    return cases


def _bucket(conf: float) -> str:
    if conf < 0.5:
        return "<0.5"
    if conf < 0.7:
        return "0.5-0.7"
    if conf < 0.9:
        return "0.7-0.9"
    return ">=0.9"


def _pr(predicted: set[str], expected: set[str]) -> tuple[float, float]:
    if not predicted and not expected:
        return 1.0, 1.0
    tp = len(predicted & expected)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(expected) if expected else 0.0
    return precision, recall


def score_case(
    case: GoldenCase,
    result: FeatureIntelligenceExtractionResult,
    *,
    resolved_customer: Optional[str] = None,
) -> dict:
    pred_gaps = {normalize_name(g.feature_name) for g in result.feature_gaps}
    exp_gaps = {normalize_name(n) for n in case.expected_feature_gaps}
    pred_pains = {normalize_name(p.summary) for p in result.pain_points}
    exp_pains = {normalize_name(n) for n in case.expected_pain_points}

    fp, fr = _pr(pred_gaps, exp_gaps)
    pp, pr = _pr(pred_pains, exp_pains)

    all_items = list(result.feature_gaps) + list(result.pain_points)
    grounded = sum(
        1 for item in all_items if excerpt_grounded(getattr(item, "excerpt", ""), case.text)
    )
    grounding = grounded / len(all_items) if all_items else 1.0

    # Duplicate rate: extra distinct topics beyond expected for this customer
    expected_n = len(exp_gaps) + len(exp_pains)
    produced_n = len(pred_gaps) + len(pred_pains)
    dup = max(0, produced_n - expected_n) / produced_n if produced_n else 0.0

    cust_ok = 1.0
    if case.expected_customer:
        got = normalize_name(resolved_customer or result.customer_name or "")
        cust_ok = 1.0 if got == normalize_name(case.expected_customer) else 0.0

    excluded = {normalize_name(n) for n in case.must_exclude}
    leaked = excluded & (pred_gaps | pred_pains)
    guidance_ok = 1.0 if not leaked else 0.0

    buckets: dict[str, tuple[int, int]] = {}
    for item in result.feature_gaps:
        name = normalize_name(item.feature_name)
        b = _bucket(item.confidence)
        correct, total = buckets.get(b, (0, 0))
        buckets[b] = (correct + (1 if name in exp_gaps else 0), total + 1)
    for item in result.pain_points:
        name = normalize_name(item.summary)
        b = _bucket(item.confidence)
        correct, total = buckets.get(b, (0, 0))
        buckets[b] = (correct + (1 if name in exp_pains else 0), total + 1)

    return {
        "feature_precision": fp,
        "feature_recall": fr,
        "pain_precision": pp,
        "pain_recall": pr,
        "duplicate_rate": dup,
        "grounding_rate": grounding,
        "customer_accuracy": cust_ok,
        "guidance_adherence": guidance_ok,
        "buckets": buckets,
    }


async def run_offline_case(case: GoldenCase, result: FeatureIntelligenceExtractionResult) -> dict:
    """Score a pre-baked LLM result after running pipeline stages."""
    taxonomy = [
        IntelligenceTopic(
            id=i + 1,
            org_id="eval",
            kind=TopicKind(t["kind"]),
            canonical_name=t["name"],
            aliases=t.get("aliases", []),
            guidance=t.get("guidance"),
        )
        for i, t in enumerate(case.taxonomy)
    ]
    hints = [
        TaxonomyHint(
            id=str(t.id),
            kind=t.kind,
            name=t.canonical_name,
            aliases=t.aliases,
            guidance=t.guidance,
        )
        for t in taxonomy
    ]
    known = [(f"id:{n}", n) for n in case.known_customers]
    ctx = ExtractionContext(
        org_id="eval",
        text=case.text,
        result=result,
        taxonomy=taxonomy,
        taxonomy_hints=hints,
        known_customers=known,
    )
    ctx = await run_pipeline(ctx)
    return score_case(case, ctx.result, resolved_customer=ctx.resolved_customer_name)


def aggregate(scores: list[dict]) -> EvalReport:
    if not scores:
        return EvalReport()
    n = len(scores)
    buckets: dict[str, BucketStats] = {}
    for s in scores:
        for name, (correct, total) in s["buckets"].items():
            b = buckets.setdefault(name, BucketStats())
            b.correct += correct
            b.total += total
    return EvalReport(
        cases=n,
        feature_precision=sum(s["feature_precision"] for s in scores) / n,
        feature_recall=sum(s["feature_recall"] for s in scores) / n,
        pain_precision=sum(s["pain_precision"] for s in scores) / n,
        pain_recall=sum(s["pain_recall"] for s in scores) / n,
        duplicate_rate=sum(s["duplicate_rate"] for s in scores) / n,
        grounding_rate=sum(s["grounding_rate"] for s in scores) / n,
        customer_accuracy=sum(s["customer_accuracy"] for s in scores) / n,
        guidance_adherence=sum(s["guidance_adherence"] for s in scores) / n,
        confidence_buckets=buckets,
    )


async def run_feature_intelligence_eval(extractor, stages=None) -> EvalReport:
    """Live eval against a real FeatureIntelligenceExtractor. Not CI-default."""
    from app.modules.customer_intelligence.pipeline import run_pipeline as _run

    scores = []
    for case in load_golden():
        taxonomy = [
            TaxonomyHint(
                id=str(i + 1),
                kind=TopicKind(t["kind"]),
                name=t["name"],
                aliases=t.get("aliases", []),
                guidance=t.get("guidance"),
            )
            for i, t in enumerate(case.taxonomy)
        ]
        result = await extractor.extract(
            text=case.text,
            org_id="eval",
            infer_customer=True,
            taxonomy=taxonomy,
            known_customers=case.known_customers,
        )
        topics = [
            IntelligenceTopic(
                id=i + 1,
                org_id="eval",
                kind=TopicKind(t["kind"]),
                canonical_name=t["name"],
                aliases=t.get("aliases", []),
                guidance=t.get("guidance"),
            )
            for i, t in enumerate(case.taxonomy)
        ]
        ctx = ExtractionContext(
            org_id="eval",
            text=case.text,
            result=result or FeatureIntelligenceExtractionResult(),
            taxonomy=topics,
            taxonomy_hints=taxonomy,
            known_customers=[(f"id:{n}", n) for n in case.known_customers],
        )
        ctx = await _run(ctx, stages)
        scores.append(score_case(case, ctx.result, resolved_customer=ctx.resolved_customer_name))
    return aggregate(scores)
