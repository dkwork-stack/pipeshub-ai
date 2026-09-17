"""DI container for the Customer Feature Intelligence portal service.

Read-only service: it owns an ``IIntelligenceQueryRepository`` (MySQL today,
selected by ``IntelligenceStoreFactory``) and the query services the portal
routers depend on. It has no graph/vector/broker connections — the write side
lives on the indexing service.
"""
from __future__ import annotations

from dependency_injector import containers, providers  # type: ignore
from dotenv import load_dotenv  # type: ignore

from app.config.configuration_service import ConfigurationService
from app.config.providers.encrypted_store import EncryptedKeyValueStore
from app.containers.container import BaseAppContainer
from app.modules.customer_intelligence.queries.services import (
    CustomerQueryService,
    FeatureGapQueryService,
    OverviewQueryService,
)
from app.services.intelligence_store.intelligence_store_factory import (
    IntelligenceStoreFactory,
)
from app.utils.logger import create_logger

load_dotenv(override=True)


class IntelligenceAppContainer(BaseAppContainer):
    logger = providers.Singleton(create_logger, "intelligence_service")
    key_value_store = providers.Singleton(EncryptedKeyValueStore, logger=logger)
    config_service = providers.Singleton(
        ConfigurationService, logger=logger, key_value_store=key_value_store
    )

    intelligence_query_repository = providers.Resource(
        IntelligenceStoreFactory.create_query_repository,
        logger=logger,
    )

    # Singletons over an async Resource: dependency-injector switches these to
    # async mode automatically, so routers ``await container.<service>()``.
    overview_query_service = providers.Singleton(
        OverviewQueryService, repository=intelligence_query_repository
    )
    feature_gap_query_service = providers.Singleton(
        FeatureGapQueryService, repository=intelligence_query_repository
    )
    customer_query_service = providers.Singleton(
        CustomerQueryService, repository=intelligence_query_repository
    )

    wiring_config = containers.WiringConfiguration(modules=["app.intelligence_main"])


async def initialize_container(container: IntelligenceAppContainer) -> bool:
    logger = container.logger()
    logger.info("🚀 Initializing Intelligence Portal Service resources")
    # A failed Resource init is not cached, so routes re-attempt the
    # connection on demand and the service self-heals once MySQL is back
    # instead of crash-looping under the process monitor.
    try:
        await container.intelligence_query_repository()
        logger.info("✅ Intelligence query repository connected")
    except Exception as e:
        logger.warning(f"⚠️ Intelligence store unavailable at startup, will retry per request: {e}")
    return True
