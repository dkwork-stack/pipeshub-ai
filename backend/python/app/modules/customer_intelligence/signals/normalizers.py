"""Record -> SignalEnvelope normalisers.

One small strategy per source *shape*, not per connector: any connector whose
records look like a thread (description + reply groups) gets turn-aware
analysis without code here knowing its name. Add a shape by appending a
``SignalNormalizer`` to ``default_normalizers()``.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Protocol

from app.models.blocks import BlockType, GroupSubType
from app.models.intelligence import ConversationTurn, SignalSourceType, SpeakerRole
from app.modules.customer_intelligence.signals.envelope import SignalEnvelope

if TYPE_CHECKING:
    from app.models.blocks import BlockGroup
    from app.models.entities import Record

UPLOAD_SOURCE_CONNECTOR = "file_upload"

_DEFAULT_MAX_ROWS = 200
_DEFAULT_MAX_TURN_CHARS = 4000
_MAX_TURNS = 40
_COMMENT_BY = re.compile(r"^(?:.* - )?Comment by (?P<author>.+)$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# "Jane Doe: …", "00:01:02 Jane Doe: …", "[00:01] Jane: …" — common transcript line shapes.
_SPEAKER_LINE = re.compile(
    r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?P<speaker>[A-Z][\w .'-]{0,60}?):\s+(?P<text>\S.*)$"
)

_THREAD_RECORD_TYPES = frozenset({"TICKET", "CASE"})
_SOURCE_TYPE_BY_RECORD_TYPE = {
    "TICKET": SignalSourceType.SUPPORT_TICKET,
    "CASE": SignalSourceType.SUPPORT_TICKET,
    "DEAL": SignalSourceType.CRM_NOTE,
    "MEETING": SignalSourceType.CALL_TRANSCRIPT,
    "MAIL": SignalSourceType.EMAIL,
    "GROUP_MAIL": SignalSourceType.EMAIL,
    "MESSAGE": SignalSourceType.CHAT,
}


def _max_turn_chars() -> int:
    return int(os.getenv("INTELLIGENCE_MAX_TURN_CHARS", _DEFAULT_MAX_TURN_CHARS))


def _value(enum_or_str: Any) -> str:  # noqa: ANN401
    return str(getattr(enum_or_str, "value", enum_or_str) or "")


def _occurred_at(record: "Record") -> datetime:
    ms = record.source_created_at or record.created_at
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def _clip(text: str) -> str:
    limit = _max_turn_chars()
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def source_connector_for(record: "Record") -> str:
    if is_upload_record(record):
        return UPLOAD_SOURCE_CONNECTOR
    return _value(record.connector_name).lower() or "unknown"


def source_type_for(record: "Record") -> SignalSourceType:
    if is_upload_record(record):
        return SignalSourceType.DOCUMENT_UPLOAD
    return _SOURCE_TYPE_BY_RECORD_TYPE.get(_value(record.record_type).upper(), SignalSourceType.DOCUMENT_UPLOAD)


def is_upload_record(record: "Record") -> bool:
    return _value(record.connector_name) == "KB" or _value(getattr(record, "record_group_type", None)) == "KB"


def _base_envelope(record: "Record", **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    upload = is_upload_record(record)
    values: dict[str, Any] = {
        "org_id": record.org_id,
        "source_connector": source_connector_for(record),
        "source_type": source_type_for(record),
        "external_event_id": record.id,
        "source_record_id": record.id,
        "occurred_at": _occurred_at(record),
        "citation_url": record.weburl,
        "customer_name_fallback": record.record_name if upload else None,
        "metadata": {
            "record_name": record.record_name,
            "record_type": _value(record.record_type),
        },
    }
    values.update(overrides)
    return values


class SignalNormalizer(Protocol):
    def accepts(self, record: "Record") -> bool: ...

    def normalize(self, record: "Record") -> list[SignalEnvelope]: ...


class TabularRowsNormalizer:
    """CSV/XLSX: one envelope per row (rows are independent customer voices)."""

    def __init__(self, logger: Any = None) -> None:  # noqa: ANN401
        self.logger = logger

    def accepts(self, record: "Record") -> bool:
        containers = record.block_containers
        return bool(containers and any(b.type == BlockType.TABLE_ROW for b in containers.blocks or []))

    def normalize(self, record: "Record") -> list[SignalEnvelope]:
        rows = []
        for block in record.block_containers.blocks:
            if block.type != BlockType.TABLE_ROW or not block.data:
                continue
            data = block.data
            text = data.get("row_natural_language_text") if isinstance(data, dict) else str(data)
            if not text or not text.strip():
                continue
            row_no = data.get("row_number", block.index) if isinstance(data, dict) else block.index
            cells = data.get("cells") if isinstance(data, dict) else None
            rows.append((row_no, text, cells if isinstance(cells, Mapping) else None))

        max_rows = int(os.getenv("INTELLIGENCE_UPLOAD_MAX_ROWS", _DEFAULT_MAX_ROWS))
        if len(rows) > max_rows:
            if self.logger:
                self.logger.warning(
                    "⚠️ Upload '%s' has %d rows; only the first %d are analysed (INTELLIGENCE_UPLOAD_MAX_ROWS)",
                    record.record_name, len(rows), max_rows,
                )
            rows = rows[:max_rows]

        return [
            SignalEnvelope(
                **_base_envelope(
                    record,
                    external_event_id=f"{record.id}:row:{row_no}",
                    turns=[ConversationTurn(text=_clip(text))],
                    cells=dict(cells) if cells else None,
                )
            )
            for row_no, text, cells in rows
        ]


class ThreadNormalizer:
    """Tickets/cases: description + reply block groups -> role-labelled turns.

    Connectors emit the opening message as a CONTENT group and each reply as
    a COMMENT group named "Comment by <author>". The reporter/creator is the
    customer; the assignee is the agent; anyone else is left unknown and the
    prompt decides from context.
    """

    def accepts(self, record: "Record") -> bool:
        groups = record.block_containers.block_groups if record.block_containers else None
        if not groups:
            return False
        if any(g.sub_type == GroupSubType.COMMENT for g in groups):
            return True
        # A ticket with no replies yet is still the customer speaking.
        return _value(record.record_type).upper() in _THREAD_RECORD_TYPES and any(
            g.sub_type == GroupSubType.CONTENT for g in groups
        )

    def normalize(self, record: "Record") -> list[SignalEnvelope]:
        customer_ids = _identities(
            getattr(record, "reporter_name", None), getattr(record, "reporter_email", None),
            getattr(record, "creator_name", None), getattr(record, "creator_email", None),
        )
        agent_ids = _identities(getattr(record, "assignee", None), getattr(record, "assignee_email", None))
        reporter = getattr(record, "reporter_name", None) or getattr(record, "creator_name", None)

        groups = sorted(
            (g for g in record.block_containers.block_groups
             if g.sub_type in (GroupSubType.CONTENT, GroupSubType.COMMENT)),
            key=lambda g: g.index if g.index is not None else 0,
        )
        turns: list[ConversationTurn] = []
        for group in groups:
            text = _group_text(group, record)
            if not text:
                continue
            if group.sub_type == GroupSubType.CONTENT:
                author, role = reporter, SpeakerRole.CUSTOMER
            else:
                author = _comment_author(group)
                role = _role_for(author, customer_ids, agent_ids)
            turns.append(ConversationTurn(role=role, author=_display_name(author), text=_clip(text)))

        if not turns:
            return []
        if len(turns) > _MAX_TURNS:
            # Keep the opening ask and the most recent exchange.
            turns = turns[:1] + turns[-(_MAX_TURNS - 1):]
        reporter_email = getattr(record, "reporter_email", None) or getattr(record, "creator_email", None)
        return [
            SignalEnvelope(
                **_base_envelope(record, turns=turns, customer_name_fallback=company_from_email(reporter_email))
            )
        ]


class TranscriptNormalizer:
    """Meetings/calls: split "Speaker: text" lines into turns when present."""

    def accepts(self, record: "Record") -> bool:
        return _value(record.record_type).upper() == "MEETING"

    def normalize(self, record: "Record") -> list[SignalEnvelope]:
        text = _record_text(record)
        if not text:
            return []
        turns: list[ConversationTurn] = []
        for line in text.splitlines():
            match = _SPEAKER_LINE.match(line)
            if match:
                speaker = match.group("speaker").strip()
                if turns and turns[-1].author == speaker:
                    turns[-1].text += " " + match.group("text").strip()
                else:
                    turns.append(ConversationTurn(author=speaker, text=match.group("text").strip()))
            elif turns and line.strip():
                turns[-1].text += " " + line.strip()
        if len(turns) < 2:
            turns = [ConversationTurn(text=text)]
        turns = [t.model_copy(update={"text": _clip(t.text)}) for t in turns]
        if len(turns) > _MAX_TURNS:
            turns = turns[:_MAX_TURNS]
        return [SignalEnvelope(**_base_envelope(record, turns=turns))]


class DocumentNormalizer:
    """Fallback: the whole document is one customer voice."""

    def accepts(self, record: "Record") -> bool:
        return True

    def normalize(self, record: "Record") -> list[SignalEnvelope]:
        text = _record_text(record)
        if not text:
            return []
        # Documents get the extractor's 20k-char window rather than the per-turn cap.
        return [SignalEnvelope(**_base_envelope(record, turns=[ConversationTurn(text=text[:20000])]))]


def default_normalizers(logger: Any = None) -> list[SignalNormalizer]:  # noqa: ANN401
    return [TabularRowsNormalizer(logger), ThreadNormalizer(), TranscriptNormalizer(), DocumentNormalizer()]


def normalize_record(record: "Record", normalizers: list[SignalNormalizer]) -> list[SignalEnvelope]:
    """First normaliser that accepts the record wins."""
    if not record.block_containers:
        return []
    for normalizer in normalizers:
        if normalizer.accepts(record):
            return normalizer.normalize(record)
    return []


# --------------------------------------------------------------------- helpers


def _record_text(record: "Record") -> str:
    containers = record.block_containers
    parts = [
        b.data if isinstance(b.data, str) else str(b.data)
        for b in containers.blocks or []
        if b.type == BlockType.TEXT and b.data
    ]
    if not parts:
        parts = [g.data for g in containers.block_groups or [] if isinstance(g.data, str) and g.data.strip()]
    return "\n".join(p for p in parts if p.strip()).strip()


def _group_text(group: "BlockGroup", record: "Record") -> str:
    if isinstance(group.data, str) and group.data.strip():
        return group.data.strip()
    parts = [
        b.data for b in record.block_containers.blocks or []
        if b.parent_index == group.index and b.type == BlockType.TEXT and isinstance(b.data, str)
    ]
    return "\n".join(parts).strip()


def _comment_author(group: "BlockGroup") -> Optional[str]:
    for label in (group.description, group.name):
        match = _COMMENT_BY.match(label or "")
        if match:
            return match.group("author").strip()
    return None


def _identities(*values: Optional[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        if not value:
            continue
        out.add(value.strip().lower())
        out.update(e.lower() for e in _EMAIL.findall(value))
    return out


def _role_for(author: Optional[str], customer_ids: set[str], agent_ids: set[str]) -> SpeakerRole:
    if not author:
        return SpeakerRole.UNKNOWN
    ids = _identities(author)
    if ids & customer_ids or any(c in author.lower() for c in customer_ids if len(c) > 3):
        return SpeakerRole.CUSTOMER
    if ids & agent_ids or any(a in author.lower() for a in agent_ids if len(a) > 3):
        return SpeakerRole.AGENT
    return SpeakerRole.UNKNOWN


_FREEMAIL = frozenset(
    "gmail.com googlemail.com yahoo.com outlook.com hotmail.com live.com icloud.com me.com "
    "aol.com proton.me protonmail.com gmx.com mail.com yandex.com zoho.com".split()
)


def company_from_email(email: Optional[str]) -> Optional[str]:
    """'jane@acme-corp.io' -> 'Acme Corp'; None for free-mail addresses."""
    match = _EMAIL.search(email or "")
    if not match:
        return None
    domain = match.group(0).split("@", 1)[1].lower()
    if domain in _FREEMAIL:
        return None
    labels = domain.split(".")
    # acme.co.uk -> acme, support.acme.com -> acme
    has_second_level_suffix = len(labels) >= 3 and labels[-2] in {"co", "com", "org", "net", "ac", "gov"}
    core = labels[-3] if has_second_level_suffix else labels[max(len(labels) - 2, 0)]
    return " ".join(part.capitalize() for part in re.split(r"[-_]", core) if part) or None


def _display_name(author: Optional[str]) -> Optional[str]:
    """Drop the address from '"Jane Doe" <jane@acme.com>' — the name is enough context and the address is PII."""
    if not author:
        return None
    name = _EMAIL.sub("", author).replace("<>", "").strip().strip('"').strip()
    return name or None
