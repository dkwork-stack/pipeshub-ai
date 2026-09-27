"""Pipeline stages: verify, dedupe, canonicalize, resolve customer."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional, Protocol

from app.models.intelligence import (
    FeatureGapCandidate,
    IntelligenceTopic,
    PainPoint,
    TopicKind,
)
from app.modules.customer_intelligence.pipeline.context import (
    DropReason,
    DropReasonCode,
    ExtractionContext,
)

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_CORP_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|gmbh|pty|plc|corp|corporation|co|company|sa|ag)\b\.?",
    re.IGNORECASE,
)

# Fuzzy match threshold for mapping a free-form name onto an existing topic.
_TOPIC_SIMILARITY = float(__import__("os").getenv("INTELLIGENCE_TOPIC_SIMILARITY", "0.82"))
_CUSTOMER_SIMILARITY = float(__import__("os").getenv("INTELLIGENCE_CUSTOMER_SIMILARITY", "0.88"))


def normalize_text(value: str) -> str:
    return _WS.sub(" ", (value or "").strip().lower())


def normalize_name(value: str) -> str:
    cleaned = _PUNCT.sub(" ", normalize_text(value))
    return _WS.sub(" ", cleaned).strip()


def normalize_customer_name(value: str) -> str:
    cleaned = normalize_name(value)
    cleaned = _CORP_SUFFIXES.sub("", cleaned)
    return _WS.sub(" ", cleaned).strip()


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
    """Map each item onto an existing taxonomy topic, or record a new proposal.

    Matching order: LLM ``topic_id`` → exact/alias → fuzzy SequenceMatcher.
    When nothing matches, the free-form name is kept and the caller (ingestion)
    will upsert a new topic under that name.
    """

    def __init__(self, similarity: float = _TOPIC_SIMILARITY) -> None:
        self.similarity = similarity

    async def run(self, ctx: ExtractionContext) -> ExtractionContext:
        by_id = {str(t.id): t for t in ctx.taxonomy if t.id is not None and t.merged_into_id is None}
        gaps_by_kind = [t for t in ctx.taxonomy if t.kind == TopicKind.FEATURE_GAP and t.merged_into_id is None]
        pains_by_kind = [t for t in ctx.taxonomy if t.kind == TopicKind.PAIN_POINT and t.merged_into_id is None]

        mapped_gaps: list[FeatureGapCandidate] = []
        for gap in ctx.result.feature_gaps:
            mapped = self._map_gap(gap, by_id, gaps_by_kind, ctx)
            if mapped is not None:
                mapped_gaps.append(mapped)

        mapped_pains: list[PainPoint] = []
        for pain in ctx.result.pain_points:
            mapped = self._map_pain(pain, by_id, pains_by_kind, ctx)
            if mapped is not None:
                mapped_pains.append(mapped)

        ctx.result.feature_gaps = mapped_gaps
        ctx.result.pain_points = mapped_pains
        return ctx

    def _map_gap(
        self,
        gap: FeatureGapCandidate,
        by_id: dict[str, IntelligenceTopic],
        topics: list[IntelligenceTopic],
        ctx: ExtractionContext,
    ) -> Optional[FeatureGapCandidate]:
        topic = self._resolve(gap.topic_id, gap.feature_name, by_id, topics)
        if topic is None:
            return gap
        if self._guidance_excludes(topic.guidance, gap.feature_name, gap.excerpt, gap.description):
            ctx.dropped.append(
                DropReason(
                    code=DropReasonCode.GUIDANCE_EXCLUDED,
                    kind="feature_gap",
                    name=gap.feature_name,
                    detail=topic.canonical_name,
                )
            )
            return None
        return gap.model_copy(
            update={"feature_name": topic.canonical_name, "topic_id": str(topic.id)}
        )

    def _map_pain(
        self,
        pain: PainPoint,
        by_id: dict[str, IntelligenceTopic],
        topics: list[IntelligenceTopic],
        ctx: ExtractionContext,
    ) -> Optional[PainPoint]:
        topic = self._resolve(pain.topic_id, pain.summary, by_id, topics)
        if topic is None:
            return pain
        if self._guidance_excludes(topic.guidance, pain.summary, pain.excerpt):
            ctx.dropped.append(
                DropReason(
                    code=DropReasonCode.GUIDANCE_EXCLUDED,
                    kind="pain_point",
                    name=pain.summary,
                    detail=topic.canonical_name,
                )
            )
            return None
        return pain.model_copy(
            update={"summary": topic.canonical_name, "topic_id": str(topic.id)}
        )

    def _resolve(
        self,
        topic_id: Optional[str],
        name: str,
        by_id: dict[str, IntelligenceTopic],
        topics: list[IntelligenceTopic],
    ) -> Optional[IntelligenceTopic]:
        if topic_id and topic_id in by_id:
            return by_id[topic_id]

        name_n = normalize_name(name)
        for topic in topics:
            if normalize_name(topic.canonical_name) == name_n:
                return topic
            for alias in topic.aliases or []:
                if normalize_name(alias) == name_n:
                    return topic

        candidates = [(str(t.id), t.canonical_name) for t in topics if t.id is not None]
        for topic in topics:
            for alias in topic.aliases or []:
                candidates.append((str(topic.id), alias))
        matched_id = _best_match(name, candidates, self.similarity)
        return by_id.get(matched_id) if matched_id else None

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
            if not (lower.startswith("exclude:") or lower.startswith("ignore:")):
                continue
            phrase = lower.split(":", 1)[1].strip()
            if phrase and phrase in haystack:
                return True
        return False


class ResolveCustomer:
    """Prefer an existing customer spelling over creating a near-duplicate."""

    def __init__(self, similarity: float = _CUSTOMER_SIMILARITY) -> None:
        self.similarity = similarity

    async def run(self, ctx: ExtractionContext) -> ExtractionContext:
        raw_name = (ctx.resolved_customer_name or ctx.result.customer_name or "").strip()
        if not raw_name:
            return ctx

        # Exact / suffix-stripped match first
        raw_n = normalize_customer_name(raw_name)
        for ext_id, known_name in ctx.known_customers:
            if normalize_customer_name(known_name) == raw_n:
                ctx.resolved_customer_id = ext_id
                ctx.resolved_customer_name = known_name
                ctx.result.customer_name = known_name
                return ctx

        candidates = [(ext_id, name) for ext_id, name in ctx.known_customers]
        # Match against customer-normalized names via a temporary list
        norm_candidates = [
            (ext_id, normalize_customer_name(name)) for ext_id, name in ctx.known_customers
        ]
        matched_id = _best_match(raw_n, norm_candidates, self.similarity)
        if matched_id:
            for ext_id, known_name in candidates:
                if ext_id == matched_id:
                    ctx.resolved_customer_id = ext_id
                    ctx.resolved_customer_name = known_name
                    ctx.result.customer_name = known_name
                    return ctx

        ctx.resolved_customer_name = raw_name
        return ctx
