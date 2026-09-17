from dependency_injector import containers, providers  # type: ignore
from dotenv import load_dotenv  # type: ignore

from app.config.configuration_service import ConfigurationService
from app.config.providers.encrypted_store import EncryptedKeyValueStore
from app.connectors.services.kafka_service import KafkaService
from app.containers.container import BaseAppContainer
from app.containers.utils.utils import ContainerUtils
from app.health.health import Health
from app.utils.logger import create_logger

load_dotenv(override=True)


class IndexingAppContainer(BaseAppContainer):
    """Dependency injection container for the indexing application."""

    # Override logger with service-specific name
    logger = providers.Singleton(create_logger, "indexing_service")
    container_utils = ContainerUtils()
    # Override config_service to use the service-specific logger
    key_value_store = providers.Singleton(EncryptedKeyValueStore, logger=logger)
    config_service = providers.Singleton(ConfigurationService, logger=logger, key_value_store=key_value_store)

    # Override arango_client to use the service-specific config_service
    arango_client = providers.Resource(
        BaseAppContainer._create_arango_client, config_service=config_service
    )
    kafka_service = providers.Singleton(
        KafkaService, logger=logger, config_service=config_service
    )

    # Graph Database Provider via Factory (HTTP mode - fully async)
    graph_provider = providers.Resource(
        container_utils.create_graph_provider,
        logger=logger,
        config_service=config_service,
    )

    vector_db_service = providers.Resource(
        container_utils.get_vector_db_service,
        config_service=config_service,
    )

    collection_registry = providers.Resource(
        container_utils.create_collection_registry,
        logger=logger,
        config_service=config_service,
        vector_db_service=vector_db_service,
    )

    indexing_pipeline = providers.Resource(
        container_utils.create_indexing_pipeline,
        logger=logger,
        config_service=config_service,
        graph_provider=graph_provider,
        vector_db_service=vector_db_service,
        collection_registry=collection_registry,
    )

    document_extractor = providers.Resource(
        container_utils.create_document_extractor,
        logger=logger,
        graph_provider=graph_provider,
        config_service=config_service,
    )

    blob_storage = providers.Resource(
        container_utils.create_blob_storage,
        logger=logger,
        config_service=config_service,
        graph_provider=graph_provider,
    )

    graphdb = providers.Resource(
        container_utils.create_graphdb,
        graph_provider=graph_provider,
        logger=logger,
    )

    vector_store = providers.Resource(
        container_utils.create_vector_store,
        logger=logger,
        graph_provider=graph_provider,
        config_service=config_service,
        vector_db_service=vector_db_service,
        collection_registry=collection_registry,
    )

    # HTTP clients for the standalone Parsing and Extraction services.
    # parsing_client is only used when USE_PARSING_SERVICE=true; extraction_client
    # is also the LLM hop for Customer Feature Intelligence, so it is always wired.
    parsing_client = providers.Resource(
        container_utils.create_parsing_client,
        config_service=config_service,
    )

    extraction_client = providers.Resource(
        container_utils.create_extraction_client,
    )

    # Customer Feature Intelligence: MySQL-backed store + ingestion service.
    # Additive to the graph/vector stores above — see AGENTS.md pluggable-store table.
    intelligence_store = providers.Resource(
        container_utils.create_intelligence_store,
        logger=logger,
    )

    customer_intelligence_ingestion_service = providers.Resource(
        container_utils.create_customer_intelligence_ingestion_service,
        logger=logger,
        intelligence_store=intelligence_store,
        extraction_client=extraction_client,
    )

    sink_orchestrator = providers.Resource(
        container_utils.create_sink_orchestrator,
        logger=logger,
        graphdb=graphdb,
        blob_storage=blob_storage,
        vector_store=vector_store,
        graph_provider=graph_provider,
        config_service=config_service,
        # The provider, not the value: the factory resolves it lazily so a MySQL
        # outage degrades to "no intelligence" instead of failing indexing startup.
        customer_intelligence_provider=customer_intelligence_ingestion_service.provider,
    )

    # Parsers
    parsers = providers.Resource(
        container_utils.create_parsers,
        logger=logger,
        config_service=config_service,
    )

    # Processor - depends on indexing_pipeline and graph_provider
    processor = providers.Resource(
        container_utils.create_processor,
        logger=logger,
        config_service=config_service,
        indexing_pipeline=indexing_pipeline,
        graph_provider=graph_provider,
        parsers=parsers,
        document_extractor=document_extractor,
        sink_orchestrator=sink_orchestrator,
    )

    event_processor = providers.Resource(
        container_utils.create_event_processor,
        logger=logger,
        processor=processor,
        graph_provider=graph_provider,
        config_service=config_service,
        collection_registry=collection_registry,
        parsing_client=parsing_client,
        extraction_client=extraction_client,
        sink_orchestrator=sink_orchestrator,
    )

    # Indexing-specific wiring configuration
    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.indexing_main"
        ]
    )

async def initialize_container(container: IndexingAppContainer) -> bool:
    """Initialize container resources"""
    logger = container.logger()
    logger.info("🚀 Initializing application resources")

    try:
        # Ensure connector service is healthy before starting indexing service
        logger.info("Checking Connector service health before startup")
        await Health.health_check_connector_service(container)

        # Ensure Graph Database Provider is initialized (connection is handled in the resource factory)
        logger.info("Ensuring Graph Database Provider is initialized")
        graph_provider = await container.graph_provider()
        if not graph_provider:
            raise Exception("Failed to initialize Graph Database Provider")

        # Store the resolved graph_provider in the container to avoid coroutine reuse
        container._graph_provider = graph_provider
        logger.info("✅ Graph Database Provider initialized and connected")

        # Customer Feature Intelligence store — additive to the existing graph/vector
        # pipeline (see AGENTS.md pluggable-store table), so a MySQL outage here must
        # not block core document indexing: log and continue, the /api/v1/intelligence/*
        # routes simply 500 until it recovers.
        logger.info("Ensuring Customer Feature Intelligence store is initialized")
        try:
            intelligence_store = await container.intelligence_store()
            if not intelligence_store:
                raise Exception("intelligence_store() returned falsy")
            logger.info("✅ Customer Feature Intelligence store initialized and connected")
        except Exception as e:
            logger.warning(
                f"⚠️ Customer Feature Intelligence store unavailable, continuing without it: {e}"
            )

        await Health.system_health_check(container)
        return True

    except Exception as e:
        logger.error(f"❌ Failed to initialize resources: {str(e)}")
        raise
