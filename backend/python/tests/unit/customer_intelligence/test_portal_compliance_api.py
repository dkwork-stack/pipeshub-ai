"""Portal API: curation and compliance endpoints, through the real services and store (SQLite)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes.intelligence_portal.router import router
from app.models.intelligence import (
    CustomerRevenueSnapshot,
    FeatureGapMentionRecord,
    IntelligenceTopic,
    SignalSourceType,
    TopicKind,
)
from app.modules.customer_intelligence.queries.services import (
    ComplianceService,
    CustomerQueryService,
    FeatureGapQueryService,
    OverviewQueryService,
    PainPointQueryService,
    TopicService,
)
from app.services.intelligence_store.mysql.mysql_intelligence_query_repository import (
    MySQLIntelligenceQueryRepository,
)
from app.services.intelligence_store.mysql.sql import utcnow
from tests.unit.customer_intelligence.fakes import LOG, ORG_ID

READ = ["intelligence:read"]
WRITE = ["intelligence:read", "intelligence:write"]


class _Container:
    def __init__(self, store, repo) -> None:
        self._services = {
            "overview_query_service": OverviewQueryService(repo),
            "feature_gap_query_service": FeatureGapQueryService(repo),
            "pain_point_query_service": PainPointQueryService(repo),
            "customer_query_service": CustomerQueryService(repo),
            "topic_service": TopicService(store),
            "compliance_service": ComplianceService(store),
        }

    def __getattr__(self, name):
        service = self._services[name]

        async def provide():
            return service

        return provide


@pytest.fixture
def portal():
    """Store, repo and app share one event loop: TestClient runs the app on its own loop thread."""
    from app.services.intelligence_store.mysql.mysql_intelligence_store import MySQLIntelligenceStore

    def build(scopes: list[str]):
        app = FastAPI()
        app.include_router(router)

        class _User(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                request.state.user = {"orgId": ORG_ID, "userId": "pm-1", "isOAuth": True, "oauthScopes": scopes}
                return await call_next(request)

        app.add_middleware(_User)
        client = TestClient(app)
        client.__enter__()
        store = MySQLIntelligenceStore(logger=LOG, dsn="sqlite+aiosqlite://")
        portal_loop = client.portal

        async def setup():
            assert await store.connect()
            await store.upsert_revenue_snapshot(
                CustomerRevenueSnapshot(org_id=ORG_ID, source_connector="file_upload", external_customer_id="acme",
                                        customer_name="Acme", arr=100_000, mrr=8_000)
            )
            for event in ("t1", "t2"):
                await store.upsert_feature_gap_mention(
                    FeatureGapMentionRecord(
                        org_id=ORG_ID, external_customer_id="acme", feature_name="SSO", description="d",
                        confidence=0.9, excerpt="need sso", source_connector="zammad",
                        source_type=SignalSourceType.SUPPORT_TICKET, external_event_id=event,
                        occurred_at=utcnow() - timedelta(days=1), source_record_id=f"rec-{event}",
                        churn_risk=True,
                    )
                )
            await store.upsert_topic(IntelligenceTopic(org_id=ORG_ID, kind=TopicKind.FEATURE_GAP, canonical_name="SSO"))
            app.container = _Container(store, MySQLIntelligenceQueryRepository(logger=LOG, engine=store.engine))

        portal_loop.call(setup)
        return client, store

    clients = []

    def factory(scopes):
        client, store = build(scopes)
        clients.append(client)
        return client, store

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def test_customer_erasure_requires_write_scope(portal) -> None:
    client, _ = portal(READ)
    assert client.delete("/api/v1/intelligence-portal/customers/acme").status_code == 403


def test_customer_erasure_deletes_everything_and_is_audited(portal) -> None:
    client, _ = portal(WRITE)
    resp = client.delete("/api/v1/intelligence-portal/customers/acme")
    assert resp.status_code == 200
    assert resp.json() == {"customers": 1, "feature_gap_mentions": 2, "pain_point_mentions": 0, "revenue_snapshots": 1}
    assert client.get("/api/v1/intelligence-portal/customers/acme").status_code == 404
    gap = client.get("/api/v1/intelligence-portal/feature-gaps").json()["items"][0]
    assert (gap["customer_count"], gap["total_arr_at_stake"]) == (0, 0.0)

    audit = client.get("/api/v1/intelligence-portal/audit").json()
    (entry,) = audit["items"]
    assert (entry["action"], entry["target_id"], entry["actor"]) == ("erasure.customer", "acme", "pm-1")
    assert client.delete("/api/v1/intelligence-portal/customers/acme").status_code == 404


def test_source_record_erasure(portal) -> None:
    client, _ = portal(WRITE)
    resp = client.delete("/api/v1/intelligence-portal/records/rec-t1")
    assert resp.json()["feature_gap_mentions"] == 1
    assert client.get("/api/v1/intelligence-portal/feature-gaps").json()["items"][0]["mention_count"] == 1


def test_audit_log_requires_write_scope(portal) -> None:
    client, _ = portal(READ)
    assert client.get("/api/v1/intelligence-portal/audit").status_code == 403


def test_topic_status_update_is_audited_and_filterable(portal) -> None:
    client, _ = portal(WRITE)
    topic = client.get("/api/v1/intelligence-portal/topics?kind=feature_gap").json()[0]
    resp = client.patch(f"/api/v1/intelligence-portal/topics/{topic['id']}", json={"status": "planned"})
    assert resp.status_code == 200 and resp.json()["status"] == "planned"

    planned = client.get("/api/v1/intelligence-portal/feature-gaps?status=planned").json()
    assert [g["feature_name"] for g in planned["items"]] == ["SSO"]
    assert planned["items"][0]["status"] == "planned"
    assert client.get("/api/v1/intelligence-portal/feature-gaps?status=open").json()["items"] == []
    assert client.get("/api/v1/intelligence-portal/feature-gaps?status=bogus").status_code == 422
    (entry,) = client.get("/api/v1/intelligence-portal/audit").json()["items"]
    assert entry["action"] == "topic.update" and entry["details"] == {"status": "planned", "updated_by": "pm-1"}


def test_evidence_and_health_reach_the_wire(portal) -> None:
    client, _ = portal(READ)
    detail = client.get("/api/v1/intelligence-portal/feature-gaps/SSO").json()
    assert detail["mentions"][0]["churn_risk"] is True
    assert detail["mentions"][0]["source_record_id"] in {"rec-t1", "rec-t2"}
    assert detail["trend"]["churn_risk_count"] == 2
    at_risk = client.get("/api/v1/intelligence-portal/customers?at_risk=true").json()["items"]
    assert at_risk[0]["health"]["at_risk"] is True
    overview = client.get("/api/v1/intelligence-portal/overview").json()
    assert overview["at_risk_customers"][0]["external_customer_id"] == "acme"
    assert overview["emerging_feature_gaps"][0]["feature_name"] == "SSO"


def test_topic_rename_rejects_empty_names(portal) -> None:
    client, _ = portal(WRITE)
    topic = client.get("/api/v1/intelligence-portal/topics").json()[0]
    assert client.patch(f"/api/v1/intelligence-portal/topics/{topic['id']}", json={"canonical_name": ""}).status_code == 422

