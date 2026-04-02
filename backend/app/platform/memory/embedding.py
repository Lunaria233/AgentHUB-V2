from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

import httpx

from app.config import Settings


class BaseMemoryEmbedder(ABC):
    @abstractmethod
    def encode(self, text: str) -> list[float]:
        raise NotImplementedError


class LocalHashEmbedder(BaseMemoryEmbedder):
    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = max(32, dimensions)

    def encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[slot] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        cleaned = "".join(char.lower() if char.isalnum() else " " for char in text)
        words = [token for token in cleaned.split() if token]
        if len(words) <= 1:
            return words
        phrases = [f"{words[index]}_{words[index + 1]}" for index in range(len(words) - 1)]
        return words + phrases


class OpenAICompatMemoryEmbedder(BaseMemoryEmbedder):
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def encode(self, text: str) -> list[float]:
        if not self.api_key or not self.base_url or not self.model:
            raise RuntimeError("Embedding provider is not configured")
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": text},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or []
        if not data:
            raise RuntimeError(f"Unexpected embedding response: {payload}")
        embedding = data[0].get("embedding") or []
        return [float(value) for value in embedding]


def build_memory_embedder(settings: Settings) -> BaseMemoryEmbedder:
    if settings.memory.embedding_mode in {"provider", "auto"} and settings.embed_base_url and settings.embed_api_key and settings.embed_model:
        return OpenAICompatMemoryEmbedder(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
            model=settings.embed_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return LocalHashEmbedder(dimensions=settings.memory.local_embedding_dimensions)
