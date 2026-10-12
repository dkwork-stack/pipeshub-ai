"""End to end through the indexing-side feeder (inline dispatch), the analysis
service and the real store on SQLite. Only the LLM and embeddings are faked."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config.constants.arangodb import Connectors
from app.models.intelligence import FeatureIntelligenceExtractionResult, TopicKind
from app.modules.customer_intelligence.ingestion_service import (
    UNATTRIBUTED_CUSTOMER,
    CustomerIntelligenceIngestionService,
)
from app.modules.customer_intelligence.matching.matcher import build_topic_matcher
from app.modules.customer_intelligence.signals.dispatch import InlineSignalDispatcher
from app.modules.customer_intelligence.signals.feeder import IntelligenceRecordFeeder
from app.modules.customer_intelligence.signals.normalizers import (
    UPLOAD_SOURCE_CONNECTOR,
)
from app.modules.customer_intelligence.signals.policy import IntelligenceSourcePolicy
from app.modules.customer_intelligence.signals.redaction import RegexPiiRedactor
from app.services.intelligence_store.mysql.schema import (
    feature_gap_mentions,
    feature_gap_scores,
    pain_point_mentions,
    revenue_snapshots,
)
from tests.unit.customer_intelligence.fakes import (
    LOG,
    ORG_ID,
    FakeExtractionClient,
    KeywordEmbedder,
    gap,
    pain,
    record,
    row,
    sqlite_store,
    text_block,
    ticket,
)


@pytest.fixture
async def store():
    s = await sqlite_store()
    yield s
    await s.close()


def _pipeline(store, client, *, embedder=None, redactor=None) -> tuple[IntelligenceRecordFeeder, CustomerIntelligenceIngestionService]:
    service = CustomerIntelligenceIngestionService(
        logger=LOG,
        intelligence_store=store,
        extraction_client=client,
        topic_matcher=build_topic_matcher(LOG, store, embedder),
        redactor=redactor,
    )
    feeder = IntelligenceRecordFeeder(LOG, InlineSignalDispatcher(LOG, service), policy=IntelligenceSourcePolicy())
    return feeder, service


async def _rows(store, table):
    async with store.engine.begin() as conn:
        return (await conn.execute(select(table))).mappings().all()


async def test_csv_rows_become_one_event_each_with_inferred_customers(store) -> None:
    client = FakeExtractionClient({
        "Acme": FeatureIntelligenceExtractionResult(feature_gaps=[gap("Bulk CSV export", "can't export in bulk")], customer_name="Acme"),
        "Globex": FeatureIntelligenceExtractionResult(feature_gaps=[gap("SSO / SAML support", "Need SSO")], customer_name="Globex"),
    })
    feeder, _ = _pipeline(store, client)

    await feeder.feed(record([row(0, "Customer: Acme. We can't export in bulk.", 2), row(1, "Customer: Globex. Need SSO.", 3)]))

    assert all(c["infer_customer"] for c in client.calls)
    mentions = {m["external_customer_id"]: m for m in await _rows(store, feature_gap_mentions)}
    acme = mentions[f"{UPLOAD_SOURCE_CONNECTOR}:acme"]
    assert (acme["feature_name"], acme["external_event_id"], acme["source_record_id"]) == ("Bulk CSV export", "rec-1:row:2", "rec-1")
    assert (acme["citation_url"], acme["extraction_model"], acme["prompt_version"]) == ("/record/rec-1", "fake/llm", "test")
    assert {name for _, name in await store.list_customer_names(ORG_ID)} == {"Acme", "Globex"}


async def test_document_upload_is_one_event_attributed_to_the_file_when_no_customer_named(store) -> None:
    client = FakeExtractionClient({"audit log": FeatureIntelligenceExtractionResult(feature_gaps=[gap("Audit log", "audit log feature")])})
    feeder, _ = _pipeline(store, client)

    await feeder.feed(record([text_block(0, "Meeting notes."), text_block(1, "They need an audit log feature.")], name="acme-notes.pdf"))

    assert len(client.calls) == 1
    assert await store.list_customer_names(ORG_ID) == [(f"{UPLOAD_SOURCE_CONNECTOR}:acme-notes-pdf", "acme-notes.pdf")]


async def test_ticket_thread_is_turn_aware_and_attributed_to_the_reporters_company(store) -> None:
    client = FakeExtractionClient({
        "SAML": FeatureIntelligenceExtractionResult(
            feature_gaps=[gap("SSO / SAML support", "We must have SAML before rollout", urgency="critical",
                              tone="frustrated", churn_risk=True, competitor="Okta", speaker_role="customer")],
            pain_points=[pain("Manual user provisioning", "adding 300 users by hand", sentiment="negative")],
        )
    })
    feeder, _ = _pipeline(store, client)

    await feeder.feed(ticket(
        [("Jane", "We must have SAML before rollout; adding 300 users by hand."),
         ('"Sam Agent" <sam@vendor.io>', "SAML is not available today."),
         ('"Jane Roe" <jane@acme-corp.com>', "Then we will look at other tools.")],
        reporter_name="Jane Roe", reporter_email="jane@acme-corp.com", assignee="Sam Agent",
    ))

    (call,) = client.calls
    assert call["text"].startswith("[Customer · Jane Roe]: # Login issues")
    assert "[Agent · Sam Agent]: SAML is not available today." in call["text"]
    assert "[Customer · Jane Roe]: Then we will look" in call["text"]
    (mention,) = await _rows(store, feature_gap_mentions)
    assert (mention["external_customer_id"], mention["source_connector"], mention["source_type"]) == ("zammad:acme-corp", "zammad", "support_ticket")
    assert (mention["urgency"], mention["tone"], mention["competitor"]) == ("critical", "frustrated", "Okta")
    assert bool(mention["churn_risk"])
    (pain_row,) = await _rows(store, pain_point_mentions)
    assert pain_row["sentiment"] == "Negative"
    assert await store.list_customer_names(ORG_ID) == [("zammad:acme-corp", "Acme Corp")]


async def test_policy_skips_record_types_not_opted_in_without_llm_calls(store) -> None:
    client = FakeExtractionClient()
    feeder, _ = _pipeline(store, client)
    drive_file = record([text_block(0, "Need SSO")], connector=Connectors.GOOGLE_DRIVE, record_type="FILE")
    assert await feeder.feed(drive_file) == 0
    assert client.calls == []


async def test_row_cap_is_enforced(store, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTELLIGENCE_UPLOAD_MAX_ROWS", "2")
    client = FakeExtractionClient()
    feeder, _ = _pipeline(store, client)
    await feeder.feed(record([row(i, f"row {i} need x", i + 2) for i in range(5)]))
    assert len(client.calls) == 2


async def test_rows_without_signals_write_nothing(store) -> None:
    feeder, _ = _pipeline(store, FakeExtractionClient())
    await feeder.feed(record([row(0, "thanks, resolved", 2)]))
    assert await store.list_customer_names(ORG_ID) == []


async def test_one_failing_row_does_not_drop_its_siblings(store) -> None:
    client = FakeExtractionClient({
        "Acme": FeatureIntelligenceExtractionResult(feature_gaps=[gap("SSO", "Need SSO")], customer_name="Acme"),
        "Globex": FeatureIntelligenceExtractionResult(feature_gaps=[gap("Audit log", "Need audit log")], customer_name="Globex"),
    })
    feeder, service = _pipeline(store, client)
    real_upsert = store.upsert_customer

    async def flaky_upsert(org_id, external_customer_id, customer_name):
        if "globex" in external_customer_id:
            raise RuntimeError("simulated mysql error")
        await real_upsert(org_id, external_customer_id, customer_name)

    store.upsert_customer = flaky_upsert
    dispatched = await feeder.feed(record([row(0, "Customer: Acme. Need SSO.", 2), row(1, "Customer: Globex. Need audit log.", 3)]))

    assert dispatched == 1
    assert [m["feature_name"] for m in await _rows(store, feature_gap_mentions)] == ["SSO"]


async def test_revenue_row_writes_snapshot_under_the_same_customer_and_weights_the_score(store) -> None:
    text = "Customer: Acme, ARR: 120000, Notes: Need SSO for compliance"
    client = FakeExtractionClient({"Acme": FeatureIntelligenceExtractionResult(feature_gaps=[gap("SSO", "Need SSO for compliance")], customer_name="Acme")})
    feeder, _ = _pipeline(store, client)

    await feeder.feed(record([row(0, text, 2, cells={"Customer": "Acme", "ARR": 120_000, "Notes": "Need SSO for compliance"})]))

    (snapshot,) = await _rows(store, revenue_snapshots)
    (mention,) = await _rows(store, feature_gap_mentions)
    assert (snapshot["arr"], snapshot["mrr"], snapshot["source_connector"]) == (120_000.0, 10_000.0, UPLOAD_SOURCE_CONNECTOR)
    assert snapshot["external_customer_id"] == mention["external_customer_id"]
    (score,) = await _rows(store, feature_gap_scores)
    assert score["total_arr_at_stake"] == 120_000.0


async def test_revenue_only_row_names_the_customer_from_its_column(store) -> None:
    feeder, _ = _pipeline(store, FakeExtractionClient())
    await feeder.feed(record([row(0, "Customer: Globex, ARR: 50000, Notes: Quarterly check-in", 2,
                                 cells={"Customer": "Globex", "ARR": 50_000, "Notes": "Quarterly check-in"})]))
    (snapshot,) = await _rows(store, revenue_snapshots)
    assert snapshot["arr"] == 50_000.0
    assert await store.list_customer_names(ORG_ID) == [(f"{UPLOAD_SOURCE_CONNECTOR}:globex", "Globex")]


async def test_connector_records_never_write_revenue(store) -> None:
    client = FakeExtractionClient({"SSO": FeatureIntelligenceExtractionResult(feature_gaps=[gap("SSO", "need SSO")])})
    feeder, _ = _pipeline(store, client)
    await feeder.feed(ticket([("Jane", "ARR: 900000. We need SSO.")], reporter_name="Jane"))
    assert await _rows(store, revenue_snapshots) == []
    assert (await store.list_customer_names(ORG_ID))[0][1] == UNATTRIBUTED_CUSTOMER


async def test_pii_is_redacted_before_the_llm_and_in_stored_excerpts(store) -> None:
    client = FakeExtractionClient({"bulk": FeatureIntelligenceExtractionResult(
        feature_gaps=[gap("Bulk CSV export", "We need bulk export, mail [email]")], customer_name="Acme")})
    feeder, _ = _pipeline(store, client, redactor=RegexPiiRedactor())

    await feeder.feed(record([row(0, "Customer: Acme. We need bulk export, mail jane@acme.com", 2)]))

    assert "jane@acme.com" not in client.calls[0]["text"]
    (mention,) = await _rows(store, feature_gap_mentions)
    assert mention["excerpt"] == "We need bulk export, mail [email]"


async def test_same_ask_in_new_words_aggregates_onto_the_existing_topic_semantically(store) -> None:
    client = FakeExtractionClient({
        "Acme": FeatureIntelligenceExtractionResult(feature_gaps=[gap("Bulk CSV export", "export everything to CSV")], customer_name="Acme"),
        "Globex": FeatureIntelligenceExtractionResult(feature_gaps=[gap("Download data in bulk", "download all our data in bulk")], customer_name="Globex"),
    })
    embedder = KeywordEmbedder()
    feeder, _ = _pipeline(store, client, embedder=embedder)

    await feeder.feed(record([row(0, "Customer: Acme. export everything to CSV", 2)]))
    await feeder.feed(record([row(0, "Customer: Globex. download all our data in bulk", 3)]))

    names = {m["feature_name"] for m in await _rows(store, feature_gap_mentions)}
    assert names == {"Bulk CSV export"}
    (score,) = await _rows(store, feature_gap_scores)
    assert (score["customer_count"], score["mention_count"]) == (2, 2)
    (topic,) = await store.list_topics(ORG_ID, TopicKind.FEATURE_GAP)
    assert topic.aliases == ["Download data in bulk"]
    assert await store.get_topic_embeddings(ORG_ID, "fake/embed")


async def test_without_embeddings_different_wording_stays_a_separate_topic(store) -> None:
    client = FakeExtractionClient({
        "Acme": FeatureIntelligenceExtractionResult(feature_gaps=[gap("Bulk CSV export", "export everything to CSV")], customer_name="Acme"),
        "Globex": FeatureIntelligenceExtractionResult(feature_gaps=[gap("Download data in bulk", "download all our data in bulk")], customer_name="Globex"),
    })
    feeder, _ = _pipeline(store, client, embedder=KeywordEmbedder(model=None))
    await feeder.feed(record([row(0, "Customer: Acme. export everything to CSV", 2)]))
    await feeder.feed(record([row(0, "Customer: Globex. download all our data in bulk", 3)]))
    assert len(await store.list_topics(ORG_ID, TopicKind.FEATURE_GAP)) == 2


async def test_reprocessing_the_same_record_is_idempotent(store) -> None:
    client = FakeExtractionClient({"Acme": FeatureIntelligenceExtractionResult(feature_gaps=[gap("SSO", "Need SSO")], customer_name="Acme")})
    feeder, _ = _pipeline(store, client)
    upload = record([row(0, "Customer: Acme. Need SSO.", 2)])
    await feeder.feed(upload)
    await feeder.feed(upload)
    assert len(await _rows(store, feature_gap_mentions)) == 1
    (score,) = await _rows(store, feature_gap_scores)
    assert score["mention_count"] == 1


async def test_prompt_hints_are_bounded_and_relevant(store) -> None:
    from app.models.intelligence import IntelligenceTopic

    for i in range(80):
        await store.upsert_topic(IntelligenceTopic(org_id=ORG_ID, kind=TopicKind.FEATURE_GAP, canonical_name=f"Feature {i:02d}"))
    await store.upsert_topic(IntelligenceTopic(org_id=ORG_ID, kind=TopicKind.FEATURE_GAP, canonical_name="Audit trail"))
    client = FakeExtractionClient()
    feeder, _ = _pipeline(store, client)

    await feeder.feed(record([row(0, "Customer: Acme. We need an audit trail of admin changes", 2)]))

    hints = client.calls[0]["taxonomy"]
    assert len(hints) == 30
    assert hints[0].name == "Audit trail"


async def test_guidance_exclusion_drops_a_matched_item(store) -> None:
    from app.models.intelligence import IntelligenceTopic, TopicGuidanceUpdate

    topic = await store.upsert_topic(IntelligenceTopic(org_id=ORG_ID, kind=TopicKind.FEATURE_GAP, canonical_name="SSO"))
    await store.update_topic_guidance(ORG_ID, topic.id, TopicGuidanceUpdate(guidance="exclude: mfa"))
    client = FakeExtractionClient({"Acme": FeatureIntelligenceExtractionResult(feature_gaps=[gap("SSO", "SSO with MFA prompts")], customer_name="Acme")})
    feeder, _ = _pipeline(store, client)
    await feeder.feed(record([row(0, "Customer: Acme. SSO with MFA prompts", 2)]))
    assert await _rows(store, feature_gap_mentions) == []
