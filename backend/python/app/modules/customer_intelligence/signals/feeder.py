"""Indexing-side entry point: turn a freshly indexed record into envelopes and dispatch them.

Cheap and deterministic — no LLM, no store access — so it can run inline in
``SinkOrchestrator`` without slowing indexing. Analysis happens wherever the
dispatcher sends the envelopes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.modules.customer_intelligence.signals.normalizers import (
    SignalNormalizer,
    default_normalizers,
    normalize_record,
)
from app.modules.customer_intelligence.signals.policy import IntelligenceSourcePolicy

if TYPE_CHECKING:
    from logging import Logger

    from app.models.entities import Record
    from app.modules.customer_intelligence.signals.dispatch import ISignalDispatcher


class IntelligenceRecordFeeder:
    def __init__(
        self,
        logger: Logger,
        dispatcher: ISignalDispatcher,
        policy: Optional[IntelligenceSourcePolicy] = None,
        normalizers: Optional[list[SignalNormalizer]] = None,
    ) -> None:
        self.logger = logger
        self.dispatcher = dispatcher
        self.policy = policy or IntelligenceSourcePolicy.from_env()
        self.normalizers = normalizers or default_normalizers(logger)

    def accepts(self, record: Record) -> bool:
        return self.policy.accepts(record)

    async def feed(self, record: Record) -> int:
        """Returns envelopes dispatched (0 when the record carries no usable text)."""
        if not self.accepts(record):
            return 0
        envelopes = normalize_record(record, self.normalizers)
        if not envelopes:
            return 0
        dispatched = await self.dispatcher.dispatch(envelopes)
        self.logger.info(
            "📨 Customer intelligence: %d envelope(s) from '%s' (%s)",
            dispatched, record.record_name, envelopes[0].source_connector,
        )
        return dispatched
