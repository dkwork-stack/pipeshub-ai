"""Shared HTTP client for pushing data into the Customer Feature Intelligence intake API.

Used by every connector adapter script in this directory (Chargebee,
Freshdesk, Salesforce, CSV/PDF upload) — new adapters for future connectors
only need to build ``CustomerSignalEvent`` / ``CustomerRevenueSnapshot``
payloads and call this client; nothing else changes.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class IntelligenceIntakeClient:
    def __init__(self, base_url: str | None = None, access_token: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("INDEXING_SERVICE_URL", "http://localhost:8091")).rstrip("/")
        self.access_token = access_token or os.getenv("INTELLIGENCE_INTAKE_TOKEN", "")
        if not self.access_token:
            raise ValueError(
                "INTELLIGENCE_INTAKE_TOKEN is required: mint a PAT/service token scoped to "
                "'intelligence:write' (see AGENTS.md — never use client_credentials for user-acting calls)."
            )

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def send_event(self, event: dict) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/intelligence/events", json=event, headers=self._headers()
            )
            response.raise_for_status()
            return response.json()

    async def send_revenue_snapshot(self, snapshot: dict) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/intelligence/revenue-snapshots",
                json=snapshot,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()
