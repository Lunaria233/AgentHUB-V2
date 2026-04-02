from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.platform.memory.base import MemoryCandidate, MemoryEntity, MemoryRelation
from app.platform.models.base import BaseModelClient, ModelRequest


PREFERENCE_PATTERNS = [
    re.compile(r"\b(?:i|we)\s+(?:prefer|like|love|enjoy)\s+(?P<value>[^.!\n]+)", re.IGNORECASE),
    re.compile(r"\bmy favorite\s+(?P<key>[^.!?\n]+?)\s+is\s+(?P<value>[^.!\n]+)", re.IGNORECASE),
]
CONSTRAINT_PATTERNS = [
    re.compile(r"\b(?:i|we)\s+(?:need|must|have to|cannot|can't|do not want|don't want|should avoid)\s+(?P<value>[^.!\n]+)", re.IGNORECASE),
]
IDENTITY_PATTERNS = {
    "user:identity:name": re.compile(r"\bmy name is\s+(?P<value>[^.!\n]+)", re.IGNORECASE),
    "user:identity:role": re.compile(r"\bi am\s+(?:an?|the)\s+(?P<value>[^.!\n]+)", re.IGNORECASE),
    "user:identity:location": re.compile(r"\bi live in\s+(?P<value>[^.!\n]+)", re.IGNORECASE),
    "user:identity:project": re.compile(r"\bi(?:'m| am)\s+working on\s+(?P<value>[^.!\n]+)", re.IGNORECASE),
}
RELATION_PATTERNS = [
    (re.compile(r"\b(?P<source>[\w\- ]+?)\s+prefers\s+(?P<target>[\w\- ]+)", re.IGNORECASE), "prefers"),
    (re.compile(r"\b(?P<source>[\w\- ]+?)\s+uses\s+(?P<target>[\w\- ]+)", re.IGNORECASE), "uses"),
    (re.compile(r"\b(?P<source>[\w\- ]+?)\s+works on\s+(?P<target>[\w\- ]+)", re.IGNORECASE), "works_on"),
    (re.compile(r"\b(?P<source>[\w\- ]+?)\s+is in\s+(?P<target>[\w\- ]+)", re.IGNORECASE), "located_in"),
]


@dataclass(slots=True)
class ExtractionResult:
    candidates: list[MemoryCandidate] = field(default_factory=list)
    entities: list[MemoryEntity] = field(default_factory=list)
    relations: list[MemoryRelation] = field(default_factory=list)
    mode: str = "heuristic"


class MemoryExtractor:
    def __init__(self, *, model_client: BaseModelClient | None = None, model_name: str = "") -> None:
        self.model_client = model_client
        self.model_name = model_name

    def extract_interaction(
        self,
        *,
        user_input: str,
        assistant_output: str,
        extraction_mode: str,
        schema_id: str = "default",
    ) -> ExtractionResult:
        text = f"User said: {user_input}\nAssistant replied: {assistant_output}".strip()
        return self.extract_text(text=text, extraction_mode=extraction_mode, source_kind="interaction", schema_id=schema_id)

    def extract_document(
        self,
        *,
        title: str,
        content: str,
        extraction_mode: str,
        schema_id: str = "default",
    ) -> ExtractionResult:
        text = f"Document title: {title}\n\n{content}".strip()
        return self.extract_text(text=text, extraction_mode=extraction_mode, source_kind="document", schema_id=schema_id)

    def extract_text(self, *, text: str, extraction_mode: str, source_kind: str, schema_id: str = "default") -> ExtractionResult:
        mode = extraction_mode.lower().strip() or "hybrid"
        if mode in {"llm", "hybrid"}:
            llm_result = self._extract_with_llm(text=text, source_kind=source_kind)
            if llm_result is not None:
                return llm_result
        return self._extract_heuristically(text=text, source_kind=source_kind, schema_id=schema_id)

    def _extract_with_llm(self, *, text: str, source_kind: str) -> ExtractionResult | None:
        if self.model_client is None or not self.model_name:
            return None
        prompt = (
            "Extract durable memory candidates, entities, and relations from the text.\n"
            "Return strict JSON with keys candidates, entities, relations.\n"
            "Each candidate must include content, memory_type, importance, tags, source_kind, "
            "source_confidence, canonical_key, canonical_value.\n"
            "Valid memory_type values: working, episodic, semantic, perceptual.\n"
            "Text:\n"
            f"{text}"
        )
        try:
            response = self.model_client.generate(
                ModelRequest(
                    model=self.model_name,
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}],
                )
            )
        except Exception:
            return None
        try:
            payload = self._extract_json(response.text)
        except ValueError:
            return None
        candidate_items = payload.get("candidates", [])
        entity_items = payload.get("entities", [])
        relation_items = payload.get("relations", [])
        if not isinstance(candidate_items, list) or not isinstance(entity_items, list) or not isinstance(relation_items, list):
            return None
        candidates = [
            MemoryCandidate(
                content=str(item.get("content", "")).strip(),
                memory_type=str(item.get("memory_type", "episodic")).strip() or "episodic",
                importance=self._coerce_score(item.get("importance", 0.5), default=0.5),
                tags=self._coerce_tags(item.get("tags", [])),
                metadata={"extraction_mode": "llm"},
                source_kind=str(item.get("source_kind", source_kind)),
                source_confidence=self._coerce_score(item.get("source_confidence", 0.75), default=0.75),
                canonical_key=str(item.get("canonical_key", "")),
                canonical_value=str(item.get("canonical_value", "")),
            )
            for item in candidate_items
            if isinstance(item, dict)
            if str(item.get("content", "")).strip()
        ]
        entities = [
            MemoryEntity(
                entity_name=str(item.get("entity_name", "")).strip(),
                entity_type=str(item.get("entity_type", "entity")),
                confidence=self._coerce_score(item.get("confidence", 0.7), default=0.7),
                metadata={"extraction_mode": "llm"},
            )
            for item in entity_items
            if isinstance(item, dict)
            if str(item.get("entity_name", "")).strip()
        ]
        relations = [
            MemoryRelation(
                source=str(item.get("source", "")).strip(),
                relation=str(item.get("relation", "")).strip(),
                target=str(item.get("target", "")).strip(),
                confidence=self._coerce_score(item.get("confidence", 0.7), default=0.7),
                metadata={"extraction_mode": "llm"},
            )
            for item in relation_items
            if isinstance(item, dict)
            if str(item.get("source", "")).strip() and str(item.get("relation", "")).strip() and str(item.get("target", "")).strip()
        ]
        if not candidates and not entities and not relations:
            return None
        return ExtractionResult(candidates=candidates, entities=entities, relations=relations, mode="llm")

    @staticmethod
    def _coerce_score(value: Any, *, default: float) -> float:
        if isinstance(value, (int, float)):
            numeric = float(value)
        elif isinstance(value, str):
            cleaned = value.strip().lower()
            score_map = {
                "low": 0.3,
                "medium": 0.6,
                "med": 0.6,
                "high": 0.9,
                "very high": 0.98,
                "very_low": 0.15,
                "very low": 0.15,
            }
            if cleaned in score_map:
                numeric = score_map[cleaned]
            else:
                if cleaned.endswith("%"):
                    cleaned = cleaned[:-1].strip()
                    try:
                        numeric = float(cleaned) / 100.0
                    except ValueError:
                        return default
                else:
                    try:
                        numeric = float(cleaned)
                    except ValueError:
                        return default
        else:
            return default
        if numeric > 1.0:
            numeric = numeric / 100.0 if numeric <= 100.0 else 1.0
        if numeric < 0.0:
            return 0.0
        if numeric > 1.0:
            return 1.0
        return numeric

    @staticmethod
    def _coerce_tags(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(tag).strip() for tag in value if str(tag).strip()]
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[,|/]", value) if part.strip()]
        return []

    def _extract_heuristically(self, *, text: str, source_kind: str, schema_id: str) -> ExtractionResult:
        candidates: list[MemoryCandidate] = []
        entities: list[MemoryEntity] = []
        relations: list[MemoryRelation] = []
        seen_contents: set[str] = set()

        def add_candidate(candidate: MemoryCandidate) -> None:
            if not candidate.content:
                return
            key = candidate.content.lower().strip()
            if key in seen_contents:
                return
            seen_contents.add(key)
            candidate.metadata.setdefault("extraction_mode", "heuristic")
            candidates.append(candidate)

        for canonical_key, pattern in IDENTITY_PATTERNS.items():
            for match in pattern.finditer(text):
                value = self._clean(match.group("value"))
                if not value:
                    continue
                add_candidate(
                    MemoryCandidate(
                        content=f"User fact: {value}",
                        memory_type="semantic",
                        importance=0.88,
                        tags=["identity", canonical_key.split(":")[-1]],
                        source_kind=source_kind,
                        source_confidence=0.82,
                        canonical_key=canonical_key,
                        canonical_value=value,
                    )
                )
                entities.append(MemoryEntity(entity_name=value, entity_type="identity", confidence=0.82))

        for pattern in PREFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                raw_value = match.groupdict().get("value", "")
                value = self._strip_trailing_clause(self._clean(raw_value))
                if not value:
                    continue
                domain = self._infer_preference_domain(value)
                add_candidate(
                    MemoryCandidate(
                        content=f"User preference: {value}",
                        memory_type="semantic",
                        importance=0.9,
                        tags=["preference", domain],
                        source_kind=source_kind,
                        source_confidence=0.84,
                        canonical_key=f"user:preference:{domain}",
                        canonical_value=value,
                    )
                )
                relations.append(MemoryRelation(source="user", relation="prefers", target=value, confidence=0.84))
                entities.append(MemoryEntity(entity_name=value, entity_type="preference_target", confidence=0.8))

        for pattern in CONSTRAINT_PATTERNS:
            for match in pattern.finditer(text):
                value = self._strip_trailing_clause(self._clean(match.group("value")))
                if not value:
                    continue
                add_candidate(
                    MemoryCandidate(
                        content=f"User constraint: {value}",
                        memory_type="semantic",
                        importance=0.92,
                        tags=["constraint"],
                        source_kind=source_kind,
                        source_confidence=0.86,
                        canonical_key="user:constraint",
                        canonical_value=value,
                    )
                )
                relations.append(MemoryRelation(source="user", relation="constraint", target=value, confidence=0.8))

        for sentence in self._sentences(text):
            cleaned = self._clean(sentence)
            if len(cleaned.split()) < 5:
                continue
            if any(marker in cleaned.lower() for marker in ["research report", "summary", "result", "finding", "document title"]):
                add_candidate(
                    MemoryCandidate(
                        content=cleaned,
                        memory_type="episodic" if source_kind != "document" else "perceptual",
                        importance=0.72 if source_kind != "document" else 0.66,
                        tags=[source_kind],
                        source_kind=source_kind,
                        source_confidence=0.65,
                        canonical_key=f"{source_kind}:{self._slug(cleaned)[:48]}",
                        canonical_value=cleaned,
                    )
                )

        for source_pattern, relation_name in RELATION_PATTERNS:
            for match in source_pattern.finditer(text):
                source = self._clean(match.group("source"))
                target = self._clean(match.group("target"))
                if not source or not target:
                    continue
                relations.append(MemoryRelation(source=source, relation=relation_name, target=target, confidence=0.72))
                entities.append(MemoryEntity(entity_name=source, entity_type="entity", confidence=0.7))
                entities.append(MemoryEntity(entity_name=target, entity_type="entity", confidence=0.7))

        if source_kind == "document":
            excerpt = self._document_excerpt(text)
            if excerpt:
                add_candidate(
                    MemoryCandidate(
                        content=excerpt,
                        memory_type="perceptual",
                        importance=0.62,
                        tags=["document", "perceptual"],
                        source_kind="document_excerpt",
                        source_confidence=0.7,
                        canonical_key=f"document:{self._slug(excerpt)[:48]}",
                        canonical_value=excerpt,
                    )
                )

        if schema_id == "research_workflow":
            self._extract_research_candidates(text, source_kind, add_candidate, entities, relations)
        if schema_id == "travel_planner":
            self._extract_travel_candidates(text, source_kind, add_candidate, entities, relations)

        return ExtractionResult(candidates=candidates, entities=entities, relations=relations, mode="heuristic")

    @staticmethod
    def _extract_json(raw_text: str) -> dict[str, object]:
        payload = raw_text.strip()
        if payload.startswith("```"):
            payload = payload.strip("`")
            if payload.startswith("json"):
                payload = payload[4:].strip()
        start = payload.find("{")
        end = payload.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object found")
        return json.loads(payload[start : end + 1])

    @staticmethod
    def _sentences(text: str) -> list[str]:
        lines = [line.strip() for line in re.split(r"[\n\r]+", text) if line.strip()]
        sentences: list[str] = []
        for line in lines:
            sentences.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line) if part.strip())
        return sentences

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip(" .:-\n\t"))

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    @staticmethod
    def _infer_preference_domain(value: str) -> str:
        lowered = value.lower()
        if any(token in lowered for token in ["brief", "concise", "short", "detailed", "technical"]):
            return "response_style"
        if any(token in lowered for token in ["python", "java", "typescript", "vue", "react"]):
            return "technology"
        return "general"

    @staticmethod
    def _document_excerpt(text: str, max_sentences: int = 2) -> str:
        sentences = [sentence for sentence in MemoryExtractor._sentences(text) if sentence]
        excerpt = " ".join(sentences[:max_sentences]).strip()
        return excerpt[:600]

    @staticmethod
    def _strip_trailing_clause(value: str) -> str:
        parts = re.split(r"\b(?:and|but|while|because)\b", value, maxsplit=1, flags=re.IGNORECASE)
        return parts[0].strip(" ,.;:-")

    def _extract_research_candidates(
        self,
        text: str,
        source_kind: str,
        add_candidate,
        entities: list[MemoryEntity],
        relations: list[MemoryRelation],
    ) -> None:
        topic_match = re.search(r"research (?:session started|topic) (?:for topic:|topic:)\s*(?P<topic>[^.\n]+)", text, re.IGNORECASE)
        if topic_match:
            topic = self._clean(topic_match.group("topic"))
            add_candidate(
                MemoryCandidate(
                    content=f"Research topic: {topic}",
                    memory_type="semantic",
                    importance=0.9,
                    tags=["research_topic"],
                    source_kind=source_kind,
                    source_confidence=0.82,
                    canonical_key="research:topic",
                    canonical_value=topic,
                )
            )
            entities.append(MemoryEntity(entity_name=topic, entity_type="research_topic", confidence=0.82))
        task_match = re.search(r"task\s+(?P<task_id>\d+)\s+search observation for\s+(?P<title>[^:]+):\s*(?P<value>.+)", text, re.IGNORECASE)
        if task_match:
            title = self._clean(task_match.group("title"))
            value = self._clean(task_match.group("value"))
            add_candidate(
                MemoryCandidate(
                    content=f"Task observation: {title} -> {value}",
                    memory_type="working",
                    importance=0.74,
                    tags=["task_observation"],
                    source_kind=source_kind,
                    source_confidence=0.75,
                    canonical_key=f"research:task:{task_match.group('task_id')}",
                    canonical_value=value,
                )
            )
            entities.append(MemoryEntity(entity_name=title, entity_type="task", confidence=0.75))

    def _extract_travel_candidates(
        self,
        text: str,
        source_kind: str,
        add_candidate,
        entities: list[MemoryEntity],
        relations: list[MemoryRelation],
    ) -> None:
        budget_match = re.search(r"\b(?:budget|cost)\s*(?:is|around|under)?\s*(?P<value>[0-9][^.\n]*)", text, re.IGNORECASE)
        if budget_match:
            value = self._clean(budget_match.group("value"))
            add_candidate(
                MemoryCandidate(
                    content=f"Travel budget: {value}",
                    memory_type="semantic",
                    importance=0.86,
                    tags=["budget"],
                    source_kind=source_kind,
                    source_confidence=0.8,
                    canonical_key="travel:budget",
                    canonical_value=value,
                )
            )
        destination_match = re.search(r"\b(?:travel to|visit|destination is)\s+(?P<value>[^.\n]+)", text, re.IGNORECASE)
        if destination_match:
            value = self._clean(destination_match.group("value"))
            add_candidate(
                MemoryCandidate(
                    content=f"Travel destination: {value}",
                    memory_type="semantic",
                    importance=0.88,
                    tags=["destination"],
                    source_kind=source_kind,
                    source_confidence=0.82,
                    canonical_key="travel:destination",
                    canonical_value=value,
                )
            )
            entities.append(MemoryEntity(entity_name=value, entity_type="destination", confidence=0.82))
            relations.append(MemoryRelation(source="user", relation="travels_to", target=value, confidence=0.8))
