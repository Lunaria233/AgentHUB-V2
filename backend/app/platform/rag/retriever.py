from __future__ import annotations

import json
import re
from typing import Any

from app.platform.models.base import BaseModelClient, ModelRequest
from app.platform.observability.tracing import TraceService
from app.platform.rag.document import RAGSearchHit, RetrievalQuery, RetrievalResult
from app.platform.rag.reranker import FeatureReranker
from app.platform.rag.store import SQLiteRAGStore


class QueryEnhancer:
    def __init__(
        self,
        *,
        model_client: BaseModelClient | None = None,
        model_name: str = "",
        default_mode: str = "hybrid",
        hyde_max_tokens: int = 220,
        mqe_variants: int = 4,
    ) -> None:
        self.model_client = model_client
        self.model_name = model_name
        self.default_mode = default_mode
        self.hyde_max_tokens = hyde_max_tokens
        self.mqe_variants = max(1, mqe_variants)

    def expand(self, query: RetrievalQuery) -> tuple[list[str], dict[str, Any]]:
        queries = [query.query.strip()]
        debug: dict[str, Any] = {
            "mqe_mode": query.metadata.get("query_rewrite_mode", self.default_mode),
            "hyde_mode": query.metadata.get("hyde_mode", "model"),
        }

        if query.query_rewrite_enabled:
            mqe_queries = self._mqe(query.query, mode=str(debug["mqe_mode"]))
            debug["mqe_queries"] = mqe_queries
            queries.extend(mqe_queries)

        if query.hyde_enabled:
            hypothetical = self._hyde(query.query, mode=str(debug["hyde_mode"]))
            if hypothetical:
                debug["hyde_preview"] = hypothetical[:240]
                queries.append(hypothetical)

        deduped = [item for item in dict.fromkeys(item for item in queries if item)]
        debug["expanded_queries"] = deduped
        return deduped, debug

    def _mqe(self, query: str, *, mode: str) -> list[str]:
        if mode in {"llm", "hybrid"}:
            llm_queries = self._mqe_via_llm(query)
            if llm_queries:
                if mode == "llm":
                    return llm_queries[: self.mqe_variants]
                heuristic_queries = self._mqe_heuristic(query)
                combined = list(dict.fromkeys(llm_queries + heuristic_queries))
                return combined[: self.mqe_variants]
        return self._mqe_heuristic(query)[: self.mqe_variants]

    def _mqe_via_llm(self, query: str) -> list[str]:
        if self.model_client is None or not self.model_name:
            return []
        try:
            response = self.model_client.generate(
                ModelRequest(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Generate 3 to 4 diverse retrieval queries for the user's information need. "
                                "Return JSON only, as an array of strings. Do not explain."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                    temperature=0.1,
                    max_tokens=220,
                )
            )
        except Exception:
            return []
        return self._parse_json_array(response.text)

    def _mqe_heuristic(self, query: str) -> list[str]:
        normalized = " ".join(query.strip().split())
        variants: list[str] = []
        comparison_markers = ["compare", "difference", "versus", "vs", "区别", "对比", "比较", "差异"]
        if any(marker in normalized.lower() for marker in comparison_markers):
            parts = [item.strip() for item in re.split(r"\bvs\b|\bversus\b|,|，|和|与|比较|对比|区别|差异", normalized, flags=re.IGNORECASE) if item.strip()]
            variants.extend(parts[:2])
            if len(parts) >= 2:
                variants.append(f"{parts[0]} advantages disadvantages")
                variants.append(f"{parts[1]} advantages disadvantages")
        question_stripped = re.sub(r"^(what|how|why|when|where|who)\s+", "", normalized, flags=re.IGNORECASE).strip()
        question_stripped = re.sub(r"(是什么|如何|为什么|怎么|怎样)$", "", question_stripped).strip()
        if question_stripped and question_stripped != normalized:
            variants.append(question_stripped)
            variants.append(f"{question_stripped} overview")
        words = normalized.split()
        if len(words) > 4:
            variants.append(" ".join(words[:4]))
        if normalized:
            variants.append(f"{normalized} key facts")
        return [item for item in dict.fromkeys(item for item in variants if item and item != query)]

    def _hyde(self, query: str, *, mode: str) -> str:
        if mode == "fallback":
            return self._hyde_fallback(query)
        if self.model_client is None or not self.model_name:
            return self._hyde_fallback(query)
        try:
            response = self.model_client.generate(
                ModelRequest(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Write a concise factual paragraph that would likely appear in a document answering the user's query. "
                                "Do not mention that it is hypothetical."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                    temperature=0.1,
                    max_tokens=self.hyde_max_tokens,
                )
            )
        except Exception:
            return self._hyde_fallback(query)
        content = response.text.strip()
        return content or self._hyde_fallback(query)

    @staticmethod
    def _hyde_fallback(query: str) -> str:
        return f"This document explains the following topic in detail: {query}. It covers definitions, key facts, comparisons, and practical guidance."

    @staticmethod
    def _parse_json_array(text: str) -> list[str]:
        raw = text.strip()
        if not raw:
            return []
        candidates = [raw]
        if "[" in raw and "]" in raw:
            candidates.append(raw[raw.find("[") : raw.rfind("]") + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return []


class HybridRetriever:
    def __init__(
        self,
        *,
        store: SQLiteRAGStore,
        vector_index,
        embedder,
        trace_service: TraceService | None = None,
        model_client: BaseModelClient | None = None,
        model_name: str = "",
        query_rewrite_mode: str = "hybrid",
        hyde_max_tokens: int = 220,
        mqe_variants: int = 4,
        rerank_strategy: str = "feature",
        rerank_top_n: int = 12,
    ) -> None:
        self.store = store
        self.vector_index = vector_index
        self.embedder = embedder
        self.trace_service = trace_service
        self.enhancer = QueryEnhancer(
            model_client=model_client,
            model_name=model_name,
            default_mode=query_rewrite_mode,
            hyde_max_tokens=hyde_max_tokens,
            mqe_variants=mqe_variants,
        )
        self.reranker = FeatureReranker(embedder=embedder, strategy=rerank_strategy)
        self.rerank_top_n = max(4, rerank_top_n)

    def retrieve(
        self,
        *,
        query: RetrievalQuery,
        candidate_chunks: list[dict[str, Any]],
        vector_should_filters: list[dict[str, Any]],
        vector_must_filters: list[dict[str, Any]] | None = None,
        trace_id: str | None = None,
    ) -> RetrievalResult:
        expanded_queries, enhancement_debug = self.enhancer.expand(query)
        lexical_hits = self._lexical_search(expanded_queries, candidate_chunks, limit=max(query.limit * 6, 24))
        vector_hits = self._vector_search(
            expanded_queries,
            limit=max(query.limit * 6, 24),
            should_filters=vector_should_filters,
            must_filters=vector_must_filters,
        )
        merged = self._merge_hits(lexical_hits=lexical_hits, vector_hits=vector_hits, query=query, limit=max(query.limit * 3, self.rerank_top_n))
        reranked = self._rerank(query=query, hits=merged, limit=query.limit)
        result = RetrievalResult(
            query=query.query,
            mode=query.retrieval_mode,
            items=reranked,
            sources=[item.citation for item in reranked],
            debug={
                **enhancement_debug,
                "lexical_count": len(lexical_hits),
                "vector_count": len(vector_hits),
                "candidate_chunks": len(candidate_chunks),
                "rerank_enabled": query.rerank_enabled,
                "rerank_strategy": query.metadata.get("rerank_strategy", self.reranker.strategy),
                "rerank_top_n": min(len(merged), max(query.limit * 3, self.rerank_top_n)),
            },
        )
        if self.trace_service and trace_id:
            self.trace_service.log_event(
                trace_id=trace_id,
                event_type="rag_retrieval",
                payload={
                    "query": query.query,
                    "mode": query.retrieval_mode,
                    "limit": query.limit,
                    **result.debug,
                },
            )
        return result

    def _lexical_search(self, queries: list[str], candidate_chunks: list[dict[str, Any]], limit: int) -> dict[str, dict[str, Any]]:
        hits: dict[str, dict[str, Any]] = {}
        for query in queries:
            tokens = self._tokenize(query)
            for chunk in candidate_chunks:
                score = self._lexical_score(tokens, str(chunk.get("title", "")), str(chunk.get("content", "")))
                if score <= 0:
                    continue
                existing = hits.get(str(chunk["chunk_id"]))
                if existing is None or score > float(existing.get("lexical_score", 0.0)):
                    hits[str(chunk["chunk_id"])] = {**chunk, "lexical_score": score}
        ranked = dict(sorted(hits.items(), key=lambda item: float(item[1]["lexical_score"]), reverse=True)[:limit])
        return ranked

    def _vector_search(
        self,
        queries: list[str],
        *,
        limit: int,
        should_filters: list[dict[str, Any]],
        must_filters: list[dict[str, Any]] | None,
    ) -> dict[str, float]:
        if self.vector_index is None or not getattr(self.vector_index, "enabled", False):
            return {}
        scores: dict[str, float] = {}
        for query in queries:
            vector = self.embedder.encode(query)
            try:
                raw_results = self.vector_index.search(
                    query_vector=vector,
                    limit=limit,
                    should_filters=should_filters,
                    must_filters=must_filters,
                )
            except Exception:
                return scores
            for item in raw_results:
                chunk_id = str(item.get("chunk_id", ""))
                if not chunk_id:
                    continue
                scores[chunk_id] = max(scores.get(chunk_id, 0.0), float(item.get("score", 0.0)))
        return scores

    def _merge_hits(
        self,
        *,
        lexical_hits: dict[str, dict[str, Any]],
        vector_hits: dict[str, float],
        query: RetrievalQuery,
        limit: int,
    ) -> list[RAGSearchHit]:
        mode = query.retrieval_mode.lower()
        candidate_ids = set(lexical_hits) | set(vector_hits)
        if not candidate_ids:
            return []
        missing_chunk_ids = [chunk_id for chunk_id in candidate_ids if chunk_id not in lexical_hits]
        extra_chunks = {item["chunk_id"]: item for item in self.store.list_chunks(chunk_ids=missing_chunk_ids)}
        lexical_max = max((float(item.get("lexical_score", 0.0)) for item in lexical_hits.values()), default=1.0)
        vector_max = max(vector_hits.values(), default=1.0)
        scope_priority = {
            "session_temporary": 1.0,
            "user_private": 0.86,
            "app_shared": 0.72,
            "system_public": 0.62,
        }
        ranked: list[RAGSearchHit] = []
        for chunk_id in candidate_ids:
            base = lexical_hits.get(chunk_id) or extra_chunks.get(chunk_id)
            if not base:
                continue
            lexical_score = float((lexical_hits.get(chunk_id) or {}).get("lexical_score", 0.0))
            vector_score = float(vector_hits.get(chunk_id, 0.0))
            normalized_lexical = lexical_score / lexical_max if lexical_max else 0.0
            normalized_vector = vector_score / vector_max if vector_max else 0.0
            if mode == "lexical":
                score = normalized_lexical
            elif mode == "vector":
                score = normalized_vector
            else:
                score = normalized_lexical * 0.45 + normalized_vector * 0.45
            score += scope_priority.get(str(base.get("visibility", "")), 0.55) * 0.1
            ranked.append(
                RAGSearchHit(
                    chunk_id=str(base["chunk_id"]),
                    document_id=str(base["document_id"]),
                    title=str(base.get("title", "")),
                    content=str(base.get("content", "")),
                    preview=str(base.get("preview", "")),
                    page_or_section=str(base.get("page_or_section", "")),
                    score=score,
                    lexical_score=lexical_score,
                    vector_score=vector_score,
                    visibility=str(base.get("visibility", "user_private")),
                    source_type=str(base.get("source_type", "text_input")),
                    kb_id=str(base.get("kb_id", "")),
                    source_uri=str(base.get("source_uri", "")),
                    metadata=dict(base.get("metadata", {})),
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        deduped: list[RAGSearchHit] = []
        seen_keys: set[tuple[str, str]] = set()
        for item in ranked:
            key = (item.document_id, item.chunk_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def _rerank(self, *, query: RetrievalQuery, hits: list[RAGSearchHit], limit: int) -> list[RAGSearchHit]:
        if not query.rerank_enabled:
            return hits[:limit]
        top_n = min(len(hits), int(query.metadata.get("rerank_top_n", self.rerank_top_n)))
        reranked = self.reranker.rerank(query=query, hits=hits[:top_n], limit=limit)
        if len(reranked) < limit:
            supplemental = [item for item in hits if item.chunk_id not in {hit.chunk_id for hit in reranked}]
            reranked.extend(supplemental[: max(0, limit - len(reranked))])
        return reranked[:limit]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        cleaned = "".join(char.lower() if char.isalnum() else " " for char in text)
        tokens = [token for token in cleaned.split() if token]
        if len(tokens) <= 1:
            return tokens
        phrases = [f"{tokens[index]}_{tokens[index + 1]}" for index in range(len(tokens) - 1)]
        return tokens + phrases

    def _lexical_score(self, tokens: list[str], title: str, content: str) -> float:
        if not tokens:
            return 0.0
        haystack = self._tokenize(f"{title} {content}")
        if not haystack:
            return 0.0
        token_set = set(haystack)
        overlap = sum(1 for token in tokens if token in token_set)
        score = overlap / max(len(set(tokens)), 1)
        if title:
            title_tokens = set(self._tokenize(title))
            if any(token in title_tokens for token in tokens):
                score += 0.15
        return min(score, 1.0)
