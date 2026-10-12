"""Composes the intelligence portal API under ``/api/v1/intelligence-portal``.

Reads need ``intelligence:read``. Curation (topic edits, merges) and
compliance (erasure, audit log) need ``intelligence:write`` and are audited.
Signal intake stays on the indexing service (``app/api/routes/intelligence.py``).
Every route requires a verified token (``authMiddleware`` in
``app.intelligence_main``).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.intelligence_portal import (
    compliance,
    customers,
    feature_gaps,
    overview,
    pain_points,
    topics,
)

API_PREFIX = "/api/v1/intelligence-portal"

router = APIRouter(prefix=API_PREFIX)
router.include_router(overview.router)
router.include_router(feature_gaps.router)
router.include_router(pain_points.router)
router.include_router(topics.router)
router.include_router(customers.router)
router.include_router(compliance.router)
