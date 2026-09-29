"""Customer Feature Intelligence ingestion service.

Connector-agnostic core: any connector (existing pipeshub connector or a new
one) maps its data to ``CustomerSignalEvent`` / ``CustomerRevenueSnapshot``
and calls this service — directly in-process (indexing service) or via the
intake API (``app/api/routes/intelligence.py``) for out-of-process adapters.
Nothing here is aware of Freshdesk, Salesforce, or Chargebee specifically.

Knowledge Base uploads are the one in-process source: ``SinkOrchestrator``
calls :meth:`ingest_indexed_record` once a record is searchable, so a CSV/PDF
dropped into the UI lands in MySQL without a separate script.

ARR/MRR is revenue-only: written from allowlisted sources (file upload,
billing) via :meth:`ingest_revenue_snapshot`. Signal connectors only identify
customers.
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Mapping, Optional

from app.config.constants.arangodb import Connectors
from app.models.blocks import BlockType
from app.models.intelligence import (
    CustomerRevenueSnapshot,
    CustomerSignalEvent,
    FeatureGapMentionRecord,
    FeatureIntelligenceExtractionResult,
    IntelligenceTopic,
    PainPointMentionRecord,
    SignalSourceType,
    TaxonomyHint,
    TopicKind,
)
from app.modules.customer_intelligence.pipeline import run_pipeline
from app.modules.customer_intelligence.pipeline.context import ExtractionContext
from app.modules.customer_intelligence.pipeline.stages import match_known_customer
from app.modules.customer_intelligence.revenue import (
    is_revenue_source,
    parse_revenue_fields,
)

if TYPE_CHECKING:
    from logging import Logger

    from app.models.entities import Record
    from app.services.extraction.client import ExtractionClient
    from app.services.intelligence_store.interface.intelligence_store import (
        IIntelligenceStore,
    )

_KB_GROUP_TYPE = "KB"  # RecordGroupType.KB; kept as a literal so this module stays import-light

UPLOAD_SOURCE_CONNECTOR = "file_upload"
# Each row is one LLM call; this keeps a large export from holding an indexing
# permit for the whole RECORD_PROCESSING_TIMEOUT budget.
_DEFAULT_UPLOAD_MAX_ROWS = 200
_DEFAULT_UPLOAD_CONCURRENCY = 4


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


class CustomerIntelligenceIngestionService:
    def __init__(
        self,
        logger: Logger,
        intelligence_store: IIntelligenceStore,
        extraction_client: ExtractionClient,
    ) -> None:
        self.logger = logger
        self.intelligence_store = intelligence_store
        self.extraction_client = extraction_client

    async def ingest_signal_event(self, event: CustomerSignalEvent) -> int:
        """Run pain-point/feature-gap inference on one event and persist mentions.

        Returns the number of feature-gap + pain-point mentions written (0 is a
        valid, common outcome — most tickets/notes don't raise a product gap).
        """
        await self.intelligence_store.upsert_customer(
            event.org_id, event.external_customer_id, event.customer_name
        )

        taxonomy, hints, known_customers = await self._load_prompt_context(event.org_id)
        result = await self.extraction_client.extract_feature_intelligence(
            text=event.text,
            org_id=event.org_id,
            taxonomy=hints,
            known_customers=[name for _, name in known_customers],
        )
        ctx = await self._run_stages(
            org_id=event.org_id,
            text=event.text,
            result=result,
            taxonomy=taxonomy,
            hints=hints,
            known_customers=known_customers,
            resolved_customer_id=event.external_customer_id,
            resolved_customer_name=event.customer_name,
        )
        if ctx.resolved_customer_id and ctx.resolved_customer_name:
            event = event.model_copy(
                update={
                    "external_customer_id": ctx.resolved_customer_id,
                    "customer_name": ctx.resolved_customer_name,
                }
            )
            await self.intelligence_store.upsert_customer(
                event.org_id, event.external_customer_id, event.customer_name
            )
        return await self._write_mentions(event, ctx.result, taxonomy=ctx.taxonomy)

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

    # ------------------------------------------------------------------
    # Knowledge Base uploads (in-process, called from SinkOrchestrator)
    # ------------------------------------------------------------------

    @staticmethod
    def is_upload_record(record: "Record") -> bool:
        group_type = getattr(record.record_group_type, "value", record.record_group_type)
        return (
            record.connector_name == Connectors.KNOWLEDGE_BASE
            or group_type == _KB_GROUP_TYPE
        )

    async def ingest_indexed_record(self, record: "Record") -> int:
        """Feed a freshly indexed Knowledge Base upload into the pipeline.

        Tabular uploads (CSV/XLSX) become one event per row; anything else is
        one event for the whole document. The customer is inferred by the
        extractor; when the text names none, the file name stands in so the
        evidence is still attributed and queryable. ARR/MRR columns on a row
        are written as revenue snapshots (file_upload source only).

        Returns mentions written.
        """
        if not self.is_upload_record(record):
            return 0

        units = self._text_units(record)
        if not units:
            return 0

        semaphore = asyncio.Semaphore(
            int(os.getenv("INTELLIGENCE_UPLOAD_CONCURRENCY", _DEFAULT_UPLOAD_CONCURRENCY))
        )

        async def _one(event_id: str, text: str, cells: Mapping[str, Any] | None) -> tuple[int, bool]:
            async with semaphore:
                return await self._ingest_upload_unit(record, event_id, text, cells)

        # return_exceptions: one row's MySQL/LLM failure must not abort the
        # rest of the CSV (and must not surface as a single sink-level throw
        # that looks like the whole upload produced nothing).
        results = await asyncio.gather(
            *(_one(eid, text, cells) for eid, text, cells in units),
            return_exceptions=True,
        )
        total = 0
        revenue_writes = 0
        failures = 0
        for result in results:
            if isinstance(result, BaseException):
                failures += 1
                self.logger.warning(
                    "Upload unit failed for '%s': %s",
                    record.record_name,
                    result,
                    exc_info=result,
                )
            else:
                mentions, wrote_revenue = result
                total += mentions
                if wrote_revenue:
                    revenue_writes += 1

        # Scores are recomputed per mention; a mid-batch failure can leave the
        # org's score rows incomplete. One org-wide pass heals that cheaply.
        # Revenue snapshots skip per-row recompute during the batch for the same reason.
        if total > 0 or revenue_writes > 0:
            try:
                await self.intelligence_store.recompute_feature_gap_scores(record.org_id)
            except Exception:
                self.logger.warning(
                    "Post-upload score recompute failed for org %s",
                    record.org_id,
                    exc_info=True,
                )

        self.logger.info(
            "✅ Upload '%s': %d unit(s) analysed, %d mention(s) written, "
            "%d revenue snapshot(s) (%d unit failure(s))",
            record.record_name, len(units), total, revenue_writes, failures,
        )
        if failures and total == 0 and revenue_writes == 0:
            raise RuntimeError(
                f"Customer intelligence ingestion failed for all {failures} unit(s) of '{record.record_name}'"
            )
        return total

    def _text_units(
        self, record: "Record"
    ) -> list[tuple[str, str, Optional[Mapping[str, Any]]]]:
        """Split a record into (external_event_id, text, cells) units."""
        containers = record.block_containers
        if not containers or not containers.blocks:
            return []

        rows: list[tuple[str, str, Optional[Mapping[str, Any]]]] = []
        prose: list[str] = []
        for block in containers.blocks:
            data = block.data
            if not data:
                continue
            if block.type == BlockType.TABLE_ROW:
                text = data.get("row_natural_language_text") if isinstance(data, dict) else str(data)
                if text and text.strip():
                    row_no = data.get("row_number", block.index) if isinstance(data, dict) else block.index
                    cells = data.get("cells") if isinstance(data, dict) else None
                    if not isinstance(cells, Mapping):
                        cells = None
                    rows.append((f"{record.id}:row:{row_no}", text, cells))
            elif block.type == BlockType.TEXT:
                prose.append(data if isinstance(data, str) else str(data))

        if rows:
            max_rows = int(os.getenv("INTELLIGENCE_UPLOAD_MAX_ROWS", _DEFAULT_UPLOAD_MAX_ROWS))
            if len(rows) > max_rows:
                self.logger.warning(
                    "⚠️ Upload '%s' has %d rows; only the first %d are analysed (INTELLIGENCE_UPLOAD_MAX_ROWS)",
                    record.record_name, len(rows), max_rows,
                )
                rows = rows[:max_rows]
            return rows

        text = "\n".join(p for p in prose if p.strip())
        return [(record.id, text, None)] if text.strip() else []

    async def _ingest_upload_unit(
        self,
        record: "Record",
        event_id: str,
        text: str,
        cells: Mapping[str, Any] | None,
    ) -> tuple[int, bool]:
        revenue = parse_revenue_fields(cells if cells is not None else text)

        taxonomy, hints, known_customers = await self._load_prompt_context(record.org_id)
        result = await self.extraction_client.extract_feature_intelligence(
            text=text,
            org_id=record.org_id,
            infer_customer=True,
            taxonomy=hints,
            known_customers=[name for _, name in known_customers],
        )
        if result is None:
            result = FeatureIntelligenceExtractionResult()

        seed_name = (revenue.customer_name if revenue else None) or result.customer_name
        ctx = await self._run_stages(
            org_id=record.org_id,
            text=text,
            result=result,
            taxonomy=taxonomy,
            hints=hints,
            known_customers=known_customers,
            resolved_customer_name=seed_name,
        )

        has_mentions = bool(ctx.result.feature_gaps or ctx.result.pain_points)
        if not has_mentions and revenue is None:
            return 0, False

        customer_name = (
            (ctx.resolved_customer_name or seed_name or "").strip()
            or record.record_name
        )
        external_customer_id = (
            ctx.resolved_customer_id
            or f"{UPLOAD_SOURCE_CONNECTOR}:{_slugify(customer_name)}"
        )

        await self.intelligence_store.upsert_customer(
            record.org_id, external_customer_id, customer_name
        )

        wrote_revenue = False
        if revenue is not None:
            await self.ingest_revenue_snapshot(
                CustomerRevenueSnapshot(
                    org_id=record.org_id,
                    source_connector=UPLOAD_SOURCE_CONNECTOR,
                    external_customer_id=external_customer_id,
                    customer_name=customer_name,
                    mrr=revenue.mrr,
                    arr=revenue.arr,
                    snapshot_at=datetime.fromtimestamp(
                        (record.source_created_at or record.created_at) / 1000,
                        tz=timezone.utc,
                    ),
                ),
                recompute_scores=False,
            )
            wrote_revenue = True

        if not has_mentions:
            return 0, wrote_revenue

        event = CustomerSignalEvent(
            org_id=record.org_id,
            source_connector=UPLOAD_SOURCE_CONNECTOR,
            source_type=SignalSourceType.DOCUMENT_UPLOAD,
            external_customer_id=external_customer_id,
            customer_name=customer_name,
            external_event_id=event_id,
            text=text,
            occurred_at=datetime.fromtimestamp(
                (record.source_created_at or record.created_at) / 1000, tz=timezone.utc
            ),
            citation_url=record.weburl,
            metadata={"record_id": record.id, "record_name": record.record_name},
        )
        mentions = await self._write_mentions(event, ctx.result, taxonomy=ctx.taxonomy)
        return mentions, wrote_revenue

    # ------------------------------------------------------------------

    async def _load_prompt_context(
        self, org_id: str
    ) -> tuple[list[IntelligenceTopic], list[TaxonomyHint], list[tuple[str, str]]]:
        taxonomy = await self.intelligence_store.list_topics(org_id)
        hints = [
            TaxonomyHint(
                id=str(t.id),
                kind=t.kind,
                name=t.canonical_name,
                aliases=t.aliases or [],
                guidance=t.guidance,
            )
            for t in taxonomy
            if t.id is not None
        ]
        known_customers = await self.intelligence_store.list_customer_names(org_id)
        return taxonomy, hints, known_customers

    async def _run_stages(
        self,
        *,
        org_id: str,
        text: str,
        result: FeatureIntelligenceExtractionResult | None,
        taxonomy: list[IntelligenceTopic],
        hints: list[TaxonomyHint],
        known_customers: list[tuple[str, str]],
        resolved_customer_id: str | None = None,
        resolved_customer_name: str | None = None,
    ) -> ExtractionContext:
        ctx = ExtractionContext(
            org_id=org_id,
            text=text,
            result=result or FeatureIntelligenceExtractionResult(),
            taxonomy=taxonomy,
            taxonomy_hints=hints,
            known_customers=known_customers,
            resolved_customer_id=resolved_customer_id,
            resolved_customer_name=resolved_customer_name,
        )
        return await run_pipeline(ctx)

    async def _write_mentions(
        self,
        event: CustomerSignalEvent,
        result: FeatureIntelligenceExtractionResult | None,
        *,
        taxonomy: list[IntelligenceTopic] | None = None,
    ) -> int:
        if result is None:
            return 0
        if not result.feature_gaps and not result.pain_points:
            self.logger.debug(
                "No feature gaps or pain points inferred for event %s (customer=%s)",
                event.external_event_id, event.customer_name,
            )
            return 0

        written = 0
        existing_names = {
            (t.kind, t.canonical_name.lower()): t for t in (taxonomy or [])
        }

        for gap in result.feature_gaps:
            if (TopicKind.FEATURE_GAP, gap.feature_name.lower()) not in existing_names:
                topic = await self.intelligence_store.upsert_topic(
                    IntelligenceTopic(
                        org_id=event.org_id,
                        kind=TopicKind.FEATURE_GAP,
                        canonical_name=gap.feature_name,
                    )
                )
                existing_names[(TopicKind.FEATURE_GAP, gap.feature_name.lower())] = topic

            mention = FeatureGapMentionRecord(
                org_id=event.org_id,
                external_customer_id=event.external_customer_id,
                feature_name=gap.feature_name,
                description=gap.description,
                confidence=gap.confidence,
                excerpt=gap.excerpt,
                source_connector=event.source_connector,
                source_type=event.source_type,
                external_event_id=event.external_event_id,
                citation_url=event.citation_url,
                occurred_at=event.occurred_at,
            )
            await self.intelligence_store.upsert_feature_gap_mention(mention)
            written += 1

        for pain in result.pain_points:
            if (TopicKind.PAIN_POINT, pain.summary.lower()) not in existing_names:
                topic = await self.intelligence_store.upsert_topic(
                    IntelligenceTopic(
                        org_id=event.org_id,
                        kind=TopicKind.PAIN_POINT,
                        canonical_name=pain.summary,
                    )
                )
                existing_names[(TopicKind.PAIN_POINT, pain.summary.lower())] = topic

            mention = PainPointMentionRecord(
                org_id=event.org_id,
                external_customer_id=event.external_customer_id,
                topic_name=pain.summary,
                summary=pain.summary,
                sentiment=pain.sentiment,
                confidence=pain.confidence,
                excerpt=pain.excerpt,
                source_connector=event.source_connector,
                source_type=event.source_type,
                external_event_id=event.external_event_id,
                citation_url=event.citation_url,
                occurred_at=event.occurred_at,
            )
            await self.intelligence_store.upsert_pain_point_mention(mention)
            written += 1

        self.logger.info(
            "✅ Ingested %d mention(s) for customer '%s' (event %s)",
            written, event.customer_name, event.external_event_id,
        )
        return written
