"""IntelligenceStoreFactory: creates the configured IIntelligenceStore.

Mirrors GraphDBProviderFactory / VectorDBProviderFactory (see AGENTS.md):
encapsulates backend selection so callers only ever see IIntelligenceStore.

Environment variables:
    INTELLIGENCE_STORE_TYPE: backend type ("mysql", default)
    INTELLIGENCE_MYSQL_HOST / _PORT / _USER / _PASSWORD / _DATABASE
    INTELLIGENCE_MYSQL_DSN: full SQLAlchemy DSN, takes precedence if set
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from logging import Logger

    from app.services.intelligence_store.interface.intelligence_query_repository import (
        IIntelligenceQueryRepository,
    )
    from app.services.intelligence_store.interface.intelligence_store import (
        IIntelligenceStore,
    )
    from app.services.intelligence_store.mysql.mysql_intelligence_store import (
        MySQLIntelligenceStore,
    )


class IntelligenceStoreFactory:
    @staticmethod
    async def create_store(logger: Logger) -> IIntelligenceStore:
        store_type = os.getenv("INTELLIGENCE_STORE_TYPE", "mysql").lower()

        if store_type == "mysql":
            return await IntelligenceStoreFactory._create_mysql_store(logger)

        raise ValueError(
            f"Unsupported intelligence store type: {store_type}. "
            "Set INTELLIGENCE_STORE_TYPE to 'mysql'."
        )

    @staticmethod
    async def create_query_repository(logger: Logger) -> IIntelligenceQueryRepository:
        """Read-only repository for the intelligence portal service."""
        store_type = os.getenv("INTELLIGENCE_STORE_TYPE", "mysql").lower()

        if store_type == "mysql":
            from app.services.intelligence_store.mysql.mysql_intelligence_query_repository import (
                MySQLIntelligenceQueryRepository,
            )

            store = await IntelligenceStoreFactory._create_mysql_store(logger)
            return MySQLIntelligenceQueryRepository(logger=logger, engine=store.engine)

        raise ValueError(
            f"Unsupported intelligence store type: {store_type}. "
            "Set INTELLIGENCE_STORE_TYPE to 'mysql'."
        )

    @staticmethod
    def _mysql_dsn() -> str:
        dsn = os.getenv("INTELLIGENCE_MYSQL_DSN")
        if not dsn:
            host = os.getenv("INTELLIGENCE_MYSQL_HOST", "localhost")
            port = os.getenv("INTELLIGENCE_MYSQL_PORT", "3306")
            user = os.getenv("INTELLIGENCE_MYSQL_USER", "pipeshub")
            password = quote_plus(os.getenv("INTELLIGENCE_MYSQL_PASSWORD", ""))
            database = os.getenv("INTELLIGENCE_MYSQL_DATABASE", "pipeshub_intelligence")
            dsn = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"
        return dsn

    @staticmethod
    async def _create_mysql_store(logger: Logger) -> "MySQLIntelligenceStore":
        from app.services.intelligence_store.mysql.mysql_intelligence_store import (
            MySQLIntelligenceStore,
        )

        store = MySQLIntelligenceStore(logger=logger, dsn=IntelligenceStoreFactory._mysql_dsn())
        connected = await store.connect()
        if not connected:
            raise ConnectionError("Failed to connect MySQLIntelligenceStore")
        return store
