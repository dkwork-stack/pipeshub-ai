"""Chargebee DataSource — subscriptions/customers needed for revenue snapshots.

Deliberately minimal (unlike the auto-generated Freshdesk/Salesforce
wrappers): only the endpoints the Customer Feature Intelligence pipeline
needs. Extend as more Chargebee data (invoices, add-ons, etc.) becomes
relevant.
"""
import logging
from typing import Any, Optional
from urllib.parse import urlencode

from app.sources.client.chargebee.chargebee import ChargebeeClient, ChargebeeResponse
from app.sources.client.http.http_request import HTTPRequest
from app.sources.client.http.http_response import HTTPResponse

logger = logging.getLogger(__name__)

HTTP_ERROR_THRESHOLD = 400


class ChargebeeDataSource:
    def __init__(self, chargebeeClient: ChargebeeClient) -> None:
        self.http_client = chargebeeClient.get_client()
        self._chargebee_client = chargebeeClient

    async def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> ChargebeeResponse:
        url = self._chargebee_client.get_base_url() + path
        if params:
            url += "?" + urlencode(params)
        try:
            request = HTTPRequest(url=url, method="GET", headers={"Content-Type": "application/json"})
            response: HTTPResponse = await self.http_client.execute(request)
            response_text = response.text()
            if response.status >= HTTP_ERROR_THRESHOLD:
                logger.debug(f"Chargebee GET {path}: status={response.status} body={response_text[:200] if response_text else 'Empty'}")
            return ChargebeeResponse(
                success=response.status < HTTP_ERROR_THRESHOLD,
                data=response.json() if response_text else None,
                message=None if response.status < HTTP_ERROR_THRESHOLD else f"Failed with status {response.status}",
            )
        except Exception as e:
            logger.debug(f"Error calling Chargebee {path}: {e}")
            return ChargebeeResponse(success=False, error=str(e))

    async def list_subscriptions(
        self, limit: int = 100, offset: Optional[str] = None
    ) -> ChargebeeResponse:
        """GET /subscriptions — includes plan, mrr, current_term_end (renewal date)."""
        params: dict[str, Any] = {"limit": limit}
        if offset:
            params["offset"] = offset
        return await self._get("/subscriptions", params)

    async def list_customers(
        self, limit: int = 100, offset: Optional[str] = None
    ) -> ChargebeeResponse:
        """GET /customers"""
        params: dict[str, Any] = {"limit": limit}
        if offset:
            params["offset"] = offset
        return await self._get("/customers", params)

    async def get_customer(self, customer_id: str) -> ChargebeeResponse:
        """GET /customers/{customer_id}"""
        return await self._get(f"/customers/{customer_id}")


def parse_subscription_list_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Chargebee's ``{"list": [{"subscription": {...}, "customer": {...}}]}`` shape."""
    if not data or "list" not in data:
        return []
    return data["list"]
