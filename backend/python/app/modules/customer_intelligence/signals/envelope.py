"""SignalEnvelope: the one versioned contract between signal sources and the analysis worker.

Self-contained by design — the worker needs no graph, vector or blob access to
analyse one, so it can scale (and be secured) independently of indexing.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.models.intelligence import (
    ConversationTurn,
    CustomerSignalEvent,
    SignalSourceType,
    render_turns,
)

SIGNAL_EVENT_TYPE = "intelligence.signal"


class SignalEnvelope(BaseModel):
    schema_version: Literal[1] = 1
    org_id: str
    source_connector: str
    source_type: SignalSourceType
    external_event_id: str = Field(..., description="Idempotency key; table rows use '<record id>:row:<n>'")
    source_record_id: Optional[str] = Field(default=None, description="PipesHub record id; lineage and erasure key")
    occurred_at: datetime
    citation_url: Optional[str] = None
    turns: list[ConversationTurn] = Field(..., min_length=1)
    customer_external_id: Optional[str] = Field(
        default=None, description="Known customer; when absent the extractor infers one"
    )
    customer_name: Optional[str] = None
    customer_name_fallback: Optional[str] = Field(
        default=None, description="Attribution of last resort (e.g. the upload's file name) so evidence is never dropped"
    )
    cells: Optional[dict[str, Any]] = Field(default=None, description="Tabular row cells, used for revenue columns")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return render_turns(self.turns)

    @property
    def infer_customer(self) -> bool:
        return not self.customer_external_id

    @classmethod
    def from_event(cls, event: CustomerSignalEvent) -> "SignalEnvelope":
        """Intake-API events already know their customer."""
        turns = event.turns or [ConversationTurn(text=event.text)]
        return cls(
            org_id=event.org_id,
            source_connector=event.source_connector,
            source_type=event.source_type,
            external_event_id=event.external_event_id,
            source_record_id=event.source_record_id,
            occurred_at=event.occurred_at,
            citation_url=event.citation_url,
            turns=turns,
            customer_external_id=event.external_customer_id,
            customer_name=event.customer_name,
            metadata=event.metadata,
        )
