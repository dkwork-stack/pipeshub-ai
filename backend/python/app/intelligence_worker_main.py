"""Customer Feature Intelligence worker (health on port 8095).

Consumes SignalEnvelopes from the ``intelligence-events`` topic and runs each
through ``CustomerIntelligenceIngestionService.analyze``. Scale it on its own:
more replicas, or ``INTELLIGENCE_WORKER_CONCURRENCY`` consumers per replica.
Indexing publishes envelopes here when ``INTELLIGENCE_DISPATCH_MODE=broker``.

From source: ``python -m app.intelligence_worker_main``.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.containers.intelligence_worker import IntelligenceWorkerContainer
from app.modules.customer_intelligence.worker import build_signal_handler
from app.services.messaging.messaging_factory import MessagingFactory
from app.services.messaging.utils import MessagingUtils

if TYPE_CHECKING:
    import types
    from collections.abc import AsyncGenerator

    from app.services.messaging.interface.consumer import IMessagingConsumer

logger = logging.getLogger("intelligence_worker_main")


def handle_sigterm(signum: int, frame: types.FrameType | None) -> None:
    logger.info("Received signal %s; shutting down gracefully", signum)
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

container = IntelligenceWorkerContainer.init("intelligence_worker")


async def start_consumers(app_container: IntelligenceWorkerContainer) -> list[IMessagingConsumer]:
    log = app_container.logger()
    redis_config = await MessagingUtils._get_redis_config(app_container)
    retry_manager = MessagingFactory.create_retry_manager(log, redis_config)
    await retry_manager.initialize()

    handler = build_signal_handler(log, app_container.analysis_service)
    concurrency = max(1, int(os.getenv("INTELLIGENCE_WORKER_CONCURRENCY", "4")))
    consumers: list[IMessagingConsumer] = []
    try:
        for i in range(concurrency):
            config = await MessagingUtils.create_intelligence_consumer_config(app_container)
            # Distinct, stable member names within the shared group.
            config.client_id = f"{config.client_id}-{i}"
            consumer = MessagingFactory.create_consumer(logger=log, config=config, retry_manager=retry_manager)
            await consumer.start(handler)
            consumers.append(consumer)
    except Exception:
        for consumer in consumers:
            await consumer.stop()
        raise
    log.info("✅ Intelligence worker consuming with %d consumer(s)", len(consumers))
    return consumers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log = container.logger()
    try:
        await container.intelligence_store()
    except Exception:
        log.warning("Intelligence store unavailable at start-up; envelopes will retry until it is back", exc_info=True)
    consumers = await start_consumers(container)
    app.state.consumers = consumers
    yield
    for consumer in consumers:
        try:
            await consumer.stop()
        except Exception:
            log.warning("Error stopping intelligence consumer", exc_info=True)
    await container.shutdown_resources()


app = FastAPI(
    title="PipesHub Customer Feature Intelligence Worker",
    description="Consumes customer-signal envelopes and writes pain points / feature gaps",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> JSONResponse:
    consumers = getattr(app.state, "consumers", [])
    running = sum(1 for c in consumers if c.is_running())
    healthy = bool(consumers) and running == len(consumers)
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "healthy" if healthy else "degraded",
            "service": "intelligence_worker",
            "consumers": running,
            "broker": MessagingUtils.get_broker_type().value,
        },
    )


if __name__ == "__main__":
    uvicorn.run(
        "app.intelligence_worker_main:app",
        host="0.0.0.0",
        port=int(os.getenv("INTELLIGENCE_WORKER_PORT", "8095")),
        log_level="info",
    )
