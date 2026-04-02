from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

import httpx

from app.platform.tools.base import BaseTool, ToolContext, ToolParameter


class BuiltinSearchTool(BaseTool):
    def __init__(
        self,
        *,
        provider: str = "duckduckgo",
        default_max_results: int = 5,
        provider_base_url: str = "",
        provider_api_key: str = "",
        fallback_provider: str = "duckduckgo",
        searxng_url: str = "",
    ) -> None:
        self.provider = provider
        self.default_max_results = default_max_results
        self.provider_base_url = provider_base_url
        self.provider_api_key = provider_api_key
        self.fallback_provider = fallback_provider
        self.searxng_url = searxng_url

    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return "Search current web information using a configured web search provider."

    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="query", description="Search query"),
            ToolParameter(name="max_results", description="Maximum result count", required=False, param_type="integer"),
        ]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        _ = context
        query = str(arguments.get("query", "")).strip()
        max_results = int(arguments.get("max_results", self.default_max_results))
        if not query:
            return {"ok": False, "error": "query is required"}

        if self.provider == "tavily":
            tavily_result = self._run_tavily(query=query, max_results=max_results)
            if tavily_result.get("ok"):
                return tavily_result
            duckduckgo_result = self._run_duckduckgo(query=query, max_results=max_results)
            if duckduckgo_result.get("ok"):
                duckduckgo_result["warning"] = tavily_result.get("error", "tavily search failed")
                duckduckgo_result["fallback_from"] = "tavily"
                return duckduckgo_result
            return tavily_result

        if self.provider != "duckduckgo":
            return self._run_duckduckgo(query=query, max_results=max_results)

        return self._run_duckduckgo(query=query, max_results=max_results)

    def _run_tavily(self, *, query: str, max_results: int) -> dict[str, Any]:
        if not self.provider_api_key:
            return {"ok": False, "provider": "tavily", "error": "TAVILY_API_KEY is not configured"}

        base_url = (self.provider_base_url or "https://api.tavily.com").rstrip("/")
        payload: dict[str, Any] = {
            "query": query,
            "topic": "general",
            "search_depth": "basic",
            "include_answer": "basic",
            "include_raw_content": False,
            "max_results": max_results,
        }
        headers = {
            "Authorization": f"Bearer {self.provider_api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(f"{base_url}/search", headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return {"ok": False, "provider": "tavily", "error": f"tavily search failed: {exc}"}

        try:
            data = response.json()
        except ValueError as exc:
            return {"ok": False, "provider": "tavily", "error": f"invalid tavily response: {exc}"}

        normalized: list[dict[str, str | float]] = []
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "title": str(item.get("title", query) or query),
                    "url": str(item.get("url", "") or ""),
                    "snippet": str(item.get("content", "") or ""),
                    "score": float(item.get("score", 0.0) or 0.0),
                }
            )
            if len(normalized) >= max_results:
                break
        return {
            "ok": True,
            "provider": "tavily",
            "query": str(data.get("query", query) or query),
            "answer": str(data.get("answer", "") or ""),
            "results": normalized,
            "response_time": data.get("response_time"),
        }

    def _run_duckduckgo(self, *, query: str, max_results: int) -> dict[str, Any]:
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
            {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
        )
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"search failed: {exc}"}

        results: list[dict[str, str]] = []
        abstract = str(data.get("AbstractText", "") or "")
        if abstract:
            results.append(
                {
                    "title": str(data.get("Heading", query) or query),
                    "url": str(data.get("AbstractURL", "") or ""),
                    "snippet": abstract,
                }
            )
        for item in data.get("RelatedTopics", []):
            if isinstance(item, dict) and "Text" in item:
                results.append(
                    {
                        "title": str(item.get("Text", query)).split(" - ")[0],
                        "url": str(item.get("FirstURL", "") or ""),
                        "snippet": str(item.get("Text", "") or ""),
                    }
                )
            if len(results) >= max_results:
                break
        return {"ok": True, "provider": "duckduckgo", "query": query, "results": results[:max_results]}
