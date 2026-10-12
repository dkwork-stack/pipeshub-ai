"""Broker message handling for the intelligence worker, kept free of process wiring so it is testable."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.modules.customer_intelligence.signals.envelope import (
    SIGNAL_EVENT_TYPE,
    SignalEnvelope,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from logging import Logger

    from app.modules.customer_intelligence.signals.dispatch import ISignalAnalyzer
    from app.services.messaging.config import MessageHandler, StreamMessage


def build_signal_handler(logger: Logger, get_analyzer: Callable[[], Awaitable[ISignalAnalyzer]]) -> MessageHandler:
    """True settles the message; False asks the consumer to retry (then dead-letter)."""

    async def handle(message: StreamMessage) -> bool:
        if message.eventType != SIGNAL_EVENT_TYPE:
            logger.debug("Skipping non-intelligence event %s", message.eventType)
            return True
        try:
            envelope = SignalEnvelope.model_validate(message.payload)
        except ValidationError:
            # A malformed envelope will never succeed; settle it instead of retrying.
            logger.error("Dropping malformed intelligence envelope", exc_info=True)
            return True
        try:
            analyzer: Any = await get_analyzer()
            await analyzer.analyze(envelope)
            return True
        except Exception:
            logger.warning(
                "Analysis failed for %s (org %s)%s",
                envelope.external_event_id, envelope.org_id,
                "; giving up" if message.is_final_failure else "; will retry",
                exc_info=True,
            )
            return False

    return handle
