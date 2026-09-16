"""CSV/PDF bulk-upload adapter for the Customer Feature Intelligence pipeline.

Two different jobs, two different tools — reuse, don't reinvent, either way:

* CSV (structured revenue/signal rows): read directly with the stdlib ``csv``
  module. This is tabular business data, not a document to parse, so there is
  nothing to reuse from the document pipeline here.
* PDF/any document (unstructured text, e.g. contract notes, meeting notes):
  reuse pipeshub's existing Knowledge Base upload pipeline (Node.js KB API)
  instead of re-implementing PDF parsing. The file is uploaded into a
  per-customer KB, pipeshub's existing parsing/indexing/extraction pipeline
  produces the parsed text, and we simply read it back via the existing
  ``GET /api/v1/records/{id}/content`` endpoint before handing it to our own
  intake API. No parsing logic lives in this script.

Env vars:
    PIPESHUB_API_URL           Node.js gateway, default http://localhost:3000
    PIPESHUB_ACCESS_TOKEN      Bearer token for the KB APIs above (kb:read/write/upload)
    CONNECTOR_SERVICE_URL      Python connectors service, default http://localhost:8088
    INDEXING_SERVICE_URL, INTELLIGENCE_INTAKE_TOKEN  (see intake_client.py)

Usage::

    python -m scripts.customer_intelligence.file_upload \\
        --org-id org123 --kind signal --csv tickets_export.csv

    python -m scripts.customer_intelligence.file_upload \\
        --org-id org123 --pdf contract_notes.pdf \\
        --customer-id acct_42 --customer-name "Acme Corp"
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from datetime import datetime, timezone

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.customer_intelligence.intake_client import (
    IntelligenceIntakeClient,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("file_upload")

_POLL_INTERVAL_SECONDS = 3
_POLL_TIMEOUT_SECONDS = 300


async def upload_signal_csv(org_id: str, csv_path: str) -> int:
    intake = IntelligenceIntakeClient()
    events_sent = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            event = {
                "org_id": org_id,
                "source_connector": "file_upload",
                "source_type": "document_upload",
                "external_customer_id": row["external_customer_id"],
                "customer_name": row.get("customer_name") or row["external_customer_id"],
                "external_event_id": row.get("external_event_id") or f"{csv_path}:{events_sent}",
                "text": row["text"],
                "occurred_at": row.get("occurred_at") or datetime.now(timezone.utc).isoformat(),
                "citation_url": row.get("citation_url") or None,
                "metadata": {"source_file": os.path.basename(csv_path)},
            }
            await intake.send_event(event)
            events_sent += 1
    logger.info("✅ Sent %d signal event(s) from %s for org '%s'", events_sent, csv_path, org_id)
    return events_sent


async def upload_revenue_csv(org_id: str, csv_path: str) -> int:
    intake = IntelligenceIntakeClient()
    snapshots_sent = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            snapshot = {
                "org_id": org_id,
                "source_connector": "file_upload",
                "external_customer_id": row["external_customer_id"],
                "customer_name": row.get("customer_name") or row["external_customer_id"],
                "mrr": float(row.get("mrr") or 0),
                "arr": float(row.get("arr") or (float(row.get("mrr") or 0) * 12)),
                "seats_used": int(row["seats_used"]) if row.get("seats_used") else None,
                "seats_licensed": int(row["seats_licensed"]) if row.get("seats_licensed") else None,
                "consumed_features": [],
                "renewal_date": row.get("renewal_date") or None,
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
            }
            await intake.send_revenue_snapshot(snapshot)
            snapshots_sent += 1
    logger.info("✅ Sent %d revenue snapshot(s) from %s for org '%s'", snapshots_sent, csv_path, org_id)
    return snapshots_sent


class _KnowledgeBaseUploader:
    """Thin orchestration wrapper around pipeshub's existing KB upload pipeline.

    Owns exactly one responsibility: get a file's parsed text out of pipeshub
    by reusing its existing APIs (find-or-create KB, upload, poll, fetch
    content). It does not parse anything itself.
    """

    def __init__(self) -> None:
        self.api_base = os.environ.get("PIPESHUB_API_URL", "http://localhost:3000").rstrip("/")
        self.connector_base = os.environ.get("CONNECTOR_SERVICE_URL", "http://localhost:8088").rstrip("/")
        token = os.environ["PIPESHUB_ACCESS_TOKEN"]
        self.headers = {"Authorization": f"Bearer {token}"}

    async def _find_or_create_kb(self, client: httpx.AsyncClient, kb_name: str) -> str:
        list_resp = await client.get(f"{self.api_base}/api/v1/kb", headers=self.headers)
        list_resp.raise_for_status()
        for kb in _extract_list(list_resp.json()):
            if kb.get("name") == kb_name or kb.get("kbName") == kb_name:
                return kb.get("id") or kb.get("_key") or kb.get("kbId")

        create_resp = await client.post(
            f"{self.api_base}/api/v1/kb", json={"kbName": kb_name}, headers=self.headers
        )
        create_resp.raise_for_status()
        kb_id = _extract_id(create_resp.json())
        if not kb_id:
            raise RuntimeError(f"Could not determine kbId from create-KB response: {create_resp.json()}")
        return kb_id

    async def upload_and_extract_text(self, file_path: str, customer_name: str) -> str:
        kb_name = f"Customer Feature Intelligence - {customer_name}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            kb_id = await self._find_or_create_kb(client, kb_name)

            with open(file_path, "rb") as f:
                upload_resp = await client.post(
                    f"{self.api_base}/api/v1/kb/{kb_id}/upload",
                    headers=self.headers,
                    files={"files": (os.path.basename(file_path), f)},
                )
            upload_resp.raise_for_status()
            record_id = _extract_id(upload_resp.json())
            if not record_id:
                raise RuntimeError(f"Could not determine recordId from upload response: {upload_resp.json()}")

            await self._wait_for_extraction(client, record_id)

            content_resp = await client.get(
                f"{self.connector_base}/api/v1/records/{record_id}/content", headers=self.headers
            )
            content_resp.raise_for_status()
            return content_resp.json().get("content", "")

    async def _wait_for_extraction(self, client: httpx.AsyncClient, record_id: str) -> None:
        elapsed = 0
        while elapsed < _POLL_TIMEOUT_SECONDS:
            resp = await client.get(f"{self.api_base}/api/v1/kb/record/{record_id}", headers=self.headers)
            resp.raise_for_status()
            record = _extract_record(resp.json())
            status = record.get("extractionStatus")
            if status == "COMPLETED":
                return
            if status == "FAILED":
                raise RuntimeError(f"Extraction failed for record {record_id}")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS
        raise TimeoutError(f"Record {record_id} did not finish extraction within {_POLL_TIMEOUT_SECONDS}s")


def _extract_list(body: dict) -> list[dict]:
    for key in ("knowledgeBases", "data", "items", "results"):
        value = body.get(key) if isinstance(body, dict) else None
        if isinstance(value, list):
            return value
    return []


def _extract_id(body: dict) -> str | None:
    """Best-effort extraction of an id from a variety of response shapes."""
    if not isinstance(body, dict):
        return None
    for key in ("id", "kbId", "recordId", "_key"):
        if body.get(key):
            return body[key]
    for container_key in ("data", "kb", "record", "records"):
        nested = body.get(container_key)
        if isinstance(nested, dict):
            found = _extract_id(nested)
            if found:
                return found
        if isinstance(nested, list) and nested:
            found = _extract_id(nested[0])
            if found:
                return found
    return None


def _extract_record(body: dict) -> dict:
    if not isinstance(body, dict):
        return {}
    if "record" in body and isinstance(body["record"], dict):
        return body["record"]
    data = body.get("data")
    if isinstance(data, dict) and isinstance(data.get("record"), dict):
        return data["record"]
    return body


async def upload_document(org_id: str, file_path: str, customer_id: str, customer_name: str) -> int:
    uploader = _KnowledgeBaseUploader()
    text = await uploader.upload_and_extract_text(file_path, customer_name)
    if not text.strip():
        logger.warning("No extractable text for %s", file_path)
        return 0

    intake = IntelligenceIntakeClient()
    event = {
        "org_id": org_id,
        "source_connector": "file_upload",
        "source_type": "document_upload",
        "external_customer_id": customer_id,
        "customer_name": customer_name,
        "external_event_id": os.path.basename(file_path),
        "text": text,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "citation_url": None,
        "metadata": {"source_file": os.path.basename(file_path)},
    }
    await intake.send_event(event)
    logger.info("✅ Sent 1 document_upload event for %s (customer '%s')", file_path, customer_name)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--kind", choices=["signal", "revenue"], default="signal")
    parser.add_argument("--csv", help="Path to a CSV file (structured rows)")
    parser.add_argument("--pdf", dest="document", help="Path to a PDF/other document — uploaded via the existing KB pipeline")
    parser.add_argument("--customer-id", help="Required with --pdf")
    parser.add_argument("--customer-name", help="Required with --pdf")
    args = parser.parse_args()

    if args.csv:
        if args.kind == "signal":
            asyncio.run(upload_signal_csv(args.org_id, args.csv))
        else:
            asyncio.run(upload_revenue_csv(args.org_id, args.csv))
    elif args.document:
        if not args.customer_id or not args.customer_name:
            parser.error("--pdf requires --customer-id and --customer-name")
        asyncio.run(upload_document(args.org_id, args.document, args.customer_id, args.customer_name))
    else:
        parser.error("one of --csv or --pdf is required")


if __name__ == "__main__":
    main()
