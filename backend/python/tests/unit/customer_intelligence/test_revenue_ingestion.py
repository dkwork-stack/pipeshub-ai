"""Unit tests for revenue snapshot intake (allowlist + customer remap)."""
from __future__ import annotations

import logging

import pytest

from app.models.intelligence import CustomerRevenueSnapshot
from app.modules.customer_intelligence.ingestion_service import (
    UPLOAD_SOURCE_CONNECTOR,
    CustomerIntelligenceIngestionService,
)
from tests.unit.customer_intelligence.test_upload_ingestion import (
    ORG_ID,
    _FakeExtractionClient,
    _FakeStore,
)


def _service() -> tuple[CustomerIntelligenceIngestionService, _FakeStore]:
    store = _FakeStore()
    svc = CustomerIntelligenceIngestionService(
        logger=logging.getLogger("test"),
        intelligence_store=store,
        extraction_client=_FakeExtractionClient({}),
    )
    return svc, store


@pytest.mark.asyncio
async def test_ingest_revenue_rejects_non_revenue_connector() -> None:
    svc, store = _service()
    with pytest.raises(ValueError, match="not a revenue source"):
        await svc.ingest_revenue_snapshot(
            CustomerRevenueSnapshot(
                org_id=ORG_ID,
                source_connector="freshdesk",
                external_customer_id="fd-1",
                customer_name="Acme",
                arr=10_000.0,
                mrr=833.33,
            )
        )
    assert store.revenue_snapshots == []


@pytest.mark.asyncio
async def test_ingest_revenue_accepts_chargebee() -> None:
    svc, store = _service()
    await svc.ingest_revenue_snapshot(
        CustomerRevenueSnapshot(
            org_id=ORG_ID,
            source_connector="chargebee",
            external_customer_id="cb_acme",
            customer_name="Acme Corp",
            arr=120_000.0,
            mrr=10_000.0,
        )
    )
    assert len(store.revenue_snapshots) == 1
    assert store.revenue_snapshots[0].external_customer_id == "cb_acme"
    assert store.recompute_calls == [(ORG_ID, None)]


@pytest.mark.asyncio
async def test_ingest_revenue_remaps_onto_existing_upload_customer_by_name() -> None:
    svc, store = _service()
    await store.upsert_customer(ORG_ID, f"{UPLOAD_SOURCE_CONNECTOR}:acme", "Acme")

    await svc.ingest_revenue_snapshot(
        CustomerRevenueSnapshot(
            org_id=ORG_ID,
            source_connector="chargebee",
            external_customer_id="cb_other",
            customer_name="Acme Inc",
            arr=60_000.0,
            mrr=5_000.0,
        )
    )

    snap = store.revenue_snapshots[0]
    assert snap.external_customer_id == f"{UPLOAD_SOURCE_CONNECTOR}:acme"
    assert snap.customer_name == "Acme"


@pytest.mark.asyncio
async def test_ingest_revenue_can_skip_inline_recompute() -> None:
    svc, store = _service()
    await svc.ingest_revenue_snapshot(
        CustomerRevenueSnapshot(
            org_id=ORG_ID,
            source_connector=UPLOAD_SOURCE_CONNECTOR,
            external_customer_id="file_upload:globex",
            customer_name="Globex",
            arr=12_000.0,
        ),
        recompute_scores=False,
    )
    assert len(store.revenue_snapshots) == 1
    assert store.recompute_calls == []
