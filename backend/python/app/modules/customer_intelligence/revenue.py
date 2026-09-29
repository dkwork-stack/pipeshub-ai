"""Revenue-only ARR/MRR helpers.

ARR/MRR may only be written from allowlisted sources (file upload, billing).
Signal connectors identify customers; they must not invent revenue.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

_DEFAULT_REVENUE_SOURCES = frozenset({"file_upload", "chargebee"})

_ARR_KEYS = frozenset(
    {
        "arr",
        "annual recurring revenue",
        "annual_recurring_revenue",
        "annualrevenue",
        "annual revenue",
    }
)
_MRR_KEYS = frozenset(
    {
        "mrr",
        "monthly recurring revenue",
        "monthly_recurring_revenue",
        "monthlyrevenue",
        "monthly revenue",
    }
)
_CUSTOMER_KEYS = frozenset(
    {
        "customer",
        "customer_name",
        "customer name",
        "account",
        "account_name",
        "account name",
        "company",
        "company_name",
        "company name",
    }
)

# "Col: val, Col2: val2" from generate_simple_row_text — split on ", " only when
# the next token looks like a new "key: " header (keys rarely contain commas).
_NL_PAIR = re.compile(r"(?:^|,\s*)([^:,]+):\s*", re.UNICODE)
_MONEY_NOISE = re.compile(r"[\s,$]")


@dataclass(frozen=True)
class RevenueFields:
    """Parsed revenue + optional customer name from a tabular row."""

    arr: float
    mrr: float
    customer_name: Optional[str] = None


def revenue_source_connectors() -> frozenset[str]:
    extras = os.getenv("INTELLIGENCE_REVENUE_SOURCE_CONNECTORS", "")
    extra = {p.strip() for p in extras.split(",") if p.strip()}
    return _DEFAULT_REVENUE_SOURCES | extra


def is_revenue_source(connector: str) -> bool:
    return (connector or "").strip().lower() in {
        c.lower() for c in revenue_source_connectors()
    }


def parse_revenue_fields(row: Mapping[str, Any] | str) -> Optional[RevenueFields]:
    """Extract ARR/MRR (and optional customer name) from cells or NL row text.

    Returns None when neither ARR nor MRR is present or parseable.
    Missing ARR is derived as MRR×12; missing MRR as ARR/12.
    """
    cells = _as_cells(row)
    if not cells:
        return None

    arr = _first_money(cells, _ARR_KEYS)
    mrr = _first_money(cells, _MRR_KEYS)
    if arr is None and mrr is None:
        return None
    if arr is None and mrr is not None:
        arr = mrr * 12.0
    if mrr is None and arr is not None:
        mrr = arr / 12.0

    name = _first_string(cells, _CUSTOMER_KEYS)
    return RevenueFields(arr=float(arr), mrr=float(mrr), customer_name=name)


def _as_cells(row: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return {str(k): v for k, v in row.items()}
    if isinstance(row, str) and row.strip():
        return _parse_nl_row(row)
    return {}


def _parse_nl_row(text: str) -> dict[str, Any]:
    matches = list(_NL_PAIR.finditer(text))
    if not matches:
        return {}
    out: dict[str, Any] = {}
    for i, match in enumerate(matches):
        key = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].rstrip(", ").strip()
        out[key] = value
    return out


def _norm_key(key: str) -> str:
    return re.sub(r"\s+", " ", (key or "").strip().lower())


def _first_money(cells: Mapping[str, Any], keys: frozenset[str]) -> Optional[float]:
    for key, value in cells.items():
        if _norm_key(key) in keys:
            parsed = _parse_money(value)
            if parsed is not None:
                return parsed
    return None


def _first_string(cells: Mapping[str, Any], keys: frozenset[str]) -> Optional[str]:
    for key, value in cells.items():
        if _norm_key(key) in keys:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"null", "none", "n/a"}:
                return text
    return None


def _parse_money(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _MONEY_NOISE.sub("", str(value).strip())
    if not text or text.lower() in {"null", "none", "n/a", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
