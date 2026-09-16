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
from app.models.intelligence import CustomerRevenueSnapshot, FeatureGapScore

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


class _FakeIntelligenceStore:
    async def list_feature_gap_scores(
        self, org_id: str, limit: int = 50, offset: int = 0
    ) -> list[FeatureGapScore]:
        return [
            FeatureGapScore(
                org_id=org_id,
                feature_name="Bulk CSV export",
                total_arr_at_stake=120_000.0,
                total_mrr_at_stake=10_000.0,
                customer_count=3,
                mention_count=5,
                score=987.65,
                top_customers=["Acme Corp"],
            )
        ]

    async def get_feature_gap_detail(
        self, org_id: str, feature_name: str
    ) -> tuple[FeatureGapScore | None, list[Any]]:
        if feature_name != "Bulk CSV export":
            return None, []
        score = FeatureGapScore(
            org_id=org_id,
            feature_name=feature_name,
            total_arr_at_stake=120_000.0,
            total_mrr_at_stake=10_000.0,
            customer_count=3,
            mention_count=5,
            score=987.65,
        )
        return score, []

    async def list_customers(
        self, org_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return [{"customer": {"external_customer_id": "cust-1", "customer_name": "Acme Corp"}}]

    async def get_customer_detail(self, org_id: str, external_customer_id: str) -> dict[str, Any]:
        if external_customer_id != "cust-1":
            return {"customer": None}
        return {"customer": {"external_customer_id": external_customer_id}, "latest_revenue_snapshot": None, "feature_gap_mentions": []}


class _FakeContainer:
    def __init__(self, ingestion_service: "_FakeIngestionService", store: _FakeIntelligenceStore) -> None:
        self._ingestion_service = ingestion_service
        self._store = store

    async def customer_intelligence_ingestion_service(self) -> "_FakeIngestionService":
        return self._ingestion_service

    async def intelligence_store(self) -> _FakeIntelligenceStore:
        return self._store


def _make_app(user: dict | None) -> tuple[FastAPI, _FakeIngestionService, _FakeIntelligenceStore]:
    app = FastAPI()
    app.include_router(router)
    ingestion_service = _FakeIngestionService()
    store = _FakeIntelligenceStore()
    app.container = _FakeContainer(ingestion_service, store)

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


def test_read_route_without_authenticated_user_is_rejected() -> None:
    app, _, _ = _make_app(user=None)
    client = TestClient(app)
    resp = client.get("/api/v1/intelligence/feature-gaps")
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
    user = {"orgId": ORG_ID, "isOAuth": True, "oauthScopes": ["some:other:scope"]}
    app, _, _ = _make_app(user=user)
    client = TestClient(app)
    resp = client.get("/api/v1/intelligence/feature-gaps")
    assert resp.status_code == 403


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


# ---------------------------------------------------------------------------
# Read endpoints: happy path + 404s
# ---------------------------------------------------------------------------


def test_list_feature_gaps_returns_scores() -> None:
    app, _, _ = _make_app(user=_authed_user(ORG_ID))
    client = TestClient(app)
    resp = client.get("/api/v1/intelligence/feature-gaps")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["feature_gaps"][0]["feature_name"] == "Bulk CSV export"


def test_get_feature_gap_detail_404_for_unknown_feature() -> None:
    app, _, _ = _make_app(user=_authed_user(ORG_ID))
    client = TestClient(app)
    resp = client.get("/api/v1/intelligence/feature-gaps/unknown-feature")
    assert resp.status_code == 404


def test_get_customer_detail_404_for_unknown_customer() -> None:
    app, _, _ = _make_app(user=_authed_user(ORG_ID))
    client = TestClient(app)
    resp = client.get("/api/v1/intelligence/customers/unknown-customer")
    assert resp.status_code == 404
