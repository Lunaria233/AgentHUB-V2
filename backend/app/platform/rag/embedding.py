from __future__ import annotations

from app.config import Settings
from app.platform.memory.embedding import BaseMemoryEmbedder, LocalHashEmbedder, OpenAICompatMemoryEmbedder


BaseRAGEmbedder = BaseMemoryEmbedder


def build_rag_embedder(settings: Settings) -> BaseRAGEmbedder:
    if settings.embed_base_url and settings.embed_api_key and settings.embed_model:
        return OpenAICompatMemoryEmbedder(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
            model=settings.embed_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return LocalHashEmbedder(dimensions=settings.memory_local_embedding_dimensions)
