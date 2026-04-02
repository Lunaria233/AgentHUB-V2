from __future__ import annotations

import logging
import time
from typing import Any

from neo4j import GraphDatabase

from app.platform.memory.base import MemoryEntity, MemoryRelation


logger = logging.getLogger(__name__)


class Neo4jGraphMemoryStore:
    def __init__(self, *, uri: str, username: str, password: str) -> None:
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None
        self.active_uri = ""
        self._cooldown_until = 0.0
        self._connect()

    @property
    def enabled(self) -> bool:
        return self.driver is not None

    def upsert_entities_and_relations(
        self,
        *,
        app_id: str,
        session_id: str | None,
        user_id: str | None,
        entities: list[MemoryEntity],
        relations: list[MemoryRelation],
        memory_id: str = "",
    ) -> None:
        if not self._ensure_connected():
            return
        scope = {"app_id": app_id, "session_id": session_id or "", "user_id": user_id or "", "memory_id": memory_id}
        try:
            with self.driver.session() as session:
                for entity in entities:
                    session.run(
                        """
                        MERGE (n:MemoryEntity {entity_key: $entity_key})
                        SET n.name = $name,
                            n.entity_type = $entity_type,
                            n.app_id = $app_id,
                            n.session_id = $session_id,
                            n.user_id = $user_id,
                            n.confidence = $confidence
                        """,
                        entity_key=self._entity_key(entity.entity_name, entity.entity_type),
                        name=entity.entity_name,
                        entity_type=entity.entity_type,
                        confidence=entity.confidence,
                        **scope,
                    ).consume()
                for relation in relations:
                    session.run(
                        """
                        MERGE (s:MemoryEntity {entity_key: $source_key})
                        SET s.name = $source, s.app_id = $app_id, s.session_id = $session_id, s.user_id = $user_id
                        MERGE (t:MemoryEntity {entity_key: $target_key})
                        SET t.name = $target, t.app_id = $app_id, t.session_id = $session_id, t.user_id = $user_id
                        MERGE (s)-[r:MEMORY_REL {relation: $relation, app_id: $app_id, session_id: $session_id, user_id: $user_id, memory_id: $memory_id}]->(t)
                        SET r.confidence = $confidence
                        """,
                        source_key=self._entity_key(relation.source, "entity"),
                        target_key=self._entity_key(relation.target, "entity"),
                        source=relation.source,
                        target=relation.target,
                        relation=relation.relation,
                        confidence=relation.confidence,
                        **scope,
                    ).consume()
        except Exception as exc:
            self._mark_failed(exc)

    def search(
        self,
        *,
        query: str,
        app_id: str,
        session_id: str | None,
        user_id: str | None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        if not self._ensure_connected():
            return []
        lowered_query = query.lower()
        try:
            with self.driver.session() as session:
                records = session.run(
                    """
                    MATCH (s:MemoryEntity)-[r:MEMORY_REL]->(t:MemoryEntity)
                    WHERE r.app_id = $app_id
                      AND (r.session_id = $session_id OR r.session_id = '')
                      AND (r.user_id = $user_id OR r.user_id = '')
                      AND (
                        toLower(s.name) CONTAINS $search_text OR
                        toLower(t.name) CONTAINS $search_text OR
                        toLower(r.relation) CONTAINS $search_text
                      )
                    RETURN s.name AS source, r.relation AS relation, t.name AS target, r.memory_id AS memory_id, r.confidence AS confidence
                    LIMIT $limit
                    """,
                    app_id=app_id,
                    session_id=session_id or "",
                    user_id=user_id or "",
                    search_text=lowered_query,
                    limit=limit,
                )
                return [
                    {
                        "memory_type": "graph",
                        "source_kind": "neo4j_graph_relation",
                        "content": f"{record['source']} {record['relation']} {record['target']}",
                        "memory_id": record["memory_id"],
                        "score": float(record["confidence"] or 0.0) * 0.25,
                    }
                    for record in records
                ]
        except Exception as exc:
            self._mark_failed(exc)
            return []

    def _connect(self) -> None:
        for candidate in self._candidate_uris(self.uri):
            try:
                driver = GraphDatabase.driver(
                    candidate,
                    auth=(self.username, self.password),
                    connection_timeout=3.0,
                    connection_acquisition_timeout=3.0,
                    liveness_check_timeout=3.0,
                    max_connection_lifetime=300.0,
                    keep_alive=True,
                )
                with driver.session() as session:
                    record = session.run("RETURN 1 AS ok").single()
                    if record and record["ok"] == 1:
                        self.driver = driver
                        self.active_uri = candidate
                        self._cooldown_until = 0.0
                        return
            except Exception:
                continue

    def _ensure_connected(self) -> bool:
        if self.driver is not None:
            return True
        if time.monotonic() < self._cooldown_until:
            return False
        self._connect()
        return self.driver is not None

    def _mark_failed(self, exc: Exception) -> None:
        logger.warning("Neo4j graph backend disabled temporarily due to connection failure: %s", exc)
        self._close_driver()
        self._cooldown_until = time.monotonic() + 30.0

    def _close_driver(self) -> None:
        if self.driver is not None:
            try:
                self.driver.close()
            except Exception:
                pass
        self.driver = None
        self.active_uri = ""

    @staticmethod
    def _candidate_uris(uri: str) -> list[str]:
        candidates = [uri]
        if uri.startswith("neo4j+s://"):
            suffix = uri[len("neo4j+s://") :]
            candidates = [f"neo4j+ssc://{suffix}", f"bolt+ssc://{suffix}", uri, f"bolt+s://{suffix}"]
        elif uri.startswith("neo4j://"):
            suffix = uri[len("neo4j://") :]
            candidates.extend([f"bolt://{suffix}"])
        return candidates

    @staticmethod
    def _entity_key(entity_name: str, entity_type: str) -> str:
        normalized = "".join(char.lower() if char.isalnum() else "-" for char in entity_name).strip("-")
        return f"{entity_type}:{normalized}"[:160]
