"""Customer Feature Intelligence ingestion service.

Connector-agnostic core: any connector (existing pipeshub connector or a new
one) maps its data to ``CustomerSignalEvent`` / ``CustomerRevenueSnapshot``
and calls this service — directly in-process (indexing service) or via the
intake API (``app/api/routes/intelligence.py``) for out-of-process adapters.
Nothing here is aware of Freshdesk, Salesforce, or Chargebee specifically.

Knowledge Base uploads are the one in-process source: ``SinkOrchestrator``
calls :meth:`ingest_indexed_record` once a record is searchable, so a CSV/PDF
dropped into the UI lands in MySQL without a separate script.
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.config.constants.arangodb import Connectors
from app.models.blocks import BlockType
from app.models.intelligence import (
    CustomerRevenueSnapshot,
    CustomerSignalEvent,
    FeatureGapMentionRecord,
    FeatureIntelligenceExtractionResult,
    SignalSourceType,
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

        Returns the number of feature-gap mentions written (0 is a valid,
        common outcome — most tickets/notes don't raise a product gap).
        """
        await self.intelligence_store.upsert_customer(
            event.org_id, event.external_customer_id, event.customer_name
        )

        result = await self.extraction_client.extract_feature_intelligence(
            text=event.text, org_id=event.org_id
        )
        return await self._write_mentions(event, result)

    async def ingest_revenue_snapshot(self, snapshot: CustomerRevenueSnapshot) -> None:
        await self.intelligence_store.upsert_revenue_snapshot(snapshot)
        # Revenue changed => every feature gap this customer is tied to needs
        # its score recomputed (ARR-at-stake moved).
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
        evidence is still attributed and queryable. Returns mentions written.
        """
        if not self.is_upload_record(record):
            return 0

        units = self._text_units(record)
        if not units:
            return 0

        semaphore = asyncio.Semaphore(
            int(os.getenv("INTELLIGENCE_UPLOAD_CONCURRENCY", _DEFAULT_UPLOAD_CONCURRENCY))
        )

        async def _one(event_id: str, text: str) -> int:
            async with semaphore:
                return await self._ingest_upload_unit(record, event_id, text)

        written = await asyncio.gather(*(_one(eid, text) for eid, text in units))
        total = sum(written)
        self.logger.info(
            "✅ Upload '%s': %d unit(s) analysed, %d feature-gap mention(s) written",
            record.record_name, len(units), total,
        )
        return total

    def _text_units(self, record: "Record") -> list[tuple[str, str]]:
        """Split a record into (external_event_id, text) units."""
        containers = record.block_containers
        if not containers or not containers.blocks:
            return []

        rows: list[tuple[str, str]] = []
        prose: list[str] = []
        for block in containers.blocks:
            data = block.data
            if not data:
                continue
            if block.type == BlockType.TABLE_ROW:
                text = data.get("row_natural_language_text") if isinstance(data, dict) else str(data)
                if text and text.strip():
                    row_no = data.get("row_number", block.index) if isinstance(data, dict) else block.index
                    rows.append((f"{record.id}:row:{row_no}", text))
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
        return [(record.id, text)] if text.strip() else []

    async def _ingest_upload_unit(self, record: "Record", event_id: str, text: str) -> int:
        result = await self.extraction_client.extract_feature_intelligence(
            text=text, org_id=record.org_id, infer_customer=True
        )
        if result is None or not result.feature_gaps:
            return 0

        customer_name = (result.customer_name or "").strip() or record.record_name
        event = CustomerSignalEvent(
            org_id=record.org_id,
            source_connector=UPLOAD_SOURCE_CONNECTOR,
            source_type=SignalSourceType.DOCUMENT_UPLOAD,
            external_customer_id=f"{UPLOAD_SOURCE_CONNECTOR}:{_slugify(customer_name)}",
            customer_name=customer_name,
            external_event_id=event_id,
            text=text,
            occurred_at=datetime.fromtimestamp(
                (record.source_created_at or record.created_at) / 1000, tz=timezone.utc
            ),
            citation_url=record.weburl,
            metadata={"record_id": record.id, "record_name": record.record_name},
        )
        await self.intelligence_store.upsert_customer(
            event.org_id, event.external_customer_id, event.customer_name
        )
        return await self._write_mentions(event, result)

    # ------------------------------------------------------------------

    async def _write_mentions(
        self,
        event: CustomerSignalEvent,
        result: FeatureIntelligenceExtractionResult | None,
    ) -> int:
        if result is None or not result.feature_gaps:
            self.logger.debug(
                "No feature gaps inferred for event %s (customer=%s)",
                event.external_event_id, event.customer_name,
            )
            return 0

        written = 0
        for gap in result.feature_gaps:
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

        self.logger.info(
            "✅ Ingested %d feature-gap mention(s) for customer '%s' (event %s)",
            written, event.customer_name, event.external_event_id,
        )
        return written
