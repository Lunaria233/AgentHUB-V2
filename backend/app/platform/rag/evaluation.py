from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

from app.platform.rag.chunking import StructuredChunker
from app.platform.rag.document import RAGEvalCaseResult, RAGEvalSummary, RetrievalQuery
from app.platform.rag.index import QdrantRAGIndex
from app.platform.rag.parsers import DocumentParser
from app.platform.rag.service import RAGService
from app.platform.rag.store import SQLiteRAGStore


class RAGEvaluator:
    def __init__(
        self,
        *,
        settings,
        embedder,
        model_client,
        trace_service=None,
    ) -> None:
        self.settings = settings
        self.embedder = embedder
        self.model_client = model_client
        self.trace_service = trace_service

    def run(self, *, app_id: str = "chat") -> RAGEvalSummary:
        root = Path(mkdtemp(prefix="agent-platform-rag-eval-"))
        eval_collection = f"{self.settings.rag_qdrant_collection}_eval_{uuid4().hex[:8]}"
        vector_index = None
        if self.settings.qdrant_url:
            vector_index = QdrantRAGIndex(
                base_url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key,
                collection=eval_collection,
            )
        service = RAGService(
            store=SQLiteRAGStore(root / "rag_eval.db"),
            parser=DocumentParser(),
            chunker=StructuredChunker(
                chunk_size=self.settings.rag_chunk_size,
                chunk_overlap=self.settings.rag_chunk_overlap,
            ),
            embedder=self.embedder,
            vector_index=vector_index,
            model_client=self.model_client,
            model_name=self.settings.llm_model,
            trace_service=self.trace_service,
            uploads_root=root / "uploads",
        )
        try:
            self._seed(service=service, app_id=app_id)
            case_results = self._run_cases(service=service, app_id=app_id)
        finally:
            if vector_index is not None:
                try:
                    vector_index.drop_collection(eval_collection)
                except Exception:
                    pass
            del service
            shutil.rmtree(root, ignore_errors=True)
        if not case_results:
            return RAGEvalSummary(
                average_recall_at_k=0.0,
                average_precision_at_k=0.0,
                average_mrr=0.0,
                average_leakage_rate=0.0,
                average_source_coverage=0.0,
                cases=[],
            )
        count = len(case_results)
        return RAGEvalSummary(
            average_recall_at_k=round(sum(item.recall_at_k for item in case_results) / count, 4),
            average_precision_at_k=round(sum(item.precision_at_k for item in case_results) / count, 4),
            average_mrr=round(sum(item.mrr for item in case_results) / count, 4),
            average_leakage_rate=round(sum(item.leakage_rate for item in case_results) / count, 4),
            average_source_coverage=round(sum(item.source_coverage for item in case_results) / count, 4),
            cases=case_results,
        )

    def _seed(self, *, service: RAGService, app_id: str) -> None:
        seed_documents = [
            {
                "document_id": "eval_chat_profile",
                "title": "User Profile",
                "text": "Zhang San is interested in Rust, distributed systems, and large-scale backend engineering.",
                "user_id": "eval-user-a",
                "knowledge_target": "user_private",
                "source_type": "user_text",
            },
            {
                "document_id": "eval_compare_doc",
                "title": "CNN vs Transformer",
                "text": (
                    "CNNs focus on local receptive fields and convolution kernels. "
                    "Transformers rely on self-attention and are stronger at global dependency modeling."
                ),
                "user_id": "eval-user-a",
                "knowledge_target": "app_shared",
                "source_type": "app_knowledge",
            },
            {
                "document_id": "eval_mqe_doc",
                "title": "MQE Retrieval Notes",
                "text": (
                    "Multi-query expansion improves retrieval recall by generating semantically related queries "
                    "that cover paraphrases, aliases, and sub-intents."
                ),
                "user_id": "eval-user-a",
                "knowledge_target": "app_shared",
                "source_type": "app_knowledge",
            },
            {
                "document_id": "eval_hyde_doc",
                "title": "HyDE Retrieval Notes",
                "text": (
                    "Hypothetical document embeddings generate a synthetic answer passage first and use it to retrieve "
                    "documents that are semantically closer to the likely answer space."
                ),
                "user_id": "eval-user-a",
                "knowledge_target": "system_public",
                "source_type": "system_knowledge",
            },
            {
                "document_id": "eval_scope_secret",
                "title": "Other User Private Music Preference",
                "text": "Li Si privately prefers jazz piano and should not leak to other users.",
                "user_id": "eval-user-b",
                "knowledge_target": "user_private",
                "source_type": "user_text",
            },
            {
                "document_id": "eval_session_note",
                "title": "Temporary Session Note",
                "text": "The current interview prep session focuses on distributed tracing and system design.",
                "user_id": "eval-user-a",
                "session_id": "eval-session-a",
                "knowledge_target": "session_temporary",
                "source_type": "generated_summary",
            },
        ]
        for item in seed_documents:
            service.ingest_text(
                title=item["title"],
                text=item["text"],
                app_id=app_id,
                user_id=item.get("user_id"),
                session_id=item.get("session_id"),
                knowledge_target=item["knowledge_target"],
                source_type=item["source_type"],
                document_id=item["document_id"],
            )

    def _run_cases(self, *, service: RAGService, app_id: str) -> list[RAGEvalCaseResult]:
        cases: list[dict[str, object]] = [
            {
                "case_id": "exact_user_profile",
                "description": "hybrid retrieval should find user-private profile",
                "query": RetrievalQuery(
                    query="What technologies does Zhang San like?",
                    app_id=app_id,
                    user_id="eval-user-a",
                    limit=4,
                    retrieval_mode="hybrid",
                    include_public=True,
                    include_app_shared=True,
                    include_user_private=True,
                    include_session_temporary=False,
                    metadata={"query_rewrite_mode": "heuristic"},
                ),
                "expected": ["eval_chat_profile"],
                "leak_forbidden": ["eval_scope_secret"],
                "mode": "hybrid",
            },
            {
                "case_id": "mqe_recall",
                "description": "MQE should retrieve multi-query expansion notes for paraphrased query",
                "query": RetrievalQuery(
                    query="How can multiple rewritten queries improve recall?",
                    app_id=app_id,
                    user_id="eval-user-a",
                    limit=4,
                    retrieval_mode="hybrid",
                    query_rewrite_enabled=True,
                    include_public=True,
                    include_app_shared=True,
                    include_user_private=True,
                    include_session_temporary=False,
                    metadata={"query_rewrite_mode": "heuristic"},
                ),
                "expected": ["eval_mqe_doc"],
                "leak_forbidden": ["eval_scope_secret"],
                "mode": "mqe",
            },
            {
                "case_id": "hyde_semantic",
                "description": "HyDE should pull hypothetical-document retrieval guidance",
                "query": RetrievalQuery(
                    query="How do synthetic answer passages help retrieve related documents?",
                    app_id=app_id,
                    user_id="eval-user-a",
                    limit=4,
                    retrieval_mode="hybrid",
                    hyde_enabled=True,
                    include_public=True,
                    include_app_shared=True,
                    include_user_private=True,
                    include_session_temporary=False,
                    metadata={"hyde_mode": "fallback"},
                ),
                "expected": ["eval_hyde_doc"],
                "leak_forbidden": ["eval_scope_secret"],
                "mode": "hyde",
            },
            {
                "case_id": "rerank_compare",
                "description": "rerank should keep comparison document at top",
                "query": RetrievalQuery(
                    query="Compare CNN and Transformer architectures",
                    app_id=app_id,
                    user_id="eval-user-a",
                    limit=3,
                    retrieval_mode="hybrid",
                    include_public=True,
                    include_app_shared=True,
                    include_user_private=True,
                    include_session_temporary=False,
                    rerank_enabled=True,
                    metadata={"rerank_strategy": "feature", "rerank_top_n": 8, "query_rewrite_mode": "heuristic"},
                ),
                "expected": ["eval_compare_doc"],
                "leak_forbidden": ["eval_scope_secret"],
                "mode": "rerank",
            },
            {
                "case_id": "scope_isolation",
                "description": "private documents from other users must not leak",
                "query": RetrievalQuery(
                    query="Who likes jazz piano?",
                    app_id=app_id,
                    user_id="eval-user-a",
                    limit=4,
                    retrieval_mode="hybrid",
                    include_public=True,
                    include_app_shared=True,
                    include_user_private=True,
                    include_session_temporary=True,
                    session_id="eval-session-a",
                ),
                "expected": [],
                "leak_forbidden": ["eval_scope_secret"],
                "mode": "scope",
            },
        ]

        results: list[RAGEvalCaseResult] = []
        for case in cases:
            query = case["query"]
            result = service.search(query)
            retrieved_doc_ids = [item.document_id for item in result.items]
            expected = list(case["expected"])
            forbidden = list(case["leak_forbidden"])
            recall = self._recall_at_k(retrieved_doc_ids, expected)
            precision = self._precision_at_k(retrieved_doc_ids, expected)
            mrr = self._mrr(retrieved_doc_ids, expected)
            leakage = self._leakage_rate(retrieved_doc_ids, forbidden)
            source_coverage = 1.0 if result.sources else 0.0
            results.append(
                RAGEvalCaseResult(
                    case_id=str(case["case_id"]),
                    description=str(case["description"]),
                    mode=str(case["mode"]),
                    recall_at_k=round(recall, 4),
                    precision_at_k=round(precision, 4),
                    mrr=round(mrr, 4),
                    leakage_rate=round(leakage, 4),
                    source_coverage=round(source_coverage, 4),
                    expected=expected,
                    retrieved=retrieved_doc_ids,
                    debug=result.debug,
                )
            )
        return results

    @staticmethod
    def _recall_at_k(retrieved: list[str], expected: list[str]) -> float:
        if not expected:
            return 1.0
        hit_count = sum(1 for item in expected if item in retrieved)
        return hit_count / len(expected)

    @staticmethod
    def _precision_at_k(retrieved: list[str], expected: list[str]) -> float:
        if not retrieved:
            return 1.0 if not expected else 0.0
        if not expected:
            return 1.0
        hit_count = sum(1 for item in retrieved if item in set(expected))
        return hit_count / len(retrieved)

    @staticmethod
    def _mrr(retrieved: list[str], expected: list[str]) -> float:
        if not expected:
            return 1.0
        expected_set = set(expected)
        for index, item in enumerate(retrieved, start=1):
            if item in expected_set:
                return 1.0 / index
        return 0.0

    @staticmethod
    def _leakage_rate(retrieved: list[str], forbidden: list[str]) -> float:
        if not forbidden:
            return 0.0
        leakage = sum(1 for item in retrieved if item in set(forbidden))
        return leakage / len(retrieved) if retrieved else 0.0
