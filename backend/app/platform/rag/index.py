from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.platform.rag.document import Document, DocumentChunk


class QdrantRAGIndex:
    FILTER_FIELDS = [
        "kb_id",
        "visibility",
        "tenant_id",
        "user_id",
        "app_id",
        "agent_id",
        "session_id",
        "owner_id",
        "source_type",
        "is_temporary",
        "document_id",
    ]

    def __init__(self, *, base_url: str, api_key: str, collection: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.collection = collection
        self._vector_size = 0
        self._payload_indexes_ready = False

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.collection)

    def ensure_collection(self, vector_size: int) -> None:
        if not self.enabled or vector_size <= 0:
            return
        if self._vector_size == vector_size:
            return
        existing_size = self._get_existing_vector_size(self.collection)
        if existing_size and existing_size != vector_size:
            self.collection = f"{self.collection}_{vector_size}"
            existing_size = self._get_existing_vector_size(self.collection)
        if existing_size == vector_size:
            self._vector_size = vector_size
            self._ensure_payload_indexes()
            return
        response = self._request(
            "PUT",
            f"{self.base_url}/collections/{self.collection}",
            json={"vectors": {"size": vector_size, "distance": "Cosine"}},
        )
        if response.status_code not in {200, 201, 409}:
            response.raise_for_status()
        self._vector_size = vector_size
        self._ensure_payload_indexes()

    def upsert_chunks(self, *, document: Document, chunks: list[DocumentChunk], vectors: dict[str, list[float]]) -> None:
        if not self.enabled or not chunks:
            return
        first_vector = next((vector for vector in vectors.values() if vector), [])
        if not first_vector:
            return
        self.ensure_collection(len(first_vector))
        points = []
        for chunk in chunks:
            vector = vectors.get(chunk.chunk_id)
            if not vector:
                continue
            points.append(
                {
                    "id": str(uuid5(NAMESPACE_URL, chunk.chunk_id)),
                    "vector": vector,
                    "payload": {
                        "chunk_id": chunk.chunk_id,
                        "document_id": document.document_id,
                        "kb_id": document.kb_id,
                        "visibility": document.visibility,
                        "tenant_id": document.tenant_id,
                        "user_id": document.user_id,
                        "app_id": document.app_id,
                        "agent_id": document.agent_id,
                        "session_id": document.session_id,
                        "owner_id": document.owner_id,
                        "source_type": document.source_type,
                        "is_temporary": document.is_temporary,
                    },
                }
            )
        if not points:
            return
        response = self._request(
            "PUT",
            f"{self.base_url}/collections/{self.collection}/points",
            json={"points": points},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Qdrant RAG upsert failed ({response.status_code}): {response.text}")

    def search(
        self,
        *,
        query_vector: list[float],
        limit: int,
        should_filters: list[dict[str, Any]],
        must_filters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.enabled or not query_vector:
            return []
        self.ensure_collection(len(query_vector))
        filter_payload: dict[str, Any] = {}
        if must_filters:
            filter_payload["must"] = must_filters
        if should_filters:
            filter_payload["should"] = should_filters
        response = self._request(
            "POST",
            f"{self.base_url}/collections/{self.collection}/points/search",
            json={
                "vector": query_vector,
                "limit": limit,
                "with_payload": True,
                "filter": filter_payload or None,
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Qdrant RAG search failed ({response.status_code}): {response.text}")
        items = response.json().get("result", [])
        return [
            {
                "chunk_id": item.get("payload", {}).get("chunk_id"),
                "document_id": item.get("payload", {}).get("document_id"),
                "score": float(item.get("score", 0.0)),
            }
            for item in items
            if item.get("payload", {}).get("chunk_id")
        ]

    def delete_document(self, document_id: str) -> None:
        if not self.enabled:
            return
        response = self._request(
            "POST",
            f"{self.base_url}/collections/{self.collection}/points/delete",
            json={"filter": {"must": [{"key": "document_id", "match": {"value": document_id}}]}},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Qdrant RAG delete failed ({response.status_code}): {response.text}")

    def collection_info(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "collection": self.collection, "base_url": self.base_url}
        response = httpx.get(f"{self.base_url}/collections/{self.collection}", headers=self._headers(), timeout=30)
        if response.status_code == 404:
            return {"enabled": True, "collection": self.collection, "base_url": self.base_url, "exists": False}
        response.raise_for_status()
        result = response.json().get("result", {})
        vectors = ((result.get("config") or {}).get("params") or {}).get("vectors") or {}
        return {
            "enabled": True,
            "collection": self.collection,
            "base_url": self.base_url,
            "exists": True,
            "vector_size": int(vectors.get("size", 0) or 0) if isinstance(vectors, dict) else 0,
            "points_count": int(result.get("points_count", 0) or 0),
            "status": result.get("status", ""),
        }

    def drop_collection(self, collection_name: str | None = None) -> None:
        if not self.enabled:
            return
        target = collection_name or self.collection
        response = httpx.delete(f"{self.base_url}/collections/{target}", headers=self._headers(), timeout=30)
        if response.status_code not in {200, 202, 404}:
            raise RuntimeError(f"Qdrant RAG drop collection failed ({response.status_code}): {response.text}")

    def _ensure_payload_indexes(self) -> None:
        if self._payload_indexes_ready or not self.enabled:
            return
        for field in self.FILTER_FIELDS:
            response = self._request(
                "PUT",
                f"{self.base_url}/collections/{self.collection}/index",
                json={"field_name": field, "field_schema": "keyword" if field != "is_temporary" else "bool"},
            )
            if response.status_code not in {200, 201, 409}:
                response.raise_for_status()
        self._payload_indexes_ready = True

    def _get_existing_vector_size(self, collection_name: str) -> int:
        response = self._request("GET", f"{self.base_url}/collections/{collection_name}")
        if response.status_code == 404:
            return 0
        response.raise_for_status()
        result = response.json().get("result", {})
        vectors = ((result.get("config") or {}).get("params") or {}).get("vectors") or {}
        if isinstance(vectors, dict):
            return int(vectors.get("size", 0) or 0)
        return 0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        last_error: Exception | None = None
        for verify in (True, False):
            try:
                return httpx.request(
                    method,
                    url,
                    headers=self._headers(),
                    timeout=30,
                    verify=verify,
                    **kwargs,
                )
            except httpx.TransportError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("Qdrant request failed without response")
