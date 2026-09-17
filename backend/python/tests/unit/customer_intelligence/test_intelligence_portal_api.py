"""Auth, org-scoping and contract tests for the intelligence portal API.

Mounts the real portal router on a minimal FastAPI app with a fake
``IIntelligenceQueryRepository`` wired through the real query services, and
drives ``request.state.user`` the way ``authMiddleware`` would. Storage is
covered separately in ``test_query_repository.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.routes.intelligence_portal.router import router
from app.models.intelligence import (
    AffectedCustomer,
    CustomerDetail,
    CustomerFilter,
    CustomerInsight,
    CustomerSummary,
    FeatureGapDetail,
    FeatureGapFilter,
    FeatureGapMentionRecord,
    FeatureGapScore,
    IntelligenceOverview,
    MentionFilter,
    RevenueSummary,
    SignalSourceType,
)
from app.modules.customer_intelligence.queries.services import (
    CustomerQueryService,
    FeatureGapQueryService,
    OverviewQueryService,
)

if TYPE_CHECKING:
    from starlette.responses import Response

ORG_ID = "org-123"
NOW = datetime(2025, 3, 1, 9, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _score(org_id: str, name: str = "Bulk CSV export") -> FeatureGapScore:
    return FeatureGapScore(
        org_id=org_id,
        feature_name=name,
        total_arr_at_stake=120_000.0,
        total_mrr_at_stake=10_000.0,
        customer_count=3,
        mention_count=5,
        score=987.65,
        top_customers=["Acme Corp"],
    )


def _mention(org_id: str) -> FeatureGapMentionRecord:
    return FeatureGapMentionRecord(
        org_id=org_id,
        external_customer_id="cust-1",
        feature_name="Bulk CSV export",
        description="Wants export",
        confidence=0.9,
        excerpt="we need CSV export",
        source_connector="freshdesk",
        source_type=SignalSourceType.SUPPORT_TICKET,
        external_event_id="t-1",
        citation_url="https://freshdesk/t-1",
        occurred_at=NOW,
    )


def _customer() -> CustomerSummary:
    return CustomerSummary(
        external_customer_id="cust-1",
        customer_name="Acme Corp",
        latest_revenue=RevenueSummary(source_connector="chargebee", mrr=10_000, arr=120_000, snapshot_at=NOW),
        feature_gap_count=1,
        mention_count=2,
        top_insights=[
            CustomerInsight(
                feature_name="Bulk CSV export", mention_count=2, max_confidence=0.9, last_mentioned_at=NOW,
                source_connectors=["freshdesk"],
            )
        ],
    )


class _FakeRepository:
    """Records every call so tests can assert org scoping and filter plumbing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self.calls.append((name, args, kwargs))

    async def get_overview(self, org_id: str, *, top_n: int = 5) -> IntelligenceOverview:
        self._record("get_overview", org_id, top_n=top_n)
        return IntelligenceOverview(
            total_arr_at_stake=150_000, feature_gap_count=3, customer_count=2, mention_count=5,
            source_connectors=["freshdesk"], top_feature_gaps=[_score(org_id)], top_customers=[_customer()],
            last_mention_at=NOW,
        )

    async def search_feature_gaps(
        self, org_id: str, filters: FeatureGapFilter, *, limit: int, offset: int
    ) -> tuple[list[FeatureGapScore], int]:
        self._record("search_feature_gaps", org_id, filters, limit=limit, offset=offset)
        return [_score(org_id)], 7

    async def get_feature_gap(
        self, org_id: str, feature_name: str, mention_filter: MentionFilter
    ) -> Optional[FeatureGapDetail]:
        self._record("get_feature_gap", org_id, feature_name, mention_filter)
        if feature_name != "Bulk CSV export":
            return None
        return FeatureGapDetail(
            score=_score(org_id, feature_name),
            affected_customers=[AffectedCustomer(external_customer_id="cust-1", customer_name="Acme Corp", arr=120_000, mention_count=2)],
            mentions=[_mention(org_id)],
        )

    async def search_customers(
        self, org_id: str, filters: CustomerFilter, *, limit: int, offset: int, top_insights: int = 3
    ) -> tuple[list[CustomerSummary], int]:
        self._record("search_customers", org_id, filters, limit=limit, offset=offset, top_insights=top_insights)
        return [_customer()], 1

    async def get_customer(
        self, org_id: str, external_customer_id: str, mention_filter: MentionFilter
    ) -> Optional[CustomerDetail]:
        self._record("get_customer", org_id, external_customer_id, mention_filter)
        if external_customer_id != "cust-1":
            return None
        return CustomerDetail(**_customer().model_dump(), insights=_customer().top_insights, mentions=[_mention(org_id)])

    async def list_source_connectors(self, org_id: str) -> list[str]:
        self._record("list_source_connectors", org_id)
        return ["freshdesk", "gong"]


class _FakeContainer:
    def __init__(self, repo: _FakeRepository) -> None:
        self._overview = OverviewQueryService(repo)
        self._gaps = FeatureGapQueryService(repo)
        self._customers = CustomerQueryService(repo)

    async def overview_query_service(self) -> OverviewQueryService:
        return self._overview

    async def feature_gap_query_service(self) -> FeatureGapQueryService:
        return self._gaps

    async def customer_query_service(self) -> CustomerQueryService:
        return self._customers


def _make_app(user: dict | None) -> tuple[TestClient, _FakeRepository]:
    app = FastAPI()
    app.include_router(router)
    repo = _FakeRepository()
    app.container = _FakeContainer(repo)

    class _InjectUserMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            if user is not None:
                request.state.user = user
            return await call_next(request)

    app.add_middleware(_InjectUserMiddleware)
    return TestClient(app), repo


def _authed_user(org_id: str = ORG_ID, scopes: tuple[str, ...] = ("intelligence:read",)) -> dict[str, Any]:
    return {"orgId": org_id, "isOAuth": True, "oauthScopes": list(scopes)}


BASE = "/api/v1/intelligence-portal"


def test_unauthenticated_requests_are_rejected() -> None:
    client, repo = _make_app(user=None)
    for path in ("/overview", "/feature-gaps", "/feature-gaps/x", "/customers", "/customers/x", "/filters/source-connectors"):
        assert client.get(f"{BASE}{path}").status_code == 401, path
    assert repo.calls == []


def test_oauth_token_without_read_scope_is_forbidden() -> None:
    client, _ = _make_app(user=_authed_user(scopes=("some:other",)))
    assert client.get(f"{BASE}/overview").status_code == 403


def test_session_jwt_without_scopes_passes() -> None:
    client, _ = _make_app(user={"orgId": ORG_ID, "isOAuth": False})
    assert client.get(f"{BASE}/overview").status_code == 200


def test_overview_is_scoped_to_token_org() -> None:
    client, repo = _make_app(user=_authed_user("org-999"))
    resp = client.get(f"{BASE}/overview?orgId={ORG_ID}")
    assert resp.status_code == 200
    assert repo.calls[0][1] == ("org-999",)
    body = resp.json()
    assert body["total_arr_at_stake"] == 150_000
    assert body["top_feature_gaps"][0]["feature_name"] == "Bulk CSV export"
    assert body["top_customers"][0]["top_insights"][0]["mention_count"] == 2
    assert "org_id" not in body["top_feature_gaps"][0]


def test_overview_plumbs_top_n() -> None:
    client, repo = _make_app(user=_authed_user())
    assert client.get(f"{BASE}/overview", params={"top_n": 10}).status_code == 200
    assert repo.calls[0][2] == {"top_n": 10}
    assert client.get(f"{BASE}/overview", params={"top_n": 0}).status_code == 422
    assert client.get(f"{BASE}/overview", params={"top_n": 99}).status_code == 422


def test_feature_gap_search_plumbs_filters_and_pagination() -> None:
    client, repo = _make_app(user=_authed_user())
    resp = client.get(
        f"{BASE}/feature-gaps",
        params={"q": "  csv ", "min_arr": 1000, "source_connector": "gong", "customer_id": "cust-1", "limit": 10, "offset": 20},
    )
    assert resp.status_code == 200
    name, args, kwargs = repo.calls[0]
    assert name == "search_feature_gaps"
    assert args[0] == ORG_ID
    assert args[1] == FeatureGapFilter(query="csv", min_arr=1000, source_connector="gong", external_customer_id="cust-1")
    assert kwargs == {"limit": 10, "offset": 20}
    body = resp.json()
    assert body["page"] == {"total": 7, "limit": 10, "offset": 20, "has_more": False}
    assert body["items"][0]["feature_name"] == "Bulk CSV export"


def test_pagination_bounds_are_validated() -> None:
    client, _ = _make_app(user=_authed_user())
    assert client.get(f"{BASE}/feature-gaps", params={"limit": 0}).status_code == 422
    assert client.get(f"{BASE}/feature-gaps", params={"limit": 999}).status_code == 422
    assert client.get(f"{BASE}/customers", params={"offset": -1}).status_code == 422
    assert client.get(f"{BASE}/customers", params={"min_arr": -5}).status_code == 422


def test_feature_gap_detail_with_mention_filters_and_404() -> None:
    client, repo = _make_app(user=_authed_user())
    resp = client.get(f"{BASE}/feature-gaps/Bulk%20CSV%20export", params={"customer_id": "cust-1", "source_connector": "freshdesk"})
    assert resp.status_code == 200
    _, args, _ = repo.calls[0]
    assert args == (ORG_ID, "Bulk CSV export", MentionFilter(external_customer_id="cust-1", source_connector="freshdesk"))
    body = resp.json()
    assert body["affected_customers"][0]["customer_name"] == "Acme Corp"
    assert body["mentions"][0]["citation_url"] == "https://freshdesk/t-1"
    assert body["mentions"][0]["source_type"] == "support_ticket"

    assert client.get(f"{BASE}/feature-gaps/Unknown").status_code == 404


def test_feature_gap_names_with_slashes_resolve() -> None:
    client, repo = _make_app(user=_authed_user())
    client.get(f"{BASE}/feature-gaps/Export/Import%20API")
    assert repo.calls[0][1][1] == "Export/Import API"


def test_customer_list_and_detail() -> None:
    client, repo = _make_app(user=_authed_user())
    resp = client.get(f"{BASE}/customers", params={"q": "acme", "min_arr": 50_000})
    assert resp.status_code == 200
    _, args, kwargs = repo.calls[0]
    assert args == (ORG_ID, CustomerFilter(query="acme", min_arr=50_000))
    assert kwargs["top_insights"] == 3
    item = resp.json()["items"][0]
    assert item["latest_revenue"]["arr"] == 120_000
    assert item["top_insights"][0]["feature_name"] == "Bulk CSV export"

    resp = client.get(f"{BASE}/customers/cust-1", params={"source_connector": "freshdesk"})
    assert resp.status_code == 200
    assert repo.calls[1][1] == (ORG_ID, "cust-1", MentionFilter(source_connector="freshdesk"))
    body = resp.json()
    assert body["insights"][0]["mention_count"] == 2
    assert body["mentions"][0]["excerpt"] == "we need CSV export"

    assert client.get(f"{BASE}/customers/nope").status_code == 404


def test_source_connectors_filter_options() -> None:
    client, _ = _make_app(user=_authed_user())
    resp = client.get(f"{BASE}/filters/source-connectors")
    assert resp.status_code == 200
    assert resp.json() == {"source_connectors": ["freshdesk", "gong"]}
