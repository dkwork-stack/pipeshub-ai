"""Chargebee REST client.

Chargebee uses HTTP Basic auth: API key as username, empty password — same
scheme as FreshDesk (see ``app/sources/client/freshdesk/freshdesk.py``),
mirrored here rather than reinvented.
"""
import base64
from logging import Logger
from typing import Any, Optional

from pydantic import BaseModel, field_validator

from app.config.configuration_service import ConfigurationService
from app.sources.client.http.http_client import HTTPClient
from app.sources.client.iclient import IClient


class ChargebeeConfigurationError(Exception):
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ChargebeeResponse(BaseModel):
    """Standardized Chargebee API response wrapper"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ChargebeeRESTClientViaApiKey(HTTPClient):
    """Chargebee REST client via API key.

    Args:
        site: The Chargebee site name (e.g. 'mycompany' for mycompany.chargebee.com)
        api_key: The API key to use for authentication
    """

    def __init__(self, site: str, api_key: str) -> None:
        credentials = f"{api_key}:"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        super().__init__(encoded_credentials, "Basic")
        self.site = site
        self.base_url = f"https://{site}.chargebee.com/api/v2"

    def get_base_url(self) -> str:
        return self.base_url

    def get_site(self) -> str:
        return self.site


class ChargebeeApiKeyConfig(BaseModel):
    site: str
    api_key: str

    @field_validator("site")
    @classmethod
    def validate_site(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("site cannot be empty or None")
        if v.startswith(("http://", "https://")):
            raise ValueError("site should not include protocol (http:// or https://)")
        return v

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("api_key cannot be empty or None")
        return v

    def create_client(self) -> ChargebeeRESTClientViaApiKey:
        return ChargebeeRESTClientViaApiKey(self.site, self.api_key)


class ChargebeeClient(IClient):
    """Builder class for Chargebee clients"""

    def __init__(self, client: ChargebeeRESTClientViaApiKey) -> None:
        self.client = client

    def get_client(self) -> ChargebeeRESTClientViaApiKey:
        return self.client

    def get_base_url(self) -> str:
        return self.client.get_base_url()

    @classmethod
    def build_with_api_key(cls, site: str, api_key: str) -> "ChargebeeClient":
        config = ChargebeeApiKeyConfig(site=site, api_key=api_key)
        return cls(config.create_client())

    @classmethod
    async def build_from_services(
        cls,
        logger: Logger,
        config_service: ConfigurationService,
        connector_instance_id: Optional[str] = None,
    ) -> "ChargebeeClient":
        """Build from the connector config service (etcd), same pattern as FreshDeskClient.

        Follow-up work (see AGENTS.md connector registry): once Chargebee is
        registered as a full connector, credentials will live under
        ``/services/connectors/{id}/config`` like every other connector. Until
        then, ``build_with_api_key`` (env-var driven, see
        ``scripts/customer_intelligence/chargebee_sync.py``) is the supported path.
        """
        config = await config_service.get_config(f"/services/connectors/{connector_instance_id}/config")
        if not config:
            raise ValueError(f"Failed to get Chargebee connector configuration for instance {connector_instance_id}")
        auth_config = config.get("auth", {})
        site = auth_config.get("site", "")
        api_key = auth_config.get("apiKey", "")
        if not api_key or not site:
            raise ValueError("Chargebee site and api_key required")
        return cls.build_with_api_key(site, api_key)
