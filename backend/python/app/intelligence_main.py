"""Customer Feature Intelligence portal service entry point (port 8094).

Read-only FastAPI microservice that serves the portal UI and AI agents from
the MySQL intelligence store: overview, revenue-ranked feature gaps with
citations, and per-customer insights. Auth is the platform's own
``authMiddleware`` (same session JWT / service tokens as every other service);
the Node gateway proxies ``/api/v1/intelligence-portal/*`` here.
"""
import asyncio
import logging
import os
import signal
import sys
import types
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middlewares.auth import authMiddleware
from app.api.routes.intelligence_portal.router import router as portal_router
from app.containers.intelligence import IntelligenceAppContainer, initialize_container

logger = logging.getLogger("intelligence_main")


def handle_sigterm(signum: int, frame: types.FrameType | None) -> None:
    logger.info("Received signal %s; shutting down gracefully", signum)
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

container = IntelligenceAppContainer.init("intelligence_service")
container_lock = asyncio.Lock()


async def _get_initialized_container() -> IntelligenceAppContainer:
    if not hasattr(_get_initialized_container, "initialized"):
        async with container_lock:
            if not hasattr(_get_initialized_container, "initialized"):
                await initialize_container(container)
                setattr(_get_initialized_container, "initialized", True)
    return container


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app_container = await _get_initialized_container()
    app.container = app_container  # type: ignore[attr-defined]
    app_logger = app_container.logger()
    app_logger.info("✅ Intelligence Portal Service started")

    yield

    app_logger.info("🔄 Intelligence Portal Service shutting down")
    try:
        await app_container.shutdown_resources()
    except Exception:
        app_logger.warning("Error while shutting down resources", exc_info=True)


app = FastAPI(
    title="PipesHub Customer Feature Intelligence API",
    description="Read-only API over customer pain points, feature gaps and revenue evidence",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

EXCLUDE_PATHS = ["/health"]


@app.middleware("http")
async def authenticate_requests(request: Request, call_next) -> JSONResponse:  # noqa: ANN001
    if any(request.url.path.startswith(path) for path in EXCLUDE_PATHS):
        return await call_next(request)
    try:
        authenticated_request = await authMiddleware(request)
        return await call_next(authenticated_request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except Exception:
        container.logger().exception(
            "Unhandled exception while processing %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portal_router)


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse(content={"status": "healthy", "service": "intelligence"})


if __name__ == "__main__":
    port = int(os.getenv("INTELLIGENCE_SERVICE_PORT", "8094"))
    uvicorn.run(
        "app.intelligence_main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
