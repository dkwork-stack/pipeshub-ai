"""Customer Feature Intelligence ingestion service.

Connector-agnostic core: any connector (existing pipeshub connector or a new
one) maps its data to ``CustomerSignalEvent`` / ``CustomerRevenueSnapshot``
and calls this service — directly in-process (indexing service) or via the
intake API (``app/api/routes/intelligence.py``) for out-of-process adapters.
Nothing here is aware of Freshdesk, Salesforce, or Chargebee specifically.
"""
from __future__ import annotations

from logging import Logger

from app.models.intelligence import (
    CustomerRevenueSnapshot,
    CustomerSignalEvent,
    FeatureGapMentionRecord,
)
from app.services.extraction.client import ExtractionClient
from app.services.intelligence_store.interface.intelligence_store import (
    IIntelligenceStore,
)


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

    async def ingest_revenue_snapshot(self, snapshot: CustomerRevenueSnapshot) -> None:
        await self.intelligence_store.upsert_revenue_snapshot(snapshot)
        # Revenue changed => every feature gap this customer is tied to needs
        # its score recomputed (ARR-at-stake moved).
        await self.intelligence_store.recompute_feature_gap_scores(snapshot.org_id)
        self.logger.info(
            "✅ Recorded revenue snapshot for customer '%s' (ARR=%.2f)",
            snapshot.customer_name, snapshot.arr,
        )
