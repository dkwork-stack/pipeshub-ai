"""Name normalisation shared by matching, pipeline stages and evals."""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_CORP_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|gmbh|pty|plc|corp|corporation|co|company|sa|ag)\b\.?",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    return _WS.sub(" ", (value or "").strip().lower())


def normalize_name(value: str) -> str:
    cleaned = _PUNCT.sub(" ", normalize_text(value))
    return _WS.sub(" ", cleaned).strip()


def normalize_customer_name(value: str) -> str:
    cleaned = normalize_name(value)
    cleaned = _CORP_SUFFIXES.sub("", cleaned)
    return _WS.sub(" ", cleaned).strip()
