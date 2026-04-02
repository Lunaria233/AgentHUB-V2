from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import gc
from pathlib import Path
import shutil
from tempfile import mkdtemp

from app.platform.apps.profiles import MemoryProfile
from app.platform.memory.embedding import LocalHashEmbedder
from app.platform.memory.service import MemoryService
from app.platform.memory.store import SQLiteMemoryStore


@dataclass(slots=True)
class MemoryEvalCaseResult:
    case_id: str
    recall_at_k: float
    precision_at_k: float
    pollution_rate: float
    retrieved: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MemoryEvalSummary:
    average_recall_at_k: float
    average_precision_at_k: float
    average_pollution_rate: float
    conflict_resolution_quality: float
    cases: list[MemoryEvalCaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "average_recall_at_k": self.average_recall_at_k,
            "average_precision_at_k": self.average_precision_at_k,
            "average_pollution_rate": self.average_pollution_rate,
            "conflict_resolution_quality": self.conflict_resolution_quality,
            "cases": [asdict(case) for case in self.cases],
        }


class MemoryEvaluator:
    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    def run_default_suite(self, *, app_id: str, profile: MemoryProfile) -> MemoryEvalSummary:
        cases: list[MemoryEvalCaseResult] = []
        cases.append(self._run_chat_preference_case(app_id=app_id, profile=profile))
        cases.append(self._run_document_case(app_id=app_id, profile=profile))
        conflict_quality = self._run_conflict_case(app_id=app_id, profile=profile)
        return MemoryEvalSummary(
            average_recall_at_k=self._average([case.recall_at_k for case in cases]),
            average_precision_at_k=self._average([case.precision_at_k for case in cases]),
            average_pollution_rate=self._average([case.pollution_rate for case in cases]),
            conflict_resolution_quality=conflict_quality,
            cases=cases,
        )

    def _run_chat_preference_case(self, *, app_id: str, profile: MemoryProfile) -> MemoryEvalCaseResult:
        user_id = "eval-user-chat"
        session_id = "eval-chat-session"
        self.memory_service.remember_interaction(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            content="User: I prefer concise technical explanations and I live in Shanghai. Assistant: Understood.",
            user_message="I prefer concise technical explanations and I live in Shanghai.",
            assistant_message="Understood.",
            profile=profile,
        )
        self.memory_service.remember_fact(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            content="User uses Python for backend work.",
            tags=["fact"],
            profile=profile,
        )
        retrieved = self.memory_service.search_relevant_memories(
            query="What response style and location should I remember?",
            app_id=app_id,
            session_id=None,
            user_id=user_id,
            limit=6,
            memory_types=profile.retrieval_types,
            retrieval_mode=profile.retrieval_mode,
            include_graph=profile.graph_enabled,
        )
        expected = ["concise", "shanghai"]
        return self._score_case("chat_preference", retrieved, expected)

    def _run_document_case(self, *, app_id: str, profile: MemoryProfile) -> MemoryEvalCaseResult:
        user_id = "eval-user-doc"
        session_id = "eval-doc-session"
        self.memory_service.remember_document(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            title="Atlas Spec",
            content=(
                "Atlas uses Python services and a Vue dashboard. "
                "The main constraint is low latency and concise reporting. "
                "Atlas supports asynchronous research workflows."
            ),
            profile=profile,
            source_path="specs/atlas.md",
        )
        retrieved = self.memory_service.search_relevant_memories(
            query="What does Atlas use and what constraint matters?",
            app_id=app_id,
            session_id=None,
            user_id=user_id,
            limit=6,
            memory_types=profile.retrieval_types,
            retrieval_mode=profile.retrieval_mode,
            include_graph=profile.graph_enabled,
        )
        expected = ["atlas", "python", "latency"]
        return self._score_case("document_perceptual", retrieved, expected)

    def _run_conflict_case(self, *, app_id: str, profile: MemoryProfile) -> float:
        user_id = "eval-user-conflict"
        session_id = "eval-conflict-session"
        self.memory_service.remember_preference(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            content="User preference: concise technical explanations",
            profile=profile,
        )
        self.memory_service.remember_preference(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            content="User preference: highly detailed explanations",
            profile=profile,
        )
        summary = self.memory_service.summarize_memory(app_id=app_id, user_id=user_id)
        active = int(summary.get("by_status", {}).get("active", 0))
        conflict = int(summary.get("by_status", {}).get("conflict", 0))
        if active >= 1 and conflict >= 1:
            return 1.0
        if active >= 1:
            return 0.5
        return 0.0

    def _score_case(self, case_id: str, retrieved: list[dict[str, object]], expected_keywords: list[str]) -> MemoryEvalCaseResult:
        retrieved_texts = [str(item.get("content", "")).lower() for item in retrieved]
        matched_expected = sum(1 for keyword in expected_keywords if any(keyword in text for text in retrieved_texts))
        relevant_retrieved = sum(1 for text in retrieved_texts if any(keyword in text for keyword in expected_keywords))
        total_retrieved = max(1, len(retrieved_texts))
        recall = matched_expected / max(1, len(expected_keywords))
        precision = relevant_retrieved / total_retrieved
        pollution = 1.0 - precision
        return MemoryEvalCaseResult(
            case_id=case_id,
            recall_at_k=round(recall, 4),
            precision_at_k=round(precision, 4),
            pollution_rate=round(pollution, 4),
            retrieved=retrieved_texts,
            expected=expected_keywords,
        )

    @staticmethod
    def _average(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)


@contextmanager
def isolated_memory_service(source_service: MemoryService):
    temp_dir = Path(mkdtemp(prefix="agent-platform-memory-eval-"))
    db_path = temp_dir / "memory_eval.db"
    local_settings = source_service.settings
    dimensions = local_settings.local_embedding_dimensions if local_settings is not None else 128
    service = MemoryService(
        SQLiteMemoryStore(db_path),
        settings=local_settings,
        model_client=None,
        model_name="",
        embedder=LocalHashEmbedder(dimensions=dimensions),
        vector_index=None,
        graph_backend=None,
    )
    try:
        yield service
    finally:
        del service
        gc.collect()
        shutil.rmtree(temp_dir, ignore_errors=True)
