from __future__ import annotations

import mimetypes
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from app.platform.rag.document import ParsedDocument, ParsedSegment


class DocumentParser:
    def parse_text(self, *, text: str, metadata: dict[str, object] | None = None) -> ParsedDocument:
        normalized = self._normalize_text(text)
        return ParsedDocument(
            text=normalized,
            segments=self._split_segments(normalized),
            metadata=dict(metadata or {}),
        )

    def parse_file(self, path: Path, *, metadata: dict[str, object] | None = None) -> ParsedDocument:
        suffix = path.suffix.lower()
        mime_type, _ = mimetypes.guess_type(path.name)
        base_metadata = dict(metadata or {})
        if mime_type:
            base_metadata.setdefault("mime_type", mime_type)
        if suffix in {".txt", ".md"}:
            return self.parse_text(text=path.read_text(encoding="utf-8"), metadata=base_metadata)
        if suffix == ".pdf":
            return self._parse_pdf(path, metadata=base_metadata)
        if suffix == ".docx":
            return self._parse_docx(path, metadata=base_metadata)
        raise ValueError(f"Unsupported document format: {suffix}")

    def _parse_pdf(self, path: Path, *, metadata: dict[str, object]) -> ParsedDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF ingestion requires pypdf. Install backend dependencies first.") from exc
        reader = PdfReader(str(path))
        segments: list[ParsedSegment] = []
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            content = self._normalize_text(page.extract_text() or "")
            if not content:
                continue
            pages.append(content)
            segments.append(
                ParsedSegment(
                    order=index,
                    content=content,
                    page_or_section=f"page {index}",
                    metadata={"page": index},
                )
            )
        return ParsedDocument(text="\n\n".join(pages), segments=segments, metadata=metadata)

    def _parse_docx(self, path: Path, *, metadata: dict[str, object]) -> ParsedDocument:
        paragraphs = self._extract_docx_paragraphs(path)
        text = self._normalize_text("\n".join(paragraphs))
        return ParsedDocument(text=text, segments=self._split_segments(text), metadata=metadata)

    def _extract_docx_paragraphs(self, path: Path) -> list[str]:
        paragraphs: list[str] = []
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for paragraph in root.findall(".//w:p", namespaces):
            runs = [node.text or "" for node in paragraph.findall(".//w:t", namespaces)]
            joined = self._normalize_text("".join(runs))
            if joined:
                paragraphs.append(joined)
        return paragraphs

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\x00", " ").strip()
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized

    def _split_segments(self, text: str) -> list[ParsedSegment]:
        if not text.strip():
            return []
        lines = text.splitlines()
        segments: list[ParsedSegment] = []
        buffer: list[str] = []
        current_label = "section 1"
        order = 1

        def flush() -> None:
            nonlocal order
            content = "\n".join(buffer).strip()
            if not content:
                return
            segments.append(
                ParsedSegment(
                    order=order,
                    content=content,
                    page_or_section=current_label,
                    metadata={"section": current_label},
                )
            )
            order += 1

        for line in lines:
            stripped = line.strip()
            if self._looks_like_heading(stripped):
                flush()
                buffer = [stripped]
                current_label = stripped[:120]
                continue
            if not stripped and buffer and buffer[-1] == "":
                continue
            buffer.append(stripped)
        flush()
        return segments or [ParsedSegment(order=1, content=text.strip(), page_or_section="section 1")]

    @staticmethod
    def _looks_like_heading(text: str) -> bool:
        if not text:
            return False
        if text.startswith("#"):
            return True
        if len(text) <= 80 and text.endswith(":"):
            return True
        return bool(re.match(r"^(\d+(\.\d+)*|[A-Z][A-Z\\s]{2,}|第[一二三四五六七八九十百]+[章节部分])", text))
