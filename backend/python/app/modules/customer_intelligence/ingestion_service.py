"""Customer Feature Intelligence analysis service.

Connector-agnostic core: every source arrives as a ``SignalEnvelope`` — from
the intelligence worker (broker mode), from the indexing process (inline
mode) or from the intake API. Nothing here knows which connector produced it.

Per envelope: redact PII → extract (LLM, via the extraction service) →
verify quotes → dedupe → [per-org critical section: classify against known
topics → resolve customer → write mentions → recompute touched scores].
Only the short critical section is serialised per org, so extraction for many
envelopes of one org still runs concurrently.

ARR/MRR is revenue-only: written from allowlisted sources (file upload,
billing) via :meth:`ingest_revenue_snapshot`. Signal connectors only identify
customers.
"""
from __future__ import annotations

import asyncio
import re
import threading
from typing import TYPE_CHECKING, Optional

from app.models.intelligence import (
    CustomerRevenueSnapshot,
    CustomerSignalEvent,
    FeatureGapMentionRecord,
    FeatureIntelligenceExtractionResult,
    IntelligenceTopic,
    PainPointMentionRecord,
    TaxonomyHint,
    TopicKind,
)
from app.modules.customer_intelligence.matching.matcher import (
    ITopicMatcher,
    LexicalTopicMatcher,
)
from app.modules.customer_intelligence.pipeline import run_pipeline
from app.modules.customer_intelligence.pipeline.context import ExtractionContext
from app.modules.customer_intelligence.pipeline.stages import (
    CanonicalizeToTopic,
    DedupeWithinEvent,
    ResolveCustomer,
    VerifyExcerpts,
    match_known_customer,
)
from app.modules.customer_intelligence.revenue import (
    RevenueFields,
    is_revenue_source,
    parse_revenue_fields,
)
from app.modules.customer_intelligence.signals.envelope import SignalEnvelope
from app.modules.customer_intelligence.signals.normalizers import (
    UPLOAD_SOURCE_CONNECTOR,
)
from app.modules.customer_intelligence.signals.redaction import (
    IPiiRedactor,
    NoopRedactor,
)

if TYPE_CHECKING:
    from logging import Logger

    from app.services.extraction.client import ExtractionClient
    from app.services.intelligence_store.interface.intelligence_store import (
        IIntelligenceStore,
    )

__all__ = ["UPLOAD_SOURCE_CONNECTOR", "CustomerIntelligenceIngestionService"]

UNATTRIBUTED_CUSTOMER = "Unattributed"
_PROMPT_TOPIC_HINTS = 60


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


class CustomerIntelligenceIngestionService:
    def __init__(
        self,
        logger: Logger,
        intelligence_store: IIntelligenceStore,
        extraction_client: ExtractionClient,
        topic_matcher: Optional[ITopicMatcher] = None,
        redactor: Optional[IPiiRedactor] = None,
    ) -> None:
        self.logger = logger
        self.intelligence_store = intelligence_store
        self.extraction_client = extraction_client
        self.topic_matcher = topic_matcher or LexicalTopicMatcher()
        self.redactor = redactor or NoopRedactor()
        self._locks: dict[tuple[asyncio.AbstractEventLoop, str], asyncio.Lock] = {}
        self._locks_guard = threading.Lock()

    # ------------------------------------------------------------ entry points

    async def ingest_signal_event(self, event: CustomerSignalEvent) -> int:
        """Intake API: an event whose customer is already known."""
        await self.intelligence_store.upsert_customer(
            event.org_id, event.external_customer_id, event.customer_name
        )
        return await self.analyze(SignalEnvelope.from_event(event))

    async def analyze(self, envelope: SignalEnvelope) -> int:
        """Run one envelope through the pipeline; returns mentions written.

        0 is a valid, common outcome — most tickets don't raise a product gap.
        """
        envelope = self._redacted(envelope)
        text = envelope.text
        revenue = (
            parse_revenue_fields(envelope.cells if envelope.cells is not None else text)
            if is_revenue_source(envelope.source_connector)
            else None
        )

        taxonomy, known_customers = await self._prompt_context(envelope.org_id)
        hints = await self._topic_hints(envelope.org_id, text, taxonomy)
        result = await self.extraction_client.extract_feature_intelligence(
            text=text,
            org_id=envelope.org_id,
            infer_customer=envelope.infer_customer,
            taxonomy=hints,
            known_customers=[name for _, name in known_customers] if envelope.infer_customer else [],
        ) or FeatureIntelligenceExtractionResult()

        ctx = await run_pipeline(
            self._context(envelope, text, result, taxonomy, known_customers),
            [VerifyExcerpts(), DedupeWithinEvent()],
        )
        if ctx.dropped:
            self.logger.debug(
                "Envelope %s: dropped %s", envelope.external_event_id,
                [(d.code.value, d.name) for d in ctx.dropped],
            )
        has_mentions = bool(ctx.result.feature_gaps or ctx.result.pain_points)
        if not has_mentions and revenue is None:
            return 0

        async with self._org_lock(envelope.org_id):
            # Topics may have been created by other envelopes while this one was
            # with the LLM; classify against the current set.
            taxonomy, known_customers = await self._prompt_context(envelope.org_id)
            ctx.taxonomy = taxonomy
            ctx.known_customers = known_customers
            if revenue is not None and revenue.customer_name and not ctx.resolved_customer_name:
                # A named customer column beats the LLM's reading of the row.
                ctx.resolved_customer_name = revenue.customer_name
            ctx = await run_pipeline(ctx, [CanonicalizeToTopic(self.topic_matcher), ResolveCustomer()])

            customer_id, customer_name = self._attribution(envelope, ctx, revenue)
            await self.intelligence_store.upsert_customer(envelope.org_id, customer_id, customer_name)

            if revenue is not None:
                await self.ingest_revenue_snapshot(
                    CustomerRevenueSnapshot(
                        org_id=envelope.org_id,
                        source_connector=envelope.source_connector,
                        external_customer_id=customer_id,
                        customer_name=customer_name,
                        mrr=revenue.mrr,
                        arr=revenue.arr,
                        snapshot_at=envelope.occurred_at,
                    ),
                    recompute_scores=not has_mentions,
                )
            if not has_mentions:
                return 0

            for topic_id, alias in ctx.alias_proposals:
                await self.intelligence_store.add_topic_alias(envelope.org_id, topic_id, alias)
            return await self._write_mentions(envelope, customer_id, ctx, result)

    async def ingest_revenue_snapshot(
        self,
        snapshot: CustomerRevenueSnapshot,
        *,
        recompute_scores: bool = True,
    ) -> None:
        """Persist ARR/MRR from an allowlisted revenue source only.

        Remaps ``external_customer_id`` onto an existing customer when the
        name fuzzy-matches one already known from any connector.
        """
        if not is_revenue_source(snapshot.source_connector):
            raise ValueError(
                f"source_connector '{snapshot.source_connector}' is not a revenue source; "
                "ARR/MRR may only come from file upload or billing connectors"
            )

        known = await self.intelligence_store.list_customer_names(snapshot.org_id)
        matched = match_known_customer(snapshot.customer_name, known)
        if matched:
            ext_id, name = matched
            snapshot = snapshot.model_copy(
                update={"external_customer_id": ext_id, "customer_name": name}
            )
        elif not (snapshot.customer_name or "").strip():
            snapshot = snapshot.model_copy(
                update={"customer_name": snapshot.external_customer_id}
            )

        await self.intelligence_store.upsert_revenue_snapshot(snapshot)
        if recompute_scores:
            await self.intelligence_store.recompute_feature_gap_scores(snapshot.org_id)
        self.logger.info(
            "✅ Recorded revenue snapshot for customer '%s' (ARR=%.2f)",
            snapshot.customer_name, snapshot.arr,
        )

    # ----------------------------------------------------------------- helpers

    def _org_lock(self, org_id: str) -> asyncio.Lock:
        # asyncio locks are loop-bound; indexing (inline mode) runs records on
        # a worker-thread loop distinct from the API loop.
        key = (asyncio.get_running_loop(), org_id)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = asyncio.Lock()
            return lock

    def _redacted(self, envelope: SignalEnvelope) -> SignalEnvelope:
        if isinstance(self.redactor, NoopRedactor):
            return envelope
        # Role labels carry the context the LLM needs; personal names do not.
        turns = [t.model_copy(update={"text": self.redactor.redact(t.text), "author": None}) for t in envelope.turns]
        cells = (
            {k: self.redactor.redact(v) if isinstance(v, str) else v for k, v in envelope.cells.items()}
            if envelope.cells
            else envelope.cells
        )
        return envelope.model_copy(update={"turns": turns, "cells": cells})

    async def _prompt_context(
        self, org_id: str
    ) -> tuple[list[IntelligenceTopic], list[tuple[str, str]]]:
        taxonomy = await self.intelligence_store.list_topics(org_id)
        known_customers = await self.intelligence_store.list_customer_names(org_id)
        return taxonomy, known_customers

    async def _topic_hints(
        self, org_id: str, text: str, taxonomy: list[IntelligenceTopic]
    ) -> list[TaxonomyHint]:
        """The org's topics most relevant to this text, so the prompt stays
        bounded no matter how large the taxonomy grows."""
        hints: list[TaxonomyHint] = []
        for kind in (TopicKind.FEATURE_GAP, TopicKind.PAIN_POINT):
            topics = [t for t in taxonomy if t.kind == kind and t.id is not None]
            if not topics:
                continue
            ranked = topics if len(topics) <= _PROMPT_TOPIC_HINTS // 2 else await self.topic_matcher.rank_hints(
                org_id, text, topics, _PROMPT_TOPIC_HINTS // 2
            )
            hints.extend(
                TaxonomyHint(id=str(t.id), kind=t.kind, name=t.canonical_name, aliases=t.aliases, guidance=t.guidance)
                for t in ranked
            )
        return hints

    @staticmethod
    def _context(
        envelope: SignalEnvelope,
        text: str,
        result: FeatureIntelligenceExtractionResult,
        taxonomy: list[IntelligenceTopic],
        known_customers: list[tuple[str, str]],
    ) -> ExtractionContext:
        return ExtractionContext(
            org_id=envelope.org_id,
            text=text,
            result=result,
            taxonomy=taxonomy,
            known_customers=known_customers,
            resolved_customer_id=envelope.customer_external_id,
            resolved_customer_name=envelope.customer_name,
        )

    @staticmethod
    def _attribution(
        envelope: SignalEnvelope, ctx: ExtractionContext, revenue: Optional[RevenueFields]
    ) -> tuple[str, str]:
        """Who the evidence belongs to: known id → revenue row's customer →
        LLM-inferred → source fallback (file name / email domain) → Unattributed."""
        if envelope.customer_external_id and not ctx.resolved_customer_id:
            return envelope.customer_external_id, envelope.customer_name or envelope.customer_external_id
        revenue_name = revenue.customer_name if revenue is not None else None
        name = (
            (ctx.resolved_customer_name or "").strip()
            or (revenue_name or "").strip()
            or (envelope.customer_name_fallback or "").strip()
            or UNATTRIBUTED_CUSTOMER
        )
        external_id = ctx.resolved_customer_id or f"{envelope.source_connector}:{_slugify(name)}"
        return external_id, name

    async def _write_mentions(
        self,
        envelope: SignalEnvelope,
        customer_id: str,
        ctx: ExtractionContext,
        result: FeatureIntelligenceExtractionResult,
    ) -> int:
        topics = {(t.kind, t.canonical_name.lower()): t for t in ctx.taxonomy}

        async def topic_for(kind: TopicKind, name: str, description: Optional[str]) -> IntelligenceTopic:
            topic = topics.get((kind, name.lower()))
            if topic is None:
                topic = await self.intelligence_store.upsert_topic(
                    IntelligenceTopic(org_id=envelope.org_id, kind=kind, canonical_name=name, description=description)
                )
                topics[(kind, name.lower())] = topic
                await self.topic_matcher.register(envelope.org_id, topic)
            return topic

        common = {
            "org_id": envelope.org_id,
            "external_customer_id": customer_id,
            "source_connector": envelope.source_connector,
            "source_type": envelope.source_type,
            "external_event_id": envelope.external_event_id,
            "citation_url": envelope.citation_url,
            "occurred_at": envelope.occurred_at,
            "source_record_id": envelope.source_record_id,
            "extraction_model": result.model,
            "prompt_version": result.prompt_version,
        }

        written = 0
        feature_names: list[str] = []
        for gap in ctx.result.feature_gaps:
            topic = await topic_for(TopicKind.FEATURE_GAP, gap.feature_name, gap.description)
            await self.intelligence_store.upsert_feature_gap_mention(
                FeatureGapMentionRecord(
                    **common,
                    **gap.attributes(),
                    feature_name=topic.canonical_name,
                    description=gap.description,
                    confidence=gap.confidence,
                    excerpt=gap.excerpt,
                    topic_id=topic.id,
                ),
                recompute=False,
            )
            feature_names.append(topic.canonical_name)
            written += 1

        for pain in ctx.result.pain_points:
            topic = await topic_for(TopicKind.PAIN_POINT, pain.summary, None)
            await self.intelligence_store.upsert_pain_point_mention(
                PainPointMentionRecord(
                    **common,
                    **pain.attributes(),
                    topic_name=topic.canonical_name,
                    summary=pain.summary,
                    confidence=pain.confidence,
                    excerpt=pain.excerpt,
                    topic_id=topic.id,
                )
            )
            written += 1

        if feature_names:
            await self.intelligence_store.recompute_feature_gap_scores(envelope.org_id, feature_names)
        self.logger.info(
            "✅ %d mention(s) for customer '%s' from %s event %s",
            written, customer_id, envelope.source_connector, envelope.external_event_id,
        )
        return written
