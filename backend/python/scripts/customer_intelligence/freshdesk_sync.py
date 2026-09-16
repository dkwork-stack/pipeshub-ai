"""Freshdesk support-ticket sync adapter.

Polls Freshdesk tickets updated since the last run and pushes one
CustomerSignalEvent (subject + description + first conversation reply) per
ticket into the Customer Feature Intelligence intake API, where LLM-based
pain-point/feature-gap inference runs.

Env vars:
    ORG_ID                     Tenant/org id to tag every event with
    FRESHDESK_DOMAIN            e.g. 'mycompany.freshdesk.com'
    FRESHDESK_API_KEY
    FRESHDESK_UPDATED_SINCE     ISO timestamp; defaults to 24h ago
    INDEXING_SERVICE_URL        default http://localhost:8091
    INTELLIGENCE_INTAKE_TOKEN   PAT/service token scoped to 'intelligence:write'

Reuses the existing ``FreshDeskClient`` / ``FreshdeskDataSource`` (already in
the codebase for agent tool-use) rather than a new HTTP integration.

Run on a schedule (cron / k8s CronJob — see
deployment/customer-intelligence-adapters.md).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.sources.client.freshdesk.freshdesk import FreshDeskClient
from app.sources.external.freshdesk.freshdesk import FreshdeskDataSource
from scripts.customer_intelligence.intake_client import (
    IntelligenceIntakeClient,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("freshdesk_sync")

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str:
    return _HTML_TAG_RE.sub(" ", value or "").strip()


async def sync_freshdesk_tickets(org_id: str) -> int:
    domain = os.environ["FRESHDESK_DOMAIN"]
    api_key = os.environ["FRESHDESK_API_KEY"]
    updated_since = os.environ.get(
        "FRESHDESK_UPDATED_SINCE",
        (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    client = FreshDeskClient.build_with_api_key(domain=domain, api_key=api_key)
    data_source = FreshdeskDataSource(client)
    intake = IntelligenceIntakeClient()

    events_sent = 0
    page = 1
    while True:
        response = await data_source.list_tickets(updated_since=updated_since, page=page, per_page=50)
        if not response.success:
            logger.error("Failed to list Freshdesk tickets: %s", response.error or response.message)
            break

        tickets = response.data if isinstance(response.data, list) else []
        if not tickets:
            break

        for ticket in tickets:
            ticket_id = ticket.get("id")
            requester_id = ticket.get("requester_id")
            company_id = ticket.get("company_id")
            customer_name = ticket.get("company_name") or f"requester-{requester_id}" or "unknown"
            external_customer_id = str(company_id or requester_id or "unknown")

            text_parts = [ticket.get("subject", ""), _strip_html(ticket.get("description_text") or ticket.get("description"))]

            conversations_resp = await data_source.list_ticket_conversations(id=ticket_id, per_page=10)
            if conversations_resp.success and isinstance(conversations_resp.data, list):
                text_parts.extend(
                    _strip_html(conv.get("body_text") or conv.get("body"))
                    for conv in conversations_resp.data[:5]
                )

            text = "\n".join(p for p in text_parts if p)
            if not text.strip():
                continue

            event = {
                "org_id": org_id,
                "source_connector": "freshdesk",
                "source_type": "support_ticket",
                "external_customer_id": external_customer_id,
                "customer_name": customer_name,
                "external_event_id": str(ticket_id),
                "text": text,
                "occurred_at": ticket.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                "citation_url": f"https://{domain}/a/tickets/{ticket_id}",
                "metadata": {"status": ticket.get("status"), "priority": ticket.get("priority")},
            }
            await intake.send_event(event)
            events_sent += 1

        if len(tickets) < 50:
            break
        page += 1

    logger.info("✅ Sent %d Freshdesk ticket event(s) for org '%s'", events_sent, org_id)
    return events_sent


if __name__ == "__main__":
    org_id_arg = os.environ["ORG_ID"]
    asyncio.run(sync_freshdesk_tickets(org_id_arg))
