"""Text embeddings for semantic topic matching.

Uses the org's configured embedding model — the one PipesHub already uses for
search — so no extra provider or sub-processor is introduced. When nothing is
configured, there is deliberately no fallback to the local default model: the
worker stays light and matching degrades to the lexical tier.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from app.config.constants.service import config_node_constants
from app.utils.aimodels import embedding_config_hash, get_embedding_model

if TYPE_CHECKING:
    from logging import Logger

    from langchain_core.embeddings import Embeddings

    from app.config.configuration_service import ConfigurationService


class ITextEmbedder(ABC):
    @abstractmethod
    async def model_id(self) -> Optional[str]:
        """Stable id of the current model; None when embeddings are unavailable."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ConfiguredTextEmbedder(ITextEmbedder):
    def __init__(self, logger: Logger, config_service: ConfigurationService) -> None:
        self.logger = logger
        self.config_service = config_service
        self._model: Optional[Embeddings] = None
        self._model_id: Optional[str] = None
        self._hash: Optional[str] = None
        self._lock = asyncio.Lock()

    async def _resolve(self) -> tuple[Optional[Embeddings], Optional[str]]:
        ai_models = await self.config_service.get_config(config_node_constants.AI_MODELS.value)
        configs = (ai_models or {}).get("embedding") or []
        if not configs:
            return None, None
        config_hash = embedding_config_hash(configs)
        if self._model is not None and self._hash == config_hash:
            return self._model, self._model_id
        async with self._lock:
            if self._model is not None and self._hash == config_hash:
                return self._model, self._model_id
            selected = next((c for c in configs if c.get("isDefault")), configs[0])
            try:
                self._model = await asyncio.to_thread(get_embedding_model, selected["provider"], selected)
            except Exception:
                self.logger.warning("Embedding model unavailable; topic matching stays lexical", exc_info=True)
                return None, None
            configuration = selected.get("configuration") or {}
            self._model_id = f"{selected['provider']}/{configuration.get('model') or 'default'}"[:191]
            self._hash = config_hash
            return self._model, self._model_id

    async def model_id(self) -> Optional[str]:
        _, model_id = await self._resolve()
        return model_id

    async def embed(self, texts: list[str]) -> list[list[float]]:
        model, _ = await self._resolve()
        if model is None or not texts:
            return []
        if hasattr(model, "aembed_documents"):
            return await model.aembed_documents(texts)
        return await asyncio.to_thread(model.embed_documents, texts)
