"""Chargebee revenue-snapshot sync adapter.

Polls Chargebee subscriptions and pushes one CustomerRevenueSnapshot per
customer into the Customer Feature Intelligence intake API. Run on a
schedule (cron / k8s CronJob — see deployment/customer-intelligence-adapters.md).

Env vars:
    ORG_ID                    Tenant/org id to tag every snapshot with
    CHARGEBEE_SITE             e.g. 'mycompany' for mycompany.chargebee.com
    CHARGEBEE_API_KEY
    INDEXING_SERVICE_URL       default http://localhost:8091
    INTELLIGENCE_INTAKE_TOKEN  PAT/service token scoped to 'intelligence:write'

Follow-up work: wire through the connector-registry config service (etcd)
like every other pipeshub connector, once Chargebee has a full
``ConnectorBuilder`` registration (see AGENTS.md / CONNECTOR_INTEGRATION_PLAYBOOK.md).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.sources.client.chargebee.chargebee import ChargebeeClient
from app.sources.external.chargebee.chargebee import (
    ChargebeeDataSource,
    parse_subscription_list_items,
)
from scripts.customer_intelligence.intake_client import (
    IntelligenceIntakeClient,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chargebee_sync")


def _epoch_to_datetime(epoch_seconds: int | None) -> datetime | None:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc) if epoch_seconds else None


async def sync_chargebee_revenue(org_id: str) -> int:
    site = os.environ["CHARGEBEE_SITE"]
    api_key = os.environ["CHARGEBEE_API_KEY"]

    client = ChargebeeClient.build_with_api_key(site=site, api_key=api_key)
    data_source = ChargebeeDataSource(client)
    intake = IntelligenceIntakeClient()

    snapshots_sent = 0
    offset: str | None = None
    while True:
        response = await data_source.list_subscriptions(limit=100, offset=offset)
        if not response.success:
            logger.error("Failed to list Chargebee subscriptions: %s", response.error or response.message)
            break

        items = parse_subscription_list_items(response.data or {})
        for item in items:
            subscription = item.get("subscription", {})
            customer = item.get("customer", {})
            if not customer or not subscription:
                continue

            mrr_cents = subscription.get("mrr") or 0
            mrr = mrr_cents / 100.0
            snapshot = {
                "org_id": org_id,
                "source_connector": "chargebee",
                "external_customer_id": customer.get("id", ""),
                "customer_name": (
                    f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
                    or customer.get("company", "")
                    or customer.get("id", "unknown")
                ),
                "mrr": mrr,
                "arr": mrr * 12,
                "seats_used": None,
                "seats_licensed": None,
                "consumed_features": [
                    subscription.get("plan_id", "")
                ] if subscription.get("plan_id") else [],
                "renewal_date": _epoch_to_datetime(subscription.get("current_term_end")).isoformat()
                if subscription.get("current_term_end") else None,
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
            }
            await intake.send_revenue_snapshot(snapshot)
            snapshots_sent += 1

        next_offset = (response.data or {}).get("next_offset")
        if not next_offset:
            break
        offset = next_offset

    logger.info("✅ Sent %d Chargebee revenue snapshot(s) for org '%s'", snapshots_sent, org_id)
    return snapshots_sent


if __name__ == "__main__":
    org_id_arg = os.environ["ORG_ID"]
    asyncio.run(sync_chargebee_revenue(org_id_arg))
