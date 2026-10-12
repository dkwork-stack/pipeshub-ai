"""Pipeline stages: verify, dedupe, canonicalize, resolve customer."""
from __future__ import annotations

import os
from difflib import SequenceMatcher
from typing import Optional, Protocol

from app.models.intelligence import (
    FeatureGapCandidate,
    IntelligenceTopic,
    PainPoint,
    TopicKind,
)
from app.modules.customer_intelligence.matching.matcher import (
    ITopicMatcher,
    LexicalTopicMatcher,
    topics_of_kind,
)
from app.modules.customer_intelligence.pipeline.context import (
    DropReason,
    DropReasonCode,
    ExtractionContext,
)
from app.modules.customer_intelligence.text import (
    normalize_customer_name,
    normalize_name,
    normalize_text,
)

__all__ = [
    "CanonicalizeToTopic",
    "DedupeWithinEvent",
    "ResolveCustomer",
    "Stage",
    "VerifyExcerpts",
    "excerpt_grounded",
    "match_known_customer",
    "normalize_customer_name",
    "normalize_name",
    "normalize_text",
]

_CUSTOMER_SIMILARITY = float(os.getenv("INTELLIGENCE_CUSTOMER_SIMILARITY", "0.88"))


def excerpt_grounded(excerpt: str, text: str) -> bool:
    if not excerpt or not text:
        return False
    return normalize_text(excerpt) in normalize_text(text)


def _best_match(
    needle: str, candidates: list[tuple[str, str]], threshold: float
) -> Optional[str]:
    """Return the id of the best fuzzy match above ``threshold``, or None.

    ``candidates`` is a list of ``(id, name)`` pairs. Matching is against the
    normalized name.
    """
    needle_n = normalize_name(needle)
    if not needle_n:
        return None
    best_id: Optional[str] = None
    best_score = 0.0
    for cand_id, cand_name in candidates:
        score = SequenceMatcher(None, needle_n, normalize_name(cand_name)).ratio()
        if score > best_score:
            best_score = score
            best_id = cand_id
    return best_id if best_score >= threshold else None


class Stage(Protocol):
    async def run(self, ctx: ExtractionContext) -> ExtractionContext: ...


class VerifyExcerpts:
    """Drop items whose excerpt is not grounded in the source text.

    Low confidence alone never drops an item — it is persisted and filtered
    at read time.
    """

    async def run(self, ctx: ExtractionContext) -> ExtractionContext:
        kept_gaps: list[FeatureGapCandidate] = []
        for gap in ctx.result.feature_gaps:
            name = (gap.feature_name or "").strip()
            if not name:
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.EMPTY_NAME,
                        kind="feature_gap",
                        name="",
                    )
                )
                continue
            if not excerpt_grounded(gap.excerpt, ctx.text):
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.UNGROUNDED_EXCERPT,
                        kind="feature_gap",
                        name=name,
                        detail=gap.excerpt[:120],
                    )
                )
                continue
            kept_gaps.append(gap)

        kept_pains: list[PainPoint] = []
        for pain in ctx.result.pain_points:
            name = (pain.summary or "").strip()
            if not name:
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.EMPTY_NAME,
                        kind="pain_point",
                        name="",
                    )
                )
                continue
            if not excerpt_grounded(pain.excerpt, ctx.text):
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.UNGROUNDED_EXCERPT,
                        kind="pain_point",
                        name=name,
                        detail=pain.excerpt[:120],
                    )
                )
                continue
            kept_pains.append(pain)

        ctx.result.feature_gaps = kept_gaps
        ctx.result.pain_points = kept_pains
        return ctx


class DedupeWithinEvent:
    """Collapse same-normalized-name items; keep highest confidence + its excerpt."""

    async def run(self, ctx: ExtractionContext) -> ExtractionContext:
        ctx.result.feature_gaps = self._dedupe_gaps(ctx, ctx.result.feature_gaps)
        ctx.result.pain_points = self._dedupe_pains(ctx, ctx.result.pain_points)
        return ctx

    def _dedupe_gaps(
        self, ctx: ExtractionContext, gaps: list[FeatureGapCandidate]
    ) -> list[FeatureGapCandidate]:
        best: dict[str, FeatureGapCandidate] = {}
        for gap in gaps:
            key = normalize_name(gap.feature_name)
            existing = best.get(key)
            if existing is None:
                best[key] = gap
            elif gap.confidence > existing.confidence:
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.DUPLICATE_WITHIN_EVENT,
                        kind="feature_gap",
                        name=existing.feature_name,
                    )
                )
                best[key] = gap
            else:
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.DUPLICATE_WITHIN_EVENT,
                        kind="feature_gap",
                        name=gap.feature_name,
                    )
                )
        return list(best.values())

    def _dedupe_pains(
        self, ctx: ExtractionContext, pains: list[PainPoint]
    ) -> list[PainPoint]:
        best: dict[str, PainPoint] = {}
        for pain in pains:
            key = normalize_name(pain.summary)
            existing = best.get(key)
            if existing is None:
                best[key] = pain
            elif pain.confidence > existing.confidence:
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.DUPLICATE_WITHIN_EVENT,
                        kind="pain_point",
                        name=existing.summary,
                    )
                )
                best[key] = pain
            else:
                ctx.dropped.append(
                    DropReason(
                        code=DropReasonCode.DUPLICATE_WITHIN_EVENT,
                        kind="pain_point",
                        name=pain.summary,
                    )
                )
        return list(best.values())


class CanonicalizeToTopic:
    """Classify each item against the org's known topics (§6 of the architecture doc).

    Order: the LLM's ``topic_id`` hint, then ``ITopicMatcher`` (lexical, then
    semantic when an embedding model is configured). A match renames the item
    to the topic's canonical name; a non-exact match also proposes the item's
    own wording as a new alias. No match keeps the free-form name, and the
    ingestion service creates a topic for it.
    """

    def __init__(self, matcher: Optional[ITopicMatcher] = None, similarity: Optional[float] = None) -> None:
        self.matcher = matcher or LexicalTopicMatcher(similarity)

    async def run(self, ctx: ExtractionContext) -> ExtractionContext:
        by_id = {str(t.id): t for t in ctx.taxonomy if t.id is not None and t.merged_into_id is None}
        gap_topics = topics_of_kind(ctx.taxonomy, TopicKind.FEATURE_GAP)
        pain_topics = topics_of_kind(ctx.taxonomy, TopicKind.PAIN_POINT)

        mapped_gaps: list[FeatureGapCandidate] = []
        for gap in ctx.result.feature_gaps:
            topic = await self._resolve(ctx, gap.topic_id, gap.feature_name, gap.description, by_id, gap_topics, TopicKind.FEATURE_GAP)
            if topic is None:
                mapped_gaps.append(gap.model_copy(update={"topic_id": None}))
            elif not self._excluded(ctx, topic, "feature_gap", gap.feature_name, gap.excerpt, gap.description):
                mapped_gaps.append(gap.model_copy(update={"feature_name": topic.canonical_name, "topic_id": str(topic.id)}))

        mapped_pains: list[PainPoint] = []
        for pain in ctx.result.pain_points:
            topic = await self._resolve(ctx, pain.topic_id, pain.summary, pain.summary, by_id, pain_topics, TopicKind.PAIN_POINT)
            if topic is None:
                mapped_pains.append(pain.model_copy(update={"topic_id": None}))
            elif not self._excluded(ctx, topic, "pain_point", pain.summary, pain.excerpt):
                mapped_pains.append(pain.model_copy(update={"summary": topic.canonical_name, "topic_id": str(topic.id)}))

        ctx.result.feature_gaps = mapped_gaps
        ctx.result.pain_points = mapped_pains
        return ctx

    async def _resolve(
        self,
        ctx: ExtractionContext,
        topic_id: Optional[str],
        name: str,
        description: str,
        by_id: dict[str, IntelligenceTopic],
        topics: list[IntelligenceTopic],
        kind: TopicKind,
    ) -> Optional[IntelligenceTopic]:
        hinted = by_id.get(topic_id) if topic_id else None
        if hinted is not None and hinted.kind == kind:
            topic, exact = hinted, normalize_name(hinted.canonical_name) == normalize_name(name)
        else:
            found = await self.matcher.match(ctx.org_id, name, description, topics)
            if found is None:
                return None
            topic, exact = found.topic, found.method in ("exact", "alias")
        if not exact and topic.id is not None and name.strip():
            ctx.alias_proposals.append((topic.id, name.strip()))
        return topic

    def _excluded(self, ctx: ExtractionContext, topic: IntelligenceTopic, kind: str, name: str, *texts: str) -> bool:
        if not self._guidance_excludes(topic.guidance, name, *texts):
            return False
        ctx.dropped.append(
            DropReason(code=DropReasonCode.GUIDANCE_EXCLUDED, kind=kind, name=name, detail=topic.canonical_name)
        )
        return True

    @staticmethod
    def _guidance_excludes(guidance: Optional[str], *texts: str) -> bool:
        """Heuristic: guidance lines starting with 'exclude:' / 'ignore:' drop matches.

        Full guidance is also sent to the LLM; this catches the common
        post-hoc case where an item was mapped to a topic whose exclude list
        covers it.
        """
        if not guidance:
            return False
        haystack = " ".join(normalize_text(t) for t in texts if t)
        for line in guidance.splitlines():
            lower = line.strip().lower()
            if not lower.startswith(("exclude:", "ignore:")):
                continue
            phrase = lower.split(":", 1)[1].strip()
            if phrase and phrase in haystack:
                return True
        return False


def match_known_customer(
    customer_name: str,
    known_customers: list[tuple[str, str]],
    *,
    similarity: float = _CUSTOMER_SIMILARITY,
) -> Optional[tuple[str, str]]:
    """Return ``(external_customer_id, canonical_name)`` when ``customer_name`` matches.

    Exact (corp-suffix-stripped) first, then fuzzy. None when no match.
    """
    raw = (customer_name or "").strip()
    if not raw or not known_customers:
        return None
    raw_n = normalize_customer_name(raw)
    for ext_id, known_name in known_customers:
        if normalize_customer_name(known_name) == raw_n:
            return ext_id, known_name
    norm_candidates = [
        (ext_id, normalize_customer_name(name)) for ext_id, name in known_customers
    ]
    matched_id = _best_match(raw_n, norm_candidates, similarity)
    if not matched_id:
        return None
    for ext_id, known_name in known_customers:
        if ext_id == matched_id:
            return ext_id, known_name
    return None


class ResolveCustomer:
    """Prefer an existing customer spelling over creating a near-duplicate."""

    def __init__(self, similarity: float = _CUSTOMER_SIMILARITY) -> None:
        self.similarity = similarity

    async def run(self, ctx: ExtractionContext) -> ExtractionContext:
        raw_name = (ctx.resolved_customer_name or ctx.result.customer_name or "").strip()
        if not raw_name:
            return ctx

        matched = match_known_customer(
            raw_name, ctx.known_customers, similarity=self.similarity
        )
        if matched:
            ext_id, known_name = matched
            ctx.resolved_customer_id = ext_id
            ctx.resolved_customer_name = known_name
            ctx.result.customer_name = known_name
            return ctx

        ctx.resolved_customer_name = raw_name
        return ctx
