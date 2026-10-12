"""Unit tests for revenue snapshot intake (allowlist + customer remap)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.intelligence import CustomerRevenueSnapshot
from app.modules.customer_intelligence.ingestion_service import (
    UPLOAD_SOURCE_CONNECTOR,
    CustomerIntelligenceIngestionService,
)
from app.services.intelligence_store.mysql.schema import revenue_snapshots
from tests.unit.customer_intelligence.fakes import (
    LOG,
    ORG_ID,
    FakeExtractionClient,
    sqlite_store,
)


@pytest.fixture
async def setup():
    store = await sqlite_store()
    recomputes: list[tuple[str, object]] = []
    real = store.recompute_feature_gap_scores

    async def spy(org_id, feature_names=None):
        recomputes.append((org_id, feature_names))
        await real(org_id, feature_names)

    store.recompute_feature_gap_scores = spy
    svc = CustomerIntelligenceIngestionService(logger=LOG, intelligence_store=store, extraction_client=FakeExtractionClient())
    yield svc, store, recomputes
    await store.close()


async def _snapshots(store):
    async with store.engine.begin() as conn:
        return (await conn.execute(select(revenue_snapshots))).mappings().all()


def _snapshot(connector: str, ext_id: str, name: str, arr: float) -> CustomerRevenueSnapshot:
    return CustomerRevenueSnapshot(
        org_id=ORG_ID, source_connector=connector, external_customer_id=ext_id,
        customer_name=name, arr=arr, mrr=arr / 12,
    )


async def test_ingest_revenue_rejects_non_revenue_connector(setup) -> None:
    svc, store, _ = setup
    with pytest.raises(ValueError, match="not a revenue source"):
        await svc.ingest_revenue_snapshot(_snapshot("freshdesk", "fd-1", "Acme", 10_000.0))
    assert await _snapshots(store) == []


async def test_ingest_revenue_accepts_chargebee(setup) -> None:
    svc, store, recomputes = setup
    await svc.ingest_revenue_snapshot(_snapshot("chargebee", "cb_acme", "Acme Corp", 120_000.0))
    (snap,) = await _snapshots(store)
    assert snap["external_customer_id"] == "cb_acme"
    assert recomputes == [(ORG_ID, None)]


async def test_ingest_revenue_remaps_onto_existing_upload_customer_by_name(setup) -> None:
    svc, store, _ = setup
    await store.upsert_customer(ORG_ID, f"{UPLOAD_SOURCE_CONNECTOR}:acme", "Acme")
    await svc.ingest_revenue_snapshot(_snapshot("chargebee", "cb_other", "Acme Inc", 60_000.0))
    (snap,) = await _snapshots(store)
    assert snap["external_customer_id"] == f"{UPLOAD_SOURCE_CONNECTOR}:acme"
    assert await store.list_customer_names(ORG_ID) == [(f"{UPLOAD_SOURCE_CONNECTOR}:acme", "Acme")]


async def test_ingest_revenue_can_skip_inline_recompute(setup) -> None:
    svc, store, recomputes = setup
    await svc.ingest_revenue_snapshot(
        _snapshot(UPLOAD_SOURCE_CONNECTOR, "file_upload:globex", "Globex", 12_000.0), recompute_scores=False
    )
    assert len(await _snapshots(store)) == 1
    assert recomputes == []
