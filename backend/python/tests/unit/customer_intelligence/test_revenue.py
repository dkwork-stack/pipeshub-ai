"""Unit tests for revenue-only ARR/MRR helpers."""
from __future__ import annotations

import pytest

from app.modules.customer_intelligence.revenue import (
    is_revenue_source,
    parse_revenue_fields,
    revenue_source_connectors,
)


def test_default_revenue_sources_include_upload_and_chargebee() -> None:
    assert "file_upload" in revenue_source_connectors()
    assert "chargebee" in revenue_source_connectors()
    assert is_revenue_source("file_upload")
    assert is_revenue_source("Chargebee")
    assert not is_revenue_source("freshdesk")
    assert not is_revenue_source("salesforce")


def test_extra_revenue_sources_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTELLIGENCE_REVENUE_SOURCE_CONNECTORS", "stripe, zuora")
    assert is_revenue_source("stripe")
    assert is_revenue_source("zuora")
    assert is_revenue_source("file_upload")


def test_parse_revenue_from_cells_arr_and_mrr() -> None:
    fields = parse_revenue_fields(
        {"Customer": "Acme Corp", "ARR": "120000", "MRR": "10000"}
    )
    assert fields is not None
    assert fields.arr == 120_000.0
    assert fields.mrr == 10_000.0
    assert fields.customer_name == "Acme Corp"


def test_parse_revenue_arr_only_derives_mrr() -> None:
    fields = parse_revenue_fields({"arr": 24_000})
    assert fields is not None
    assert fields.arr == 24_000.0
    assert fields.mrr == 2_000.0


def test_parse_revenue_mrr_only_derives_arr() -> None:
    fields = parse_revenue_fields({"Monthly Recurring Revenue": "$1,500.50"})
    assert fields is not None
    assert fields.mrr == 1_500.50
    assert fields.arr == pytest.approx(18_006.0)


def test_parse_revenue_from_nl_row_text() -> None:
    text = "Customer Name: Globex, ARR: 50000, Ticket: Need SSO"
    fields = parse_revenue_fields(text)
    assert fields is not None
    assert fields.arr == 50_000.0
    assert fields.mrr == pytest.approx(50_000.0 / 12.0)
    assert fields.customer_name == "Globex"


def test_parse_revenue_missing_returns_none() -> None:
    assert parse_revenue_fields({"Customer": "Acme", "Notes": "Need SSO"}) is None
    assert parse_revenue_fields("") is None
    assert parse_revenue_fields({}) is None


def test_parse_arr_revenue_usd_column() -> None:
    """Real CSV header from freshservice_negative_review_1000_with_arr."""
    fields = parse_revenue_fields(
        {
            "customer_name": "Pioneer Telecom",
            "ARR Revenue (USD)": "826000",
            "subject": "Project module feels clunky",
        }
    )
    assert fields is not None
    assert fields.arr == 826_000.0
    assert fields.mrr == pytest.approx(826_000.0 / 12.0)
    assert fields.customer_name == "Pioneer Telecom"


def test_parse_arr_revenue_usd_from_nl_text() -> None:
    text = (
        "customer_name: Pioneer Telecom, subject: Project module feels clunky, "
        "ARR Revenue (USD): 826000"
    )
    fields = parse_revenue_fields(text)
    assert fields is not None
    assert fields.arr == 826_000.0
    assert fields.customer_name == "Pioneer Telecom"
