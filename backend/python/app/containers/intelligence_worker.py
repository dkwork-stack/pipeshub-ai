"""DI container for the Customer Feature Intelligence worker (``app.intelligence_worker_main``).

Deliberately narrow: config, the intelligence store, the extraction-service
client and the analysis service. No graph, vector or blob connections — the
SignalEnvelopes it consumes are self-contained.
"""
from __future__ import annotations

from dependency_injector import containers, providers  # type: ignore
from dotenv import load_dotenv  # type: ignore

from app.config.configuration_service import ConfigurationService
from app.config.providers.encrypted_store import EncryptedKeyValueStore
from app.containers.container import BaseAppContainer
from app.modules.customer_intelligence.factory import create_analysis_service
from app.services.extraction.client import ExtractionClient
from app.services.intelligence_store.intelligence_store_factory import (
    IntelligenceStoreFactory,
)
from app.utils.logger import create_logger

load_dotenv(override=True)


class IntelligenceWorkerContainer(BaseAppContainer):
    logger = providers.Singleton(create_logger, "intelligence_worker")
    key_value_store = providers.Singleton(EncryptedKeyValueStore, logger=logger)
    config_service = providers.Singleton(
        ConfigurationService, logger=logger, key_value_store=key_value_store
    )
    intelligence_store = providers.Resource(IntelligenceStoreFactory.create_store, logger=logger)
    extraction_client = providers.Singleton(ExtractionClient, config_service=config_service)
    analysis_service = providers.Singleton(
        create_analysis_service,
        logger=logger,
        store=intelligence_store,
        extraction_client=extraction_client,
        config_service=config_service,
    )

    wiring_config = containers.WiringConfiguration(modules=["app.intelligence_worker_main"])
