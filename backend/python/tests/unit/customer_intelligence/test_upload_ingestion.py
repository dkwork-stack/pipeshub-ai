"""Unit tests for the Knowledge Base upload path of the ingestion service.

No MySQL, no LLM, no DI container: the store and extraction client are fakes,
and records are lightweight stand-ins carrying only the fields the service
reads (``app.models.entities.Record`` pulls in templating deps this suite
does not need).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.config.constants.arangodb import Connectors
from app.models.blocks import Block, BlocksContainer, BlockType, DataFormat
from app.models.intelligence import (
    FeatureGapCandidate,
    FeatureIntelligenceExtractionResult,
)
from app.modules.customer_intelligence.ingestion_service import (
    UPLOAD_SOURCE_CONNECTOR,
    CustomerIntelligenceIngestionService,
)

ORG_ID = "org-123"


class _FakeStore:
    def __init__(self) -> None:
        self.customers: list[tuple[str, str, str]] = []
        self.mentions = []
        self.recompute_calls: list[tuple[str, list[str] | None]] = []

    async def upsert_customer(self, org_id, external_customer_id, customer_name) -> None:
        self.customers.append((org_id, external_customer_id, customer_name))

    async def upsert_feature_gap_mention(self, mention) -> None:
        self.mentions.append(mention)

    async def recompute_feature_gap_scores(self, org_id, feature_names=None) -> None:
        self.recompute_calls.append((org_id, feature_names))


class _FakeExtractionClient:
    def __init__(self, results: dict[str, FeatureIntelligenceExtractionResult]) -> None:
        self.results = results
        self.calls: list[dict] = []

    async def extract_feature_intelligence(
        self, text: str, org_id: str, *, infer_customer: bool = False
    ) -> FeatureIntelligenceExtractionResult:
        self.calls.append({"text": text, "org_id": org_id, "infer_customer": infer_customer})
        return self.results.get(text, FeatureIntelligenceExtractionResult())


def _gap(name: str) -> FeatureGapCandidate:
    return FeatureGapCandidate(
        feature_name=name, description=f"needs {name}", confidence=0.9, excerpt=name
    )


def _record(
    blocks: list[Block], *, connector: Connectors = Connectors.KNOWLEDGE_BASE, name: str = "tickets.csv"
) -> SimpleNamespace:
    return SimpleNamespace(
        id="rec-1",
        org_id=ORG_ID,
        record_name=name,
        connector_name=connector,
        record_group_type=None,
        block_containers=BlocksContainer(blocks=blocks, block_groups=[]),
        created_at=1_700_000_000_000,
        source_created_at=None,
        weburl="/record/rec-1",
    )


def _row(index: int, text: str, row_number: int) -> Block:
    return Block(
        index=index,
        type=BlockType.TABLE_ROW,
        format=DataFormat.JSON,
        data={"row_natural_language_text": text, "row_number": row_number},
    )


def _text(index: int, text: str) -> Block:
    return Block(index=index, type=BlockType.TEXT, format=DataFormat.TXT, data=text)


def _service(client: _FakeExtractionClient) -> tuple[CustomerIntelligenceIngestionService, _FakeStore]:
    store = _FakeStore()
    svc = CustomerIntelligenceIngestionService(
        logger=logging.getLogger("test"), intelligence_store=store, extraction_client=client
    )
    return svc, store


@pytest.mark.asyncio
async def test_csv_upload_is_ingested_row_by_row_with_inferred_customers() -> None:
    row_a = "Customer: Acme. We can't export in bulk."
    row_b = "Customer: Globex. Need SSO."
    client = _FakeExtractionClient(
        {
            row_a: FeatureIntelligenceExtractionResult(
                feature_gaps=[_gap("Bulk CSV export")], customer_name="Acme"
            ),
            row_b: FeatureIntelligenceExtractionResult(
                feature_gaps=[_gap("SSO / SAML support")], customer_name="Globex"
            ),
        }
    )
    svc, store = _service(client)

    written = await svc.ingest_indexed_record(_record([_row(0, row_a, 2), _row(1, row_b, 3)]))

    assert written == 2
    assert all(c["infer_customer"] for c in client.calls)
    assert {c[2] for c in store.customers} == {"Acme", "Globex"}
    by_customer = {m.external_customer_id: m for m in store.mentions}
    assert f"{UPLOAD_SOURCE_CONNECTOR}:acme" in by_customer
    acme = by_customer[f"{UPLOAD_SOURCE_CONNECTOR}:acme"]
    assert acme.feature_name == "Bulk CSV export"
    assert acme.external_event_id == "rec-1:row:2"
    assert acme.source_connector == UPLOAD_SOURCE_CONNECTOR
    assert acme.citation_url == "/record/rec-1"


@pytest.mark.asyncio
async def test_document_upload_is_one_event_and_falls_back_to_file_name() -> None:
    para1, para2 = "Meeting notes.", "They need an audit log feature."
    joined = f"{para1}\n{para2}"
    client = _FakeExtractionClient(
        {joined: FeatureIntelligenceExtractionResult(feature_gaps=[_gap("Audit log")])}
    )
    svc, store = _service(client)

    written = await svc.ingest_indexed_record(
        _record([_text(0, para1), _text(1, para2)], name="acme-notes.pdf")
    )

    assert written == 1
    assert len(client.calls) == 1
    assert store.customers == [(ORG_ID, f"{UPLOAD_SOURCE_CONNECTOR}:acme-notes-pdf", "acme-notes.pdf")]
    assert store.mentions[0].external_event_id == "rec-1"


@pytest.mark.asyncio
async def test_rows_without_feature_gaps_write_nothing() -> None:
    client = _FakeExtractionClient({})
    svc, store = _service(client)

    written = await svc.ingest_indexed_record(_record([_row(0, "thanks, resolved", 2)]))

    assert written == 0
    assert store.customers == []
    assert store.mentions == []


@pytest.mark.asyncio
async def test_non_kb_records_are_skipped_without_llm_calls() -> None:
    client = _FakeExtractionClient({})
    svc, _store = _service(client)

    written = await svc.ingest_indexed_record(
        _record([_row(0, "Need SSO", 2)], connector=Connectors.GOOGLE_DRIVE)
    )

    assert written == 0
    assert client.calls == []


@pytest.mark.asyncio
async def test_row_cap_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTELLIGENCE_UPLOAD_MAX_ROWS", "2")
    client = _FakeExtractionClient({})
    svc, _store = _service(client)

    await svc.ingest_indexed_record(_record([_row(i, f"row {i} need x", i + 2) for i in range(5)]))

    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_one_unit_failure_does_not_drop_sibling_writes() -> None:
    """A single row's store error must not abort the rest of the CSV batch."""
    ok = "Customer: Acme. Need SSO."
    boom = "Customer: Globex. Need audit log."

    class _BoomStore(_FakeStore):
        async def upsert_customer(self, org_id, external_customer_id, customer_name) -> None:
            if "globex" in external_customer_id:
                raise RuntimeError("simulated mysql loop error")
            await super().upsert_customer(org_id, external_customer_id, customer_name)

    client = _FakeExtractionClient(
        {
            ok: FeatureIntelligenceExtractionResult(
                feature_gaps=[_gap("SSO")], customer_name="Acme"
            ),
            boom: FeatureIntelligenceExtractionResult(
                feature_gaps=[_gap("Audit log")], customer_name="Globex"
            ),
        }
    )
    store = _BoomStore()
    svc = CustomerIntelligenceIngestionService(
        logger=logging.getLogger("test"), intelligence_store=store, extraction_client=client
    )

    written = await svc.ingest_indexed_record(_record([_row(0, ok, 2), _row(1, boom, 3)]))

    assert written == 1
    assert len(store.mentions) == 1
    assert store.mentions[0].feature_name == "SSO"
    assert store.recompute_calls == [(ORG_ID, None)]
