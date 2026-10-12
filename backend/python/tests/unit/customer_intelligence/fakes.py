"""Shared test doubles for Customer Feature Intelligence.

Only the LLM hop and embeddings are faked; tests that need persistence use
the real store on SQLite (see ``sqlite_store``).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Optional

from app.config.constants.arangodb import Connectors
from app.models.blocks import (
    Block,
    BlockGroup,
    BlocksContainer,
    BlockType,
    DataFormat,
    GroupSubType,
    GroupType,
)
from app.models.intelligence import (
    FeatureGapCandidate,
    FeatureIntelligenceExtractionResult,
    PainPoint,
)
from app.modules.customer_intelligence.matching.embedder import ITextEmbedder
from app.services.intelligence_store.mysql.mysql_intelligence_store import (
    MySQLIntelligenceStore,
)

ORG_ID = "org-123"
LOG = logging.getLogger("customer-intelligence-tests")


async def sqlite_store() -> MySQLIntelligenceStore:
    store = MySQLIntelligenceStore(logger=LOG, dsn="sqlite+aiosqlite://")
    assert await store.connect()
    return store


class FakeExtractionClient:
    """Returns canned results keyed by a substring of the (rendered, redacted) text."""

    def __init__(self, results: Optional[dict[str, FeatureIntelligenceExtractionResult]] = None) -> None:
        self.results = results or {}
        self.calls: list[dict] = []

    async def extract_feature_intelligence(
        self, text: str, org_id: str, *, infer_customer: bool = False, taxonomy=None, known_customers=None
    ) -> FeatureIntelligenceExtractionResult:
        self.calls.append(
            {"text": text, "org_id": org_id, "infer_customer": infer_customer,
             "taxonomy": taxonomy or [], "known_customers": known_customers or []}
        )
        for key, result in self.results.items():
            if key in text:
                return result.model_copy(deep=True, update={"model": "fake/llm", "prompt_version": "test"})
        return FeatureIntelligenceExtractionResult()


class KeywordEmbedder(ITextEmbedder):
    """Deterministic 'semantic' space: each axis is a concept with synonyms."""

    CONCEPTS = (
        ("export", "csv", "download", "bulk"),
        ("sso", "saml", "single", "okta"),
        ("audit", "log", "trail"),
        ("slow", "latency", "performance"),
    )

    def __init__(self, model: Optional[str] = "fake/embed") -> None:
        self.model = model
        self.calls = 0

    async def model_id(self) -> Optional[str]:
        return self.model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for text in texts:
            lower = text.lower()
            out.append([float(sum(lower.count(w) for w in words)) for words in self.CONCEPTS])
        return out


def gap(name: str, excerpt: str, **attrs) -> FeatureGapCandidate:
    return FeatureGapCandidate(feature_name=name, description=f"needs {name}", confidence=0.9, excerpt=excerpt, **attrs)


def pain(summary: str, excerpt: str, **attrs) -> PainPoint:
    return PainPoint(summary=summary, confidence=0.8, excerpt=excerpt, **attrs)


def row(index: int, text: str, row_number: int, cells: Optional[dict] = None) -> Block:
    data: dict = {"row_natural_language_text": text, "row_number": row_number}
    if cells is not None:
        data["cells"] = cells
    return Block(index=index, type=BlockType.TABLE_ROW, format=DataFormat.JSON, data=data)


def text_block(index: int, text: str, parent_index: Optional[int] = None) -> Block:
    return Block(index=index, type=BlockType.TEXT, format=DataFormat.TXT, data=text, parent_index=parent_index)


def record(
    blocks: Optional[list[Block]] = None,
    groups: Optional[list[BlockGroup]] = None,
    *,
    connector: Connectors = Connectors.KNOWLEDGE_BASE,
    record_type: str = "FILE",
    name: str = "tickets.csv",
    **extra,
) -> SimpleNamespace:
    """Stand-in for ``app.models.entities.Record`` carrying only what the pipeline reads."""
    return SimpleNamespace(
        id="rec-1",
        org_id=ORG_ID,
        record_name=name,
        record_type=record_type,
        connector_name=connector,
        record_group_type=None,
        block_containers=BlocksContainer(blocks=blocks or [], block_groups=groups or []),
        created_at=1_700_000_000_000,
        source_created_at=None,
        weburl="/record/rec-1",
        **extra,
    )


def ticket(articles: list[tuple[str, str]], **extra) -> SimpleNamespace:
    """articles: [(author, body)]; the first is the description, the rest are replies."""
    groups = []
    for i, (author, body) in enumerate(articles):
        if i == 0:
            groups.append(BlockGroup(index=0, name="Login issues", type=GroupType.TEXT_SECTION,
                                     sub_type=GroupSubType.CONTENT, data=f"# Login issues\n\n{body}"))
        else:
            groups.append(BlockGroup(index=i, parent_index=0, name=f"Comment by {author}",
                                     description=f"Comment by {author}", type=GroupType.TEXT_SECTION,
                                     sub_type=GroupSubType.COMMENT, data=body))
    return record(groups=groups, connector=Connectors.ZAMMAD, record_type="TICKET", name="Login issues", **extra)
