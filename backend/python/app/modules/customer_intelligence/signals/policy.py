"""Which indexed records feed Customer Feature Intelligence.

Processing customer conversations through an LLM is a purpose that has to be
deliberate (GDPR Art. 6), so connector records are opt-in by record type and,
optionally, by connector. Knowledge Base uploads are always in scope: a user
uploading a CSV to this product is the opt-in.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.customer_intelligence.signals.normalizers import is_upload_record

if TYPE_CHECKING:
    from app.models.entities import Record

_DEFAULT_RECORD_TYPES = "TICKET,CASE,MEETING"


def _csv_env(name: str, default: str = "") -> frozenset[str]:
    return frozenset(p.strip().upper() for p in os.getenv(name, default).split(",") if p.strip())


@dataclass(frozen=True)
class IntelligenceSourcePolicy:
    record_types: frozenset[str] = frozenset(_DEFAULT_RECORD_TYPES.split(","))
    connectors: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls) -> "IntelligenceSourcePolicy":
        return cls(
            record_types=_csv_env("INTELLIGENCE_SOURCE_RECORD_TYPES", _DEFAULT_RECORD_TYPES),
            connectors=_csv_env("INTELLIGENCE_SOURCE_CONNECTORS"),
        )

    def accepts(self, record: "Record") -> bool:
        if not record.org_id:
            return False
        if is_upload_record(record):
            return True
        record_type = str(getattr(record.record_type, "value", record.record_type) or "").upper()
        if record_type not in self.record_types:
            return False
        connector = str(getattr(record.connector_name, "value", record.connector_name) or "").upper()
        return not self.connectors or connector in self.connectors
