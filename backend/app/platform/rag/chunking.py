from __future__ import annotations

import re

from app.platform.rag.document import Document, DocumentChunk, ParsedDocument, ParsedSegment


class StructuredChunker:
    def __init__(self, *, chunk_size: int = 800, chunk_overlap: int = 120) -> None:
        self.chunk_size = max(200, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))

    def chunk(self, document: Document, parsed: ParsedDocument) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        chunk_index = 1
        segments = parsed.segments or [ParsedSegment(order=1, content=parsed.text, page_or_section="section 1")]
        for segment in segments:
            for content in self._chunk_segment(segment.content):
                preview = self._build_preview(content)
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{document.document_id}::chunk::{chunk_index}",
                        document_id=document.document_id,
                        kb_id=document.kb_id,
                        chunk_index=chunk_index,
                        title=document.title,
                        content=content,
                        preview=preview,
                        page_or_section=segment.page_or_section,
                        metadata={
                            **document.metadata,
                            **segment.metadata,
                            "visibility": document.visibility,
                            "source_type": document.source_type,
                            "tenant_id": document.tenant_id,
                            "user_id": document.user_id,
                            "app_id": document.app_id,
                            "agent_id": document.agent_id,
                            "session_id": document.session_id,
                            "owner_id": document.owner_id,
                            "is_temporary": document.is_temporary,
                            "kb_id": document.kb_id,
                            "document_title": document.title,
                        },
                    )
                )
                chunk_index += 1
        return chunks

    def _chunk_segment(self, text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs or [normalized]:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= self.chunk_size:
                current = candidate
                continue
            if current:
                chunks.append(current.strip())
            current = paragraph
            while len(current) > self.chunk_size:
                window = current[: self.chunk_size]
                split_at = max(window.rfind("\n"), window.rfind(" "), self.chunk_size - self.chunk_overlap)
                split_at = max(80, split_at)
                piece = current[:split_at].strip()
                if piece:
                    chunks.append(piece)
                overlap_start = max(0, split_at - self.chunk_overlap)
                current = current[overlap_start:].strip()
        if current.strip():
            chunks.append(current.strip())
        return chunks

    @staticmethod
    def _build_preview(content: str, limit: int = 240) -> str:
        flattened = re.sub(r"\s+", " ", content).strip()
        if len(flattened) <= limit:
            return flattened
        return f"{flattened[: limit - 1].rstrip()}…"
