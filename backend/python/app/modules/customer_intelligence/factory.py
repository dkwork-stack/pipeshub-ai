"""Composition root for Customer Feature Intelligence.

The one place that decides which implementations back each seam (matcher,
embedder, redactor, dispatcher), so the indexing container, the intelligence
worker and tests assemble the pipeline the same way.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional

from app.modules.customer_intelligence.ingestion_service import (
    CustomerIntelligenceIngestionService,
)
from app.modules.customer_intelligence.matching.embedder import ConfiguredTextEmbedder
from app.modules.customer_intelligence.matching.matcher import build_topic_matcher
from app.modules.customer_intelligence.signals.dispatch import (
    BrokerSignalDispatcher,
    InlineSignalDispatcher,
    dispatch_mode,
)
from app.modules.customer_intelligence.signals.feeder import IntelligenceRecordFeeder
from app.modules.customer_intelligence.signals.redaction import create_redactor

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger

    from app.config.configuration_service import ConfigurationService
    from app.modules.customer_intelligence.signals.envelope import SignalEnvelope
    from app.services.extraction.client import ExtractionClient
    from app.services.intelligence_store.interface.intelligence_store import (
        IIntelligenceStore,
    )


def _flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() not in {"0", "false", "no", "off"}


def create_analysis_service(
    logger: Logger,
    store: IIntelligenceStore,
    extraction_client: ExtractionClient,
    config_service: ConfigurationService,
) -> CustomerIntelligenceIngestionService:
    embedder = ConfiguredTextEmbedder(logger, config_service) if _flag("INTELLIGENCE_TOPIC_EMBEDDINGS", default=True) else None
    return CustomerIntelligenceIngestionService(
        logger=logger,
        intelligence_store=store,
        extraction_client=extraction_client,
        topic_matcher=build_topic_matcher(logger, store, embedder),
        redactor=create_redactor(),
    )


class _LazyAnalyzer:
    """Resolves the analysis service (and so MySQL) on first use, so inline
    mode never blocks indexing start-up on the intelligence store."""

    def __init__(self, provider: Callable[[], Any]) -> None:
        self._provider = provider
        self._service: Optional[CustomerIntelligenceIngestionService] = None

    async def analyze(self, envelope: SignalEnvelope) -> int:
        if self._service is None:
            self._service = await self._provider()
        return await self._service.analyze(envelope)


async def create_record_feeder(
    logger: Logger,
    config_service: ConfigurationService,
    analysis_service_provider: Callable[[], Any],
) -> IntelligenceRecordFeeder:
    mode = dispatch_mode()
    if mode == "broker":
        dispatcher = BrokerSignalDispatcher(logger, config_service)
    elif mode == "inline":
        dispatcher = InlineSignalDispatcher(logger, _LazyAnalyzer(analysis_service_provider))
    else:
        raise ValueError(f"Unsupported INTELLIGENCE_DISPATCH_MODE '{mode}' (expected 'broker' or 'inline')")
    logger.info("Customer Feature Intelligence dispatch mode: %s", mode)
    return IntelligenceRecordFeeder(logger, dispatcher)
