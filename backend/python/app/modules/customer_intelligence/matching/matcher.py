"""Classify a newly extracted ask / pain point against the org's known topics.

Tiers, cheapest first (see docs/customer-intelligence-architecture.md §6):
the LLM's own ``topic_id`` hint, lexical (exact/alias, then fuzzy), then
semantic (embedding cosine). ``CompositeTopicMatcher`` chains matchers so a
deployment without an embedding model still works on the lexical tier.
"""
from __future__ import annotations

import hashlib
import math
import os
from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, NamedTuple, Optional

from app.modules.customer_intelligence.text import normalize_name

if TYPE_CHECKING:
    from logging import Logger

    from app.models.intelligence import IntelligenceTopic, TopicKind
    from app.modules.customer_intelligence.matching.embedder import ITextEmbedder
    from app.services.intelligence_store.interface.intelligence_store import (
        IIntelligenceStore,
    )

_STOPWORDS = frozenset(
    "a an and are be can for from have in is it of on or our the to we with would need want".split()
)


def _tokens(value: str) -> set[str]:
    return {t for t in normalize_name(value).split() if t not in _STOPWORDS and len(t) > 1}


class TopicMatch(NamedTuple):
    topic: IntelligenceTopic
    score: float
    method: str  # exact | alias | fuzzy | semantic


class ITopicMatcher(ABC):
    @abstractmethod
    async def match(
        self, org_id: str, name: str, description: str, topics: list[IntelligenceTopic]
    ) -> Optional[TopicMatch]:
        """Best existing topic for ``name``/``description`` among ``topics`` (one kind), or None."""

    async def register(self, org_id: str, topic: IntelligenceTopic) -> None:
        """Called after a new topic is created so caches can include it."""

    @abstractmethod
    async def rank_hints(
        self, org_id: str, text: str, topics: list[IntelligenceTopic], limit: int
    ) -> list[IntelligenceTopic]:
        """Topics most likely relevant to ``text`` — the prompt's 'known topics' list."""


class LexicalTopicMatcher(ITopicMatcher):
    def __init__(self, similarity: Optional[float] = None) -> None:
        self.similarity = similarity if similarity is not None else float(
            os.getenv("INTELLIGENCE_TOPIC_SIMILARITY", "0.82")
        )

    async def match(
        self, org_id: str, name: str, description: str, topics: list[IntelligenceTopic]
    ) -> Optional[TopicMatch]:
        needle = normalize_name(name)
        if not needle:
            return None
        for topic in topics:
            if normalize_name(topic.canonical_name) == needle:
                return TopicMatch(topic, 1.0, "exact")
        for topic in topics:
            if any(normalize_name(a) == needle for a in topic.aliases):
                return TopicMatch(topic, 1.0, "alias")
        best: Optional[TopicMatch] = None
        for topic in topics:
            for candidate in (topic.canonical_name, *topic.aliases):
                score = SequenceMatcher(None, needle, normalize_name(candidate)).ratio()
                if score >= self.similarity and (best is None or score > best.score):
                    best = TopicMatch(topic, score, "fuzzy")
        return best

    async def rank_hints(
        self, org_id: str, text: str, topics: list[IntelligenceTopic], limit: int
    ) -> list[IntelligenceTopic]:
        words = _tokens(text)

        def overlap(topic: IntelligenceTopic) -> int:
            return max(len(words & _tokens(n)) for n in (topic.canonical_name, *topic.aliases))

        return sorted(topics, key=lambda t: (-overlap(t), t.canonical_name))[:limit]


def _topic_text(topic: IntelligenceTopic) -> str:
    parts = [topic.canonical_name]
    if topic.aliases:
        parts.append("also: " + ", ".join(topic.aliases[:10]))
    if topic.description:
        parts.append(topic.description)
    return ". ".join(parts)[:1000]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingTopicMatcher(ITopicMatcher):
    """Cosine similarity over cached topic vectors (``intelligence_topic_embeddings``).

    Vectors are cached per (topic, model) in the store and in-process per org;
    a topic whose name/aliases/description changed is re-embedded lazily via
    its text hash. Brute-force cosine is fine to ~50k topics per org; past
    that, move vectors to IVectorDBService behind this same interface.
    """

    def __init__(
        self,
        logger: Logger,
        embedder: ITextEmbedder,
        store: IIntelligenceStore,
        similarity: Optional[float] = None,
    ) -> None:
        self.logger = logger
        self.embedder = embedder
        self.store = store
        self.similarity = similarity if similarity is not None else float(
            os.getenv("INTELLIGENCE_TOPIC_EMBED_SIMILARITY", "0.86")
        )
        self._cache: dict[tuple[str, str], dict[int, tuple[str, list[float]]]] = {}

    async def _vectors(
        self, org_id: str, topics: list[IntelligenceTopic]
    ) -> tuple[Optional[str], dict[int, list[float]]]:
        model = await self.embedder.model_id()
        if model is None:
            return None, {}
        key = (org_id, model)
        cache = self._cache.get(key)
        if cache is None:
            cache = await self.store.get_topic_embeddings(org_id, model)
            self._cache[key] = cache

        stale = []
        for topic in topics:
            if topic.id is None:
                continue
            text = _topic_text(topic)
            digest = hashlib.sha256(text.encode()).hexdigest()
            cached = cache.get(topic.id)
            if cached is None or cached[0] != digest:
                stale.append((topic.id, digest, text))
        if stale:
            vectors = await self.embedder.embed([t for _, _, t in stale])
            for (topic_id, digest, _), vector in zip(stale, vectors):
                cache[topic_id] = (digest, list(vector))
                await self.store.upsert_topic_embedding(org_id, topic_id, model, digest, list(vector))
        return model, {tid: vec for tid, (_, vec) in cache.items()}

    async def match(
        self, org_id: str, name: str, description: str, topics: list[IntelligenceTopic]
    ) -> Optional[TopicMatch]:
        if not topics:
            return None
        model, vectors = await self._vectors(org_id, topics)
        if model is None:
            return None
        query = await self.embedder.embed([f"{name}. {description}"[:1000]])
        if not query:
            return None
        best: Optional[TopicMatch] = None
        for topic in topics:
            vector = vectors.get(topic.id)
            if vector is None:
                continue
            score = _cosine(query[0], vector)
            if score >= self.similarity and (best is None or score > best.score):
                best = TopicMatch(topic, score, "semantic")
        return best

    async def register(self, org_id: str, topic: IntelligenceTopic) -> None:
        await self._vectors(org_id, [topic])

    async def rank_hints(
        self, org_id: str, text: str, topics: list[IntelligenceTopic], limit: int
    ) -> list[IntelligenceTopic]:
        model, vectors = await self._vectors(org_id, topics)
        if model is None or not topics:
            return []
        query = await self.embedder.embed([text[:2000]])
        if not query:
            return []
        scored = [(_cosine(query[0], vectors[t.id]), t) for t in topics if t.id in vectors]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [t for _, t in scored[:limit]]


class CompositeTopicMatcher(ITopicMatcher):
    """First matcher with an answer wins; a failing tier is skipped, never fatal."""

    def __init__(self, logger: Logger, matchers: list[ITopicMatcher]) -> None:
        self.logger = logger
        self.matchers = matchers

    async def match(
        self, org_id: str, name: str, description: str, topics: list[IntelligenceTopic]
    ) -> Optional[TopicMatch]:
        for matcher in self.matchers:
            try:
                found = await matcher.match(org_id, name, description, topics)
            except Exception:
                self.logger.warning("Topic matcher %s failed", type(matcher).__name__, exc_info=True)
                continue
            if found is not None:
                return found
        return None

    async def register(self, org_id: str, topic: IntelligenceTopic) -> None:
        for matcher in self.matchers:
            try:
                await matcher.register(org_id, topic)
            except Exception:
                self.logger.warning("Topic matcher %s could not register a topic", type(matcher).__name__, exc_info=True)

    async def rank_hints(
        self, org_id: str, text: str, topics: list[IntelligenceTopic], limit: int
    ) -> list[IntelligenceTopic]:
        # Semantic ranking first when available; lexical fills any remaining slots.
        ranked: list[IntelligenceTopic] = []
        seen: set[Optional[int]] = set()
        for matcher in reversed(self.matchers):
            try:
                hints = await matcher.rank_hints(org_id, text, topics, limit)
            except Exception:
                self.logger.warning("Topic hint ranking failed in %s", type(matcher).__name__, exc_info=True)
                continue
            for topic in hints:
                if topic.id not in seen:
                    ranked.append(topic)
                    seen.add(topic.id)
            if len(ranked) >= limit:
                break
        return ranked[:limit]


def build_topic_matcher(
    logger: Logger, store: IIntelligenceStore, embedder: Optional[ITextEmbedder] = None
) -> ITopicMatcher:
    matchers: list[ITopicMatcher] = [LexicalTopicMatcher()]
    if embedder is not None:
        matchers.append(EmbeddingTopicMatcher(logger, embedder, store))
    return CompositeTopicMatcher(logger, matchers)


def topics_of_kind(topics: list[IntelligenceTopic], kind: TopicKind) -> list[IntelligenceTopic]:
    return [t for t in topics if t.kind == kind and t.merged_into_id is None]
