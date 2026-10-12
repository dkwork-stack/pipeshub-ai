"""Auth and org-scoping unit tests for the Customer Feature Intelligence API.

These deliberately avoid a real MySQL store or DI container: they mount the
real router on a minimal FastAPI app, inject fake store/service objects onto
``app.container`` (matching the real container's async-provider shape), and
drive ``request.state.user`` the same way the platform's real auth
middleware would. This isolates what these tests care about — auth,
scoping, and 404 handling — from storage plumbing.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api.routes.intelligence import router
from app.models.intelligence import CustomerRevenueSnapshot

ORG_ID = "org-123"
OTHER_ORG_ID = "org-456"


class _FakeIngestionService:
    def __init__(self) -> None:
        self.ingested_events = []
        self.ingested_snapshots = []

    async def ingest_signal_event(self, event) -> int:
        self.ingested_events.append(event)
        return 1

    async def ingest_revenue_snapshot(self, snapshot) -> None:
        self.ingested_snapshots.append(snapshot)


class _FakeContainer:
    def __init__(self, ingestion_service: "_FakeIngestionService") -> None:
        self._ingestion_service = ingestion_service

    async def customer_intelligence_ingestion_service(self) -> "_FakeIngestionService":
        return self._ingestion_service


def _make_app(user: dict | None) -> tuple[FastAPI, _FakeIngestionService, None]:
    app = FastAPI()
    app.include_router(router)
    ingestion_service = _FakeIngestionService()
    store = None
    app.container = _FakeContainer(ingestion_service)

    class _InjectUserMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            if user is not None:
                request.state.user = user
            return await call_next(request)


    app.add_middleware(_InjectUserMiddleware)
    return app, ingestion_service, store


def _authed_user(org_id: str = ORG_ID) -> dict[str, Any]:
    return {"orgId": org_id, "isOAuth": True, "oauthScopes": ["intelligence:read", "intelligence:write"]}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def _event(org_id: str = ORG_ID) -> dict[str, Any]:
    return {
        "org_id": org_id,
        "source_connector": "freshdesk",
        "source_type": "support_ticket",
        "external_customer_id": "cust-1",
        "customer_name": "Acme Corp",
        "external_event_id": "t-1",
        "turns": [
            {"role": "customer", "author": "Jane", "text": "We need SSO before rollout."},
            {"role": "agent", "text": "SSO is not available yet."},
        ],
    }


def test_event_route_without_authenticated_user_is_rejected() -> None:
    app, _, _ = _make_app(user=None)
    client = TestClient(app)
    resp = client.post("/api/v1/intelligence/events", json=_event())
    assert resp.status_code == 401


def test_write_route_without_authenticated_user_is_rejected() -> None:
    app, _, _ = _make_app(user=None)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/intelligence/revenue-snapshots",
        json=CustomerRevenueSnapshot(
            org_id=ORG_ID, external_customer_id="cust-1", customer_name="Acme Corp"
        ).model_dump(mode="json"),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------


def test_oauth_token_missing_required_scope_is_forbidden() -> None:
    user = {"orgId": ORG_ID, "isOAuth": True, "oauthScopes": ["intelligence:read"]}
    app, ingestion_service, _ = _make_app(user=user)
    client = TestClient(app)
    resp = client.post("/api/v1/intelligence/events", json=_event())
    assert resp.status_code == 403
    assert ingestion_service.ingested_events == []


# ---------------------------------------------------------------------------
# Org scoping — never trust client-supplied org_id
# ---------------------------------------------------------------------------


def test_ingest_revenue_snapshot_rejects_mismatched_org_id() -> None:
    app, ingestion_service, _ = _make_app(user=_authed_user(ORG_ID))
    client = TestClient(app)
    body = CustomerRevenueSnapshot(
        org_id=OTHER_ORG_ID, external_customer_id="cust-1", customer_name="Acme Corp"
    ).model_dump(mode="json")
    resp = client.post("/api/v1/intelligence/revenue-snapshots", json=body)
    assert resp.status_code == 403
    assert ingestion_service.ingested_snapshots == []


def test_ingest_revenue_snapshot_accepts_matching_org_id() -> None:
    app, ingestion_service, _ = _make_app(user=_authed_user(ORG_ID))
    client = TestClient(app)
    body = CustomerRevenueSnapshot(
        org_id=ORG_ID, external_customer_id="cust-1", customer_name="Acme Corp"
    ).model_dump(mode="json")
    resp = client.post("/api/v1/intelligence/revenue-snapshots", json=body)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert len(ingestion_service.ingested_snapshots) == 1


def test_ingest_event_rejects_mismatched_org_id() -> None:
    app, ingestion_service, _ = _make_app(user=_authed_user(ORG_ID))
    resp = TestClient(app).post("/api/v1/intelligence/events", json=_event(OTHER_ORG_ID))
    assert resp.status_code == 403
    assert ingestion_service.ingested_events == []


def test_ingest_event_accepts_conversation_turns() -> None:
    app, ingestion_service, _ = _make_app(user=_authed_user(ORG_ID))
    resp = TestClient(app).post("/api/v1/intelligence/events", json=_event())
    assert resp.status_code == 200
    (event,) = ingestion_service.ingested_events
    assert event.text == "[Customer · Jane]: We need SSO before rollout.\n\n[Agent]: SSO is not available yet."


def test_ingest_event_without_text_or_turns_is_rejected() -> None:
    app, _, _ = _make_app(user=_authed_user(ORG_ID))
    body = _event()
    body.pop("turns")
    resp = TestClient(app).post("/api/v1/intelligence/events", json=body)
    assert resp.status_code == 422


def test_legacy_read_routes_are_gone() -> None:
    app, _, _ = _make_app(user=_authed_user(ORG_ID))
    assert TestClient(app).get("/api/v1/intelligence/feature-gaps").status_code in (404, 405)
