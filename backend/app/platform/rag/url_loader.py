from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.platform.rag.document import ParsedDocument, ParsedSegment


@dataclass(slots=True)
class FetchedURLDocument:
    url: str
    title: str
    text: str
    metadata: dict[str, Any]
    parsed: ParsedDocument


class URLDocumentLoader:
    def __init__(self, *, parser, timeout_seconds: float = 20.0) -> None:
        self.parser = parser
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> FetchedURLDocument:
        try:
            response = self._request(url, verify=True)
        except httpx.ConnectError:
            response = self._request(url, verify=False)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        metadata = {
            "source_url": str(response.url),
            "content_type": content_type,
            "status_code": response.status_code,
        }
        if "pdf" in content_type:
            return self._load_remote_pdf(response.content, url=str(response.url), metadata=metadata)
        if "text/plain" in content_type or "markdown" in content_type:
            text = response.text
            parsed = self.parser.parse_text(text=text, metadata=metadata)
            title = self._title_from_url(str(response.url))
            return FetchedURLDocument(url=str(response.url), title=title, text=text, metadata=metadata, parsed=parsed)
        return self._load_html(response.text, url=str(response.url), metadata=metadata)

    def _load_remote_pdf(self, content: bytes, *, url: str, metadata: dict[str, Any]) -> FetchedURLDocument:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            parsed = self.parser.parse_file(temp_path, metadata=metadata)
        finally:
            temp_path.unlink(missing_ok=True)
        title = str(parsed.metadata.get("title") or self._title_from_url(url))
        return FetchedURLDocument(url=url, title=title, text=parsed.text, metadata={**metadata, **parsed.metadata}, parsed=parsed)

    def _load_html(self, html: str, *, url: str, metadata: dict[str, Any]) -> FetchedURLDocument:
        soup = BeautifulSoup(html, "html.parser")
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        title = (soup.title.string.strip() if soup.title and soup.title.string else self._title_from_url(url))
        description = ""
        description_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.IGNORECASE)})
        if description_tag and description_tag.get("content"):
            description = str(description_tag.get("content")).strip()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        segments: list[ParsedSegment] = []
        buffer: list[str] = []
        current_section = title
        order = 0
        for element in main.find_all(["h1", "h2", "h3", "h4", "p", "li"], recursive=True):
            text = element.get_text(" ", strip=True)
            if not text:
                continue
            if element.name.startswith("h"):
                if buffer:
                    order += 1
                    content = "\n".join(buffer).strip()
                    if content:
                        segments.append(ParsedSegment(order=order, content=content, page_or_section=current_section))
                    buffer = []
                current_section = text
                continue
            buffer.append(text)
        if buffer:
            order += 1
            content = "\n".join(buffer).strip()
            if content:
                segments.append(ParsedSegment(order=order, content=content, page_or_section=current_section))
        text = "\n\n".join(segment.content for segment in segments).strip()
        if not text:
            text = soup.get_text("\n", strip=True)
        parsed = ParsedDocument(
            text=text,
            segments=segments,
            metadata={
                **metadata,
                "title": title,
                "description": description,
                "host": urlparse(url).netloc,
            },
        )
        return FetchedURLDocument(url=url, title=title, text=text, metadata=parsed.metadata, parsed=parsed)

    def _request(self, url: str, *, verify: bool) -> httpx.Response:
        return httpx.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0 Safari/537.36 AgentPlatformRAG/1.0"
                )
            },
            follow_redirects=True,
            timeout=self.timeout_seconds,
            verify=verify,
        )

    @staticmethod
    def _title_from_url(url: str) -> str:
        path = urlparse(url).path.rstrip("/")
        if not path:
            return urlparse(url).netloc or "Imported URL"
        return path.split("/")[-1] or urlparse(url).netloc or "Imported URL"
