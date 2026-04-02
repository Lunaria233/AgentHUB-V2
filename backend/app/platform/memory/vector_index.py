from __future__ import annotations

from typing import Any

import httpx


class QdrantMemoryIndex:
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
        response = httpx.put(
            f"{self.base_url}/collections/{self.collection}",
            headers=self._headers(),
            json={
                "vectors": {
                    "size": vector_size,
                    "distance": "Cosine",
                }
            },
            timeout=30,
        )
        if response.status_code not in {200, 201, 409}:
            response.raise_for_status()
        self._vector_size = vector_size
        self._ensure_payload_indexes()

    def upsert_memory(
        self,
        *,
        memory_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        if not self.enabled or not vector:
            return
        self.ensure_collection(len(vector))
        response = httpx.put(
            f"{self.base_url}/collections/{self.collection}/points",
            headers=self._headers(),
            json={
                "points": [
                    {
                        "id": memory_id,
                        "vector": vector,
                        "payload": payload,
                    }
                ]
            },
            timeout=30,
        )
        response.raise_for_status()

    def search(
        self,
        *,
        query_vector: list[float],
        limit: int,
        app_id: str | None,
        session_id: str | None,
        user_id: str | None,
        memory_types: list[str] | None,
    ) -> list[dict[str, Any]]:
        if not self.enabled or not query_vector:
            return []
        self.ensure_collection(len(query_vector))
        filter_payload: dict[str, Any] = {"must": []}
        if app_id:
            filter_payload["must"].append({"key": "app_id", "match": {"value": app_id}})
        if session_id:
            filter_payload["must"].append({"key": "session_id", "match": {"value": session_id}})
        if user_id:
            filter_payload["must"].append({"key": "user_id", "match": {"value": user_id}})
        if memory_types:
            filter_payload["must"].append({"key": "memory_type", "match": {"any": memory_types}})
        if not filter_payload["must"]:
            filter_payload = {}
        response = httpx.post(
            f"{self.base_url}/collections/{self.collection}/points/search",
            headers=self._headers(),
            json={
                "vector": query_vector,
                "limit": limit,
                "with_payload": True,
                "filter": filter_payload or None,
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json().get("result", [])
        hits: list[dict[str, Any]] = []
        for item in result:
            payload = dict(item.get("payload", {}))
            payload["score"] = float(item.get("score", 0.0))
            payload["memory_id"] = payload.get("memory_id") or str(item.get("id", ""))
            hits.append(payload)
        return hits

    def _ensure_payload_indexes(self) -> None:
        if self._payload_indexes_ready or not self.enabled:
            return
        for field in ["app_id", "session_id", "user_id", "memory_type"]:
            response = httpx.put(
                f"{self.base_url}/collections/{self.collection}/index",
                headers=self._headers(),
                json={"field_name": field, "field_schema": "keyword"},
                timeout=30,
            )
            if response.status_code not in {200, 201, 409}:
                response.raise_for_status()
        self._payload_indexes_ready = True

    def _get_existing_vector_size(self, collection_name: str) -> int:
        response = httpx.get(
            f"{self.base_url}/collections/{collection_name}",
            headers=self._headers(),
            timeout=30,
        )
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
