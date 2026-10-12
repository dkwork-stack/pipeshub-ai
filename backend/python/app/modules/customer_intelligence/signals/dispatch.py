"""How SignalEnvelopes reach the analysis pipeline.

``broker`` (production): publish to the ``intelligence-events`` topic keyed by
org id and let ``app.intelligence_worker_main`` analyse them — indexing never
waits on an LLM. ``inline`` (single-process dev, tests): analyse in the
caller's process, bounded by a semaphore.
"""
from __future__ import annotations

import asyncio
import os
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol

from app.modules.customer_intelligence.signals.envelope import (
    SIGNAL_EVENT_TYPE,
    SignalEnvelope,
)
from app.services.messaging.config import Topic
from app.utils.time_conversion import get_epoch_timestamp_in_ms

if TYPE_CHECKING:
    from logging import Logger

    from app.config.configuration_service import ConfigurationService
    from app.services.messaging.interface.producer import IMessagingProducer


class ISignalAnalyzer(Protocol):
    async def analyze(self, envelope: SignalEnvelope) -> int: ...


class ISignalDispatcher(ABC):
    @abstractmethod
    async def dispatch(self, envelopes: list[SignalEnvelope]) -> int:
        """Hand envelopes to the pipeline; returns how many were accepted."""

    async def close(self) -> None:
        """Release resources (producers)."""


class InlineSignalDispatcher(ISignalDispatcher):
    def __init__(self, logger: Logger, analyzer: ISignalAnalyzer, concurrency: int | None = None) -> None:
        self.logger = logger
        self.analyzer = analyzer
        self.concurrency = concurrency or int(os.getenv("INTELLIGENCE_WORKER_CONCURRENCY", "4"))

    async def dispatch(self, envelopes: list[SignalEnvelope]) -> int:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def _one(envelope: SignalEnvelope) -> None:
            async with semaphore:
                await self.analyzer.analyze(envelope)

        results = await asyncio.gather(*(_one(e) for e in envelopes), return_exceptions=True)
        failures = [r for r in results if isinstance(r, BaseException)]
        for failure in failures:
            self.logger.warning("Inline intelligence analysis failed: %s", failure, exc_info=failure)
        if failures and len(failures) == len(envelopes):
            raise RuntimeError(f"Intelligence analysis failed for all {len(envelopes)} envelope(s)")
        return len(envelopes) - len(failures)


class BrokerSignalDispatcher(ISignalDispatcher):
    """Publishes envelopes; one producer per event loop (producers are loop-bound,
    and indexing runs records on a worker-thread loop)."""

    def __init__(self, logger: Logger, config_service: ConfigurationService, topic: str = Topic.INTELLIGENCE_EVENTS.value) -> None:
        self.logger = logger
        self.config_service = config_service
        self.topic = topic
        self._producers: dict[asyncio.AbstractEventLoop, IMessagingProducer] = {}
        self._lock = threading.Lock()

    async def _producer(self) -> IMessagingProducer:
        from app.services.messaging.messaging_factory import (
            MessagingFactory,
        )
        from app.services.messaging.utils import MessagingUtils

        loop = asyncio.get_running_loop()
        with self._lock:
            producer = self._producers.get(loop)
        if producer is not None:
            return producer
        config = await MessagingUtils.create_producer_config_from_service(
            self.config_service, client_id="intelligence_signal_producer"
        )
        producer = MessagingFactory.create_producer(logger=self.logger, config=config)
        await producer.initialize()
        with self._lock:
            existing = self._producers.setdefault(loop, producer)
        if existing is not producer:
            await producer.cleanup()
        return existing

    async def dispatch(self, envelopes: list[SignalEnvelope]) -> int:
        if not envelopes:
            return 0
        producer = await self._producer()
        now = get_epoch_timestamp_in_ms()
        # Keyed by org: one org's envelopes are consumed in order by one worker,
        # which makes topic creation race-free without distributed locks.
        messages = [
            (e.org_id, {"eventType": SIGNAL_EVENT_TYPE, "payload": e.model_dump(mode="json"), "timestamp": now})
            for e in envelopes
        ]
        results = await producer.send_messages(self.topic, messages)
        sent = sum(1 for ok in results if ok)
        if sent < len(envelopes):
            raise RuntimeError(f"Published {sent}/{len(envelopes)} intelligence envelope(s) to '{self.topic}'")
        return sent

    async def close(self) -> None:
        with self._lock:
            producers = list(self._producers.values())
            self._producers.clear()
        for producer in producers:
            try:
                await producer.cleanup()
            except Exception:
                self.logger.debug("Error closing intelligence producer", exc_info=True)


def dispatch_mode() -> str:
    return os.getenv("INTELLIGENCE_DISPATCH_MODE", "inline").strip().lower()
