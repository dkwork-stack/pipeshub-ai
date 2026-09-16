"""Salesforce CRM-note sync adapter.

Queries recently modified Salesforce Cases (support/CRM interactions) via
SOQL and pushes one CustomerSignalEvent per case into the Customer Feature
Intelligence intake API. Reuses the existing ``SalesforceDataSource``
(``soql_query``) already in the codebase rather than a new integration.

Env vars:
    ORG_ID                        Tenant/org id to tag every event with
    SALESFORCE_INSTANCE_URL        e.g. https://mycompany.my.salesforce.com
    SALESFORCE_ACCESS_TOKEN        OAuth access token (see AGENTS.md: never
                                    client_credentials for user-acting calls —
                                    use a token minted for a real integration user)
    SALESFORCE_API_VERSION          default '59.0'
    SALESFORCE_MODIFIED_SINCE_DAYS  default 1
    INDEXING_SERVICE_URL            default http://localhost:8091
    INTELLIGENCE_INTAKE_TOKEN       PAT/service token scoped to 'intelligence:write'

Run on a schedule (cron / k8s CronJob — see
deployment/customer-intelligence-adapters.md).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.sources.client.salesforce.salesforce import (
    SalesforceClient,
    SalesforceConfig,
)
from app.sources.external.salesforce.salesforce_data_source import (
    SalesforceDataSource,
)
from scripts.customer_intelligence.intake_client import (
    IntelligenceIntakeClient,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("salesforce_sync")

CASE_SOQL_TEMPLATE = (
    "SELECT Id, Subject, Description, Status, Account.Id, Account.Name, LastModifiedDate "
    "FROM Case WHERE LastModifiedDate >= {since} ORDER BY LastModifiedDate DESC LIMIT 200"
)


async def sync_salesforce_cases(org_id: str) -> int:
    instance_url = os.environ["SALESFORCE_INSTANCE_URL"]
    access_token = os.environ["SALESFORCE_ACCESS_TOKEN"]
    api_version = os.environ.get("SALESFORCE_API_VERSION", "59.0")
    since_days = int(os.environ.get("SALESFORCE_MODIFIED_SINCE_DAYS", "1"))
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    client = SalesforceClient.build_with_config(
        SalesforceConfig(instance_url=instance_url, access_token=access_token, api_version=api_version)
    )
    data_source = SalesforceDataSource(client)
    intake = IntelligenceIntakeClient()

    query = CASE_SOQL_TEMPLATE.format(since=since)
    response = await data_source.soql_query(api_version=api_version, q=query)
    if not response.success:
        logger.error("Failed to query Salesforce cases: %s", response.error or response.message)
        return 0

    records = (response.data or {}).get("records", []) if isinstance(response.data, dict) else []
    events_sent = 0
    for record in records:
        account = record.get("Account") or {}
        account_id = account.get("Id")
        account_name = account.get("Name")
        if not account_id:
            # A case not tied to an Account can't be joined to revenue data downstream.
            continue

        text = "\n".join(p for p in [record.get("Subject"), record.get("Description")] if p)
        if not text.strip():
            continue

        event = {
            "org_id": org_id,
            "source_connector": "salesforce",
            "source_type": "crm_note",
            "external_customer_id": account_id,
            "customer_name": account_name or account_id,
            "external_event_id": record.get("Id"),
            "text": text,
            "occurred_at": record.get("LastModifiedDate") or datetime.now(timezone.utc).isoformat(),
            "citation_url": f"{instance_url}/lightning/r/Case/{record.get('Id')}/view",
            "metadata": {"status": record.get("Status")},
        }
        await intake.send_event(event)
        events_sent += 1

    logger.info("✅ Sent %d Salesforce case event(s) for org '%s'", events_sent, org_id)
    return events_sent


if __name__ == "__main__":
    org_id_arg = os.environ["ORG_ID"]
    asyncio.run(sync_salesforce_cases(org_id_arg))
