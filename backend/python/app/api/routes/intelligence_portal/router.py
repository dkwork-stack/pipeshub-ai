"""Composes the intelligence portal API under ``/api/v1/intelligence-portal``.

Read-only by design: the write/intake surface stays on the indexing service
(``app/api/routes/intelligence.py``). Every route requires a verified token
(``authMiddleware`` in ``app.intelligence_main``) and the ``intelligence:read``
scope for service tokens.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.intelligence_portal import customers, feature_gaps, overview

API_PREFIX = "/api/v1/intelligence-portal"

router = APIRouter(prefix=API_PREFIX)
router.include_router(overview.router)
router.include_router(feature_gaps.router)
router.include_router(customers.router)
