"""Normalisers, source policy, PII redaction and broker dispatch."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.config.constants.arangodb import Connectors
from app.models.intelligence import SignalSourceType, SpeakerRole
from app.modules.customer_intelligence.signals.dispatch import BrokerSignalDispatcher
from app.modules.customer_intelligence.signals.envelope import (
    SIGNAL_EVENT_TYPE,
    SignalEnvelope,
)
from app.modules.customer_intelligence.signals.normalizers import (
    company_from_email,
    default_normalizers,
    normalize_record,
)
from app.modules.customer_intelligence.signals.policy import IntelligenceSourcePolicy
from app.modules.customer_intelligence.signals.redaction import RegexPiiRedactor
from tests.unit.customer_intelligence.fakes import (
    LOG,
    ORG_ID,
    record,
    text_block,
    ticket,
)


def _normalize(rec):
    return normalize_record(rec, default_normalizers(LOG))


def test_ticket_turns_label_customer_agent_and_unknown_and_drop_addresses() -> None:
    (env,) = _normalize(ticket(
        [("Jane", "Need SSO"), ('"Sam" <sam@vendor.io>', "Not yet"), ("Bob from Finance", "+1"),
         ('"Jane Roe" <jane@acme.com>', "Ok")],
        reporter_name="Jane Roe", reporter_email="jane@acme.com", assignee_email="sam@vendor.io",
    ))
    assert [(t.role, t.author) for t in env.turns] == [
        (SpeakerRole.CUSTOMER, "Jane Roe"),
        (SpeakerRole.AGENT, "Sam"),
        (SpeakerRole.UNKNOWN, "Bob from Finance"),
        (SpeakerRole.CUSTOMER, "Jane Roe"),
    ]
    assert env.source_type == SignalSourceType.SUPPORT_TICKET
    assert env.customer_name_fallback == "Acme"
    assert env.infer_customer


def test_long_threads_keep_the_opening_ask_and_the_latest_replies() -> None:
    articles = [("Jane", "opening ask")] + [(f"Agent {i}", f"reply {i}") for i in range(60)]
    (env,) = _normalize(ticket(articles, reporter_name="Jane"))
    assert len(env.turns) == 40
    assert env.turns[0].text.endswith("opening ask")
    assert env.turns[-1].text == "reply 59"


def test_turn_text_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTELLIGENCE_MAX_TURN_CHARS", "10")
    (env,) = _normalize(ticket([("Jane", "x" * 50)], reporter_name="Jane"))
    assert len(env.turns[0].text) <= 12


def test_meeting_transcript_is_split_by_speaker() -> None:
    transcript = "00:00:01 Jane Roe: We keep exporting by hand.\ncontinued thought\n00:00:09 Sam: Noted.\n00:00:12 Sam: Anything else?"
    rec = record([text_block(0, transcript)], connector=Connectors.ZOOM, record_type="MEETING", name="QBR")
    (env,) = _normalize(rec)
    assert [(t.author, t.text) for t in env.turns] == [
        ("Jane Roe", "We keep exporting by hand. continued thought"),
        ("Sam", "Noted. Anything else?"),
    ]
    assert env.source_type == SignalSourceType.CALL_TRANSCRIPT


def test_meeting_without_speaker_lines_is_one_turn() -> None:
    rec = record([text_block(0, "General notes about the account.")], connector=Connectors.ZOOM, record_type="MEETING")
    (env,) = _normalize(rec)
    assert env.text == "General notes about the account."


def test_records_without_text_produce_nothing() -> None:
    assert _normalize(record([])) == []


def test_policy_scopes_connector_records_by_type_and_connector() -> None:
    policy = IntelligenceSourcePolicy(record_types=frozenset({"TICKET"}), connectors=frozenset({"ZAMMAD"}))
    assert policy.accepts(record([]))  # KB uploads are always in scope
    assert policy.accepts(ticket([("a", "b")]))
    assert not policy.accepts(record([], connector=Connectors.SERVICENOW, record_type="TICKET"))
    assert not policy.accepts(record([], connector=Connectors.ZAMMAD, record_type="FILE"))


def test_policy_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTELLIGENCE_SOURCE_RECORD_TYPES", "mail, ticket")
    monkeypatch.delenv("INTELLIGENCE_SOURCE_CONNECTORS", raising=False)
    policy = IntelligenceSourcePolicy.from_env()
    assert policy.record_types == frozenset({"MAIL", "TICKET"})
    assert policy.connectors == frozenset()


@pytest.mark.parametrize(
    ("email", "company"),
    [("jane@acme-corp.io", "Acme Corp"), ("Bob <b@support.globex.co.uk>", "Globex"), ("x@gmail.com", None), (None, None)],
)
def test_company_from_email(email, company) -> None:
    assert company_from_email(email) == company


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail jane.doe@acme.co.uk now", "mail [email] now"),
        ("call +1 (415) 555-0134 today", "call [phone] today"),
        ("card 4111 1111 1111 1111", "card [card]"),
        ("order 1234 5678 9012 3456", "order 1234 5678 9012 3456"),
        ("SSN 123-45-6789", "SSN [id-number]"),
        ("IBAN DE89 3704 0044 0532 0130 00", "IBAN [iban]"),
        ("host 10.0.0.12 v4.2.1", "host [ip] v4.2.1"),
        ("renewal 2026-12-31 for 300 seats at $12,000", "renewal 2026-12-31 for 300 seats at $12,000"),
    ],
)
def test_regex_redactor(text, expected) -> None:
    assert RegexPiiRedactor().redact(text) == expected


class _FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list]] = []
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    async def send_messages(self, topic, messages):
        self.sent.append((topic, messages))
        return [True] * len(messages)

    async def cleanup(self) -> None:
        pass


def _envelope(event_id: str, org: str = ORG_ID) -> SignalEnvelope:
    return SignalEnvelope(
        org_id=org, source_connector="zammad", source_type=SignalSourceType.SUPPORT_TICKET,
        external_event_id=event_id, occurred_at=datetime(2026, 10, 1), turns=[{"text": "need sso"}],
    )


async def test_broker_dispatcher_publishes_versioned_envelopes_keyed_by_org(monkeypatch: pytest.MonkeyPatch) -> None:
    producer = _FakeProducer()
    dispatcher = BrokerSignalDispatcher(LOG, config_service=None)

    async def fake_producer():
        return producer

    monkeypatch.setattr(dispatcher, "_producer", fake_producer)
    assert await dispatcher.dispatch([_envelope("a"), _envelope("b", org="org-2")]) == 2

    ((topic, messages),) = producer.sent
    assert topic == "intelligence-events"
    assert [key for key, _ in messages] == [ORG_ID, "org-2"]
    payload = messages[0][1]
    assert payload["eventType"] == SIGNAL_EVENT_TYPE
    assert SignalEnvelope.model_validate(payload["payload"]).external_event_id == "a"
    assert payload["payload"]["schema_version"] == 1


async def test_broker_dispatcher_raises_on_partial_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    producer = _FakeProducer()

    async def half(topic, messages):
        return [True, False]

    producer.send_messages = half
    dispatcher = BrokerSignalDispatcher(LOG, config_service=None)

    async def fake_producer():
        return producer

    monkeypatch.setattr(dispatcher, "_producer", fake_producer)
    with pytest.raises(RuntimeError, match="1/2"):
        await dispatcher.dispatch([_envelope("a"), _envelope("b")])


class _Analyzer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.seen: list[str] = []

    async def analyze(self, envelope: SignalEnvelope) -> int:
        if self.fail:
            raise RuntimeError("llm down")
        self.seen.append(envelope.external_event_id)
        return 1


def _message(payload, event_type: str = SIGNAL_EVENT_TYPE, final: bool = False):
    from app.services.messaging.config import StreamMessage

    return StreamMessage(eventType=event_type, payload=payload, is_final_failure=final)


async def test_worker_handler_settles_success_retries_failure_and_drops_malformed() -> None:
    from app.modules.customer_intelligence.worker import build_signal_handler

    ok, broken = _Analyzer(), _Analyzer(fail=True)

    async def get_ok():
        return ok

    async def get_broken():
        return broken

    good = _envelope("evt-1").model_dump(mode="json")
    assert await build_signal_handler(LOG, get_ok)(_message(good)) is True
    assert ok.seen == ["evt-1"]
    assert await build_signal_handler(LOG, get_broken)(_message(good)) is False
    assert await build_signal_handler(LOG, get_ok)(_message({"org_id": ORG_ID})) is True
    assert await build_signal_handler(LOG, get_ok)(_message(good, event_type="other")) is True
    assert ok.seen == ["evt-1"]
