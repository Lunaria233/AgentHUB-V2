from __future__ import annotations

import math
from dataclasses import replace

from app.platform.rag.document import RAGSearchHit, RetrievalQuery


class FeatureReranker:
    def __init__(self, *, embedder, strategy: str = "feature") -> None:
        self.embedder = embedder
        self.strategy = strategy

    def rerank(self, *, query: RetrievalQuery, hits: list[RAGSearchHit], limit: int) -> list[RAGSearchHit]:
        if not hits:
            return []
        query_vector = self.embedder.encode(query.query)
        max_base = max((item.score for item in hits), default=1.0) or 1.0
        max_lexical = max((item.lexical_score for item in hits), default=1.0) or 1.0
        max_vector = max((item.vector_score for item in hits), default=1.0) or 1.0

        reranked: list[RAGSearchHit] = []
        for item in hits:
            chunk_vector = self.embedder.encode(f"{item.title}\n{item.content}")
            semantic_similarity = self._cosine(query_vector, chunk_vector)
            lexical_coverage = self._token_overlap(query.query, f"{item.title} {item.content}")
            title_overlap = self._token_overlap(query.query, item.title)
            source_weight = {
                "generated_report": 0.95,
                "generated_summary": 0.9,
                "user_upload": 0.88,
                "user_text": 0.84,
                "url_import": 0.8,
                "web_import": 0.8,
                "app_knowledge": 0.76,
                "system_knowledge": 0.7,
            }.get(item.source_type, 0.72)
            visibility_weight = {
                "session_temporary": 1.0,
                "user_private": 0.9,
                "app_shared": 0.78,
                "system_public": 0.68,
            }.get(item.visibility, 0.68)

            base_score = item.score / max_base
            lexical_score = item.lexical_score / max_lexical if item.lexical_score else 0.0
            vector_score = item.vector_score / max_vector if item.vector_score else 0.0
            rerank_score = (
                semantic_similarity * 0.34
                + lexical_coverage * 0.22
                + title_overlap * 0.12
                + base_score * 0.14
                + lexical_score * 0.08
                + vector_score * 0.06
                + source_weight * 0.02
                + visibility_weight * 0.02
            )
            reranked.append(replace(item, score=rerank_score, rerank_score=rerank_score))

        reranked.sort(key=lambda item: (item.rerank_score, item.score, item.vector_score, item.lexical_score), reverse=True)

        final_hits: list[RAGSearchHit] = []
        seen: set[tuple[str, str]] = set()
        for item in reranked:
            key = (item.document_id, item.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            final_hits.append(item)
            if len(final_hits) >= limit:
                break
        return final_hits

    @staticmethod
    def _token_overlap(left: str, right: str) -> float:
        left_tokens = FeatureReranker._tokenize(left)
        right_tokens = set(FeatureReranker._tokenize(right))
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = sum(1 for token in left_tokens if token in right_tokens)
        return overlap / max(len(set(left_tokens)), 1)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        cleaned = "".join(char.lower() if char.isalnum() else " " for char in text)
        tokens = [token for token in cleaned.split() if token]
        if len(tokens) <= 1:
            return tokens
        phrases = [f"{tokens[index]}_{tokens[index + 1]}" for index in range(len(tokens) - 1)]
        return tokens + phrases

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(x * y for x, y in zip(left, right, strict=False))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
