"""LLM-based extraction of customer pain points and product feature gaps.

Runs in the standalone Extraction Service (:8093), alongside
``DocumentExtraction``. Deliberately independent of the document
classification path — different prompt, different schema — so it can be
called directly for a single CustomerSignalEvent's text without needing a
full BlocksContainer/record.
"""
from __future__ import annotations

import re
from logging import Logger
from typing import Optional

from langchain_core.messages import HumanMessage

from app.config.configuration_service import ConfigurationService
from app.models.intelligence import (
    FeatureIntelligenceExtractionResult,
    TaxonomyHint,
    TopicKind,
)
from app.utils.llm import get_llm_for_role
from app.utils.streaming import invoke_with_structured_output_and_reflection

_TAXONOMY_CAP_PER_KIND = 100

FEATURE_INTELLIGENCE_PROMPT = """You are a product-management analyst. Read the customer-facing text below \
(a support ticket, CRM note, call-transcript excerpt, or uploaded document) and extract two things, \
grounded strictly in the text:

1. pain_points: concrete problems/frustrations the customer expressed. For each, include a short summary, \
sentiment (Positive|Neutral|Negative), a confidence score (0-1), a verbatim excerpt copied from the text \
that supports it, and topic_id when the item matches a Known topic below (otherwise null).
2. feature_gaps: specific product features or capabilities the customer is asking for, or that would resolve \
their pain point, that do not appear to exist today. For each, include a short, normalized feature_name \
(e.g. "Bulk CSV export", not a full sentence), a one-sentence description of what's needed and why, a \
confidence score (0-1), a verbatim excerpt copied from the text that supports it, and topic_id when the \
item matches a Known topic below (otherwise null).

Rules:
- Only extract what is explicitly supported by the text. Do not invent excerpts — they must be copied verbatim.
- If there is no clear pain point or feature gap, return empty lists.
- Prefer Known topics: when an item matches a known topic (by name or alias), set topic_id to that topic's \
id and use its canonical name for feature_name / summary. Follow each topic's guidance (include/exclude).
- Propose a new name only when nothing in Known topics fits. Normalize new names so the same underlying \
request from different customers uses the same wording (e.g. always "SSO / SAML support").
{known_topics_block}
{known_customers_block}
{customer_instruction}
Text:
---
{text}
---
"""

# Appended only for sources that carry no customer identity of their own
# (Knowledge Base uploads); tickets/CRM notes already know their customer.
_CUSTOMER_INSTRUCTION = """
3. customer_name: the customer/account/company the text is about (e.g. from a "Customer:" or \
"Account:" field, a signature, or the company named in the text). Prefer an exact spelling from \
Known customers when one matches. Return null if the text does not identify one. Never guess; \
never return the vendor's own name.
"""

# A lightweight pre-tagger: cheap keyword screen so obviously irrelevant text
# (e.g. a one-line "thanks, resolved!" ticket) skips the LLM call entirely.
# It only ever short-circuits toward "skip"; every candidate is still fully
# classified by the LLM, never the other way around.
_SIGNAL_KEYWORDS = re.compile(
    r"\b(feature|support|add|missing|unable|can'?t|doesn'?t|does not|need|request|"
    r"wish|would like|integrat|export|import|limit|slow|bug|issue|problem|broken|"
    r"upgrade|renew|cancel|churn)\b",
    re.IGNORECASE,
)


def has_extractable_signal(text: str) -> bool:
    """Cheap keyword screen used before spending an LLM call. See module docstring."""
    return bool(text and _SIGNAL_KEYWORDS.search(text))


def _format_taxonomy(taxonomy: list[TaxonomyHint]) -> str:
    if not taxonomy:
        return ""
    # Cap per kind so the prompt stays bounded.
    by_kind: dict[str, list[TaxonomyHint]] = {}
    for hint in taxonomy:
        kind = hint.kind.value if isinstance(hint.kind, TopicKind) else str(hint.kind)
        by_kind.setdefault(kind, []).append(hint)
    lines = ["Known topics (reuse topic_id when matching):"]
    for kind, hints in by_kind.items():
        for hint in hints[:_TAXONOMY_CAP_PER_KIND]:
            aliases = f" aliases=[{', '.join(hint.aliases)}]" if hint.aliases else ""
            guidance = f" guidance=\"{hint.guidance}\"" if hint.guidance else ""
            lines.append(f"- id={hint.id} kind={kind} name=\"{hint.name}\"{aliases}{guidance}")
    return "\n".join(lines) + "\n"


def _format_customers(known_customers: list[str]) -> str:
    if not known_customers:
        return ""
    names = ", ".join(f'"{n}"' for n in known_customers[:200])
    return f"Known customers (prefer these spellings): {names}\n"


class FeatureIntelligenceExtractor:
    def __init__(self, logger: Logger, config_service: ConfigurationService) -> None:
        self.logger = logger
        self.config_service = config_service

    async def extract(
        self,
        text: str,
        org_id: str,
        *,
        infer_customer: bool = False,
        taxonomy: Optional[list[TaxonomyHint]] = None,
        known_customers: Optional[list[str]] = None,
    ) -> FeatureIntelligenceExtractionResult | None:
        if not text or not text.strip():
            return None
        if not has_extractable_signal(text):
            self.logger.debug("⏭️ Skipping LLM extraction: no signal keywords found")
            return FeatureIntelligenceExtractionResult()

        llm, _config = await get_llm_for_role(self.config_service, "indexing", reasoning_effort="low")
        prompt = FEATURE_INTELLIGENCE_PROMPT.format(
            text=text[:20000],
            customer_instruction=_CUSTOMER_INSTRUCTION if infer_customer else "",
            known_topics_block=_format_taxonomy(taxonomy or []),
            known_customers_block=_format_customers(known_customers or []) if infer_customer else "",
        )
        messages = [HumanMessage(content=prompt)]
        try:
            parsed = await invoke_with_structured_output_and_reflection(
                llm, messages, FeatureIntelligenceExtractionResult
            )
            return parsed if parsed is not None else FeatureIntelligenceExtractionResult()
        except Exception as e:
            self.logger.error(f"❌ Feature intelligence extraction failed for org '{org_id}': {e}")
            raise
