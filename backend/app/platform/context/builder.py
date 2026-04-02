from __future__ import annotations

from collections import defaultdict
import hashlib

from app.platform.context.providers import BaseContextProvider
from app.platform.context.registry import ContextProviderRegistry
from app.platform.context.types import ContextBuildRequest, ContextBuildResult, ContextPacket, ContextSection


SOURCE_TITLES = {
    "search": "Web Search Results",
    "task_summary": "Task Summaries",
    "rag": "Knowledge Base",
    "memory": "Memory",
    "notes": "Working Notes",
    "history": "Conversation History",
}

SOURCE_ORDER = {
    "search": 0,
    "task_summary": 1,
    "rag": 2,
    "memory": 3,
    "notes": 4,
    "history": 5,
}


class ContextBuilder:
    def __init__(
        self,
        providers: list[BaseContextProvider] | None = None,
        provider_registry: ContextProviderRegistry | None = None,
    ) -> None:
        if provider_registry is not None:
            self.provider_registry = provider_registry
        else:
            self.provider_registry = ContextProviderRegistry()
            for provider in providers or []:
                self.provider_registry.register(provider)

    def build(self, request: ContextBuildRequest) -> ContextBuildResult:
        packets = self._gather(request)
        selected, selection_diagnostics = self._select(packets, request)
        compressed, compression_diagnostics = self._compress(selected, request)
        sections = self._structure(request, compressed)
        prompt = self._render_prompt(sections)
        diagnostics = {
            "profile": request.profile,
            "max_tokens": request.max_tokens,
            "provider_order": list(request.provider_order),
            "knowledge_scopes": list(request.knowledge_scopes),
            "source_budgets": self._resolve_source_budgets(request),
            "gathered_count": len(packets),
            "selected_count": len(selected),
            "compressed_count": len(compressed),
            "selected_tokens": sum(packet.token_count for packet in selected),
            "compressed_tokens": sum(packet.token_count for packet in compressed),
            "sections": [section.title for section in sections],
            "selection": selection_diagnostics,
            "compression": compression_diagnostics,
            "sources": self._summarize_sources(
                gathered=packets,
                selected=selected,
                compressed=compressed,
            ),
        }
        return ContextBuildResult(sections=sections, packets=compressed, prompt=prompt, diagnostics=diagnostics)

    def _gather(self, request: ContextBuildRequest) -> list[ContextPacket]:
        packets: list[ContextPacket] = list(request.inline_packets)
        for provider in self.provider_registry.resolve(request.provider_order):
            packets.extend(provider.collect(request))
        return packets

    def _select(self, packets: list[ContextPacket], request: ContextBuildRequest) -> tuple[list[ContextPacket], dict[str, object]]:
        max_tokens = request.max_tokens
        budgets = self._resolve_source_budgets(request)
        original_count = len(packets)
        packets = self._dedupe_packets(packets)
        grouped: dict[str, list[ContextPacket]] = defaultdict(list)
        for packet in packets:
            grouped[self._source_name(packet)].append(packet)

        selected: list[ContextPacket] = []
        total_tokens = 0
        source_spent: dict[str, int] = defaultdict(int)

        for source in budgets:
            source_packets = sorted(grouped.pop(source, []), key=lambda item: item.relevance_score, reverse=True)
            source_budget = max(0, int(max_tokens * budgets[source]))
            for packet in source_packets:
                if source_spent[source] + packet.token_count > source_budget:
                    continue
                if total_tokens + packet.token_count > max_tokens:
                    continue
                selected.append(packet)
                source_spent[source] += packet.token_count
                total_tokens += packet.token_count

        leftovers = [
            packet
            for source_packets in grouped.values()
            for packet in source_packets
        ]
        leftovers.extend(
            packet
            for source in budgets
            for packet in sorted(grouped.get(source, []), key=lambda item: item.relevance_score, reverse=True)
        )
        leftovers = self._dedupe_packets(leftovers)
        for packet in sorted(leftovers, key=lambda item: item.relevance_score, reverse=True):
            if total_tokens + packet.token_count > max_tokens:
                continue
            selected.append(packet)
            total_tokens += packet.token_count
        sorted_selected = sorted(
            selected,
            key=lambda item: (
                SOURCE_ORDER.get(self._source_name(item), 99),
                item.timestamp if self._source_name(item) == "history" else -item.relevance_score,
            ),
        )
        diagnostics = {
            "input_count": original_count,
            "deduped_count": len(packets),
            "dropped_by_dedupe": max(0, original_count - len(packets)),
            "selected_count": len(sorted_selected),
            "selected_tokens": total_tokens,
            "source_spent_tokens": dict(source_spent),
        }
        return sorted_selected, diagnostics

    def _structure(self, request: ContextBuildRequest, packets: list[ContextPacket]) -> list[ContextSection]:
        sections: list[ContextSection] = []
        if request.system_prompt.strip():
            sections.append(ContextSection(title="Role & Policies", content=request.system_prompt.strip()))
        if request.user_input.strip():
            sections.append(ContextSection(title="Task", content=request.user_input.strip()))

        grouped_packets: dict[str, list[ContextPacket]] = defaultdict(list)
        for packet in packets:
            source = str(packet.metadata.get("source", "context")).lower()
            grouped_packets[source].append(packet)

        for source, items in sorted(grouped_packets.items(), key=lambda item: (SOURCE_ORDER.get(item[0], 99), item[0])):
            title = SOURCE_TITLES.get(source, f"Additional Context: {source}")
            content = self._render_source_block(source, items).strip()
            if content:
                sections.append(ContextSection(title=title, content=content))
        return sections

    def _compress(self, packets: list[ContextPacket], request: ContextBuildRequest) -> tuple[list[ContextPacket], dict[str, object]]:
        compact_after = int(request.metadata.get("history_compact_after", 4) or 4)
        compressed: list[ContextPacket] = []
        grouped: dict[str, list[ContextPacket]] = defaultdict(list)
        history_compacted = False
        rag_trimmed = 0
        for packet in packets:
            grouped[self._source_name(packet)].append(packet)

        for source, items in grouped.items():
            if source == "history" and len(items) > compact_after:
                history_compacted = True
                items = sorted(items, key=lambda item: item.timestamp)
                recent = items[-compact_after:]
                earlier = items[:-compact_after]
                summary_lines = [self._trim_packet_content(item.content, 120) for item in earlier[-6:]]
                summary_text = "Earlier conversation summary:\n- " + "\n- ".join(summary_lines)
                compressed.append(
                    ContextPacket(
                        content=summary_text,
                        token_count=self._estimate_tokens(summary_text),
                        relevance_score=max(item.relevance_score for item in earlier),
                        metadata={"source": "history", "compressed": True},
                    )
                )
                compressed.extend(recent)
                continue
            if source == "rag":
                for item in items:
                    trimmed = self._trim_packet_content(item.content, int(request.metadata.get("rag_chunk_char_limit", 420) or 420))
                    if trimmed != item.content.strip():
                        rag_trimmed += 1
                    compressed.append(
                        ContextPacket(
                            content=trimmed,
                            token_count=min(item.token_count, self._estimate_tokens(trimmed)),
                            relevance_score=item.relevance_score,
                            metadata=item.metadata,
                        )
                    )
                continue
            compressed.extend(items)
        diagnostics = {
            "input_count": len(packets),
            "output_count": len(compressed),
            "history_compacted": history_compacted,
            "rag_trimmed_count": rag_trimmed,
        }
        return compressed, diagnostics

    def _render_prompt(self, sections: list[ContextSection]) -> str:
        return "\n\n".join(f"[{section.title}]\n{section.content}" for section in sections)

    def _render_source_block(self, source: str, packets: list[ContextPacket]) -> str:
        if source != "rag":
            return "\n\n".join(packet.content for packet in packets if packet.content.strip())
        lines: list[str] = []
        for index, packet in enumerate(sorted(packets, key=lambda item: item.relevance_score, reverse=True), start=1):
            citation = dict(packet.metadata.get("citation", {}))
            title = str(citation.get("title", "Untitled source"))
            section = str(citation.get("page_or_section", "") or "n/a")
            visibility = str(citation.get("visibility", "unknown"))
            chunk_id = str(citation.get("chunk_id", packet.metadata.get("chunk_id", "")))
            lines.append(
                f"[S{index}] {title}\n"
                f"Chunk: {chunk_id}\n"
                f"Section: {section}\n"
                f"Visibility: {visibility}\n"
                f"{packet.content}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _source_name(packet: ContextPacket) -> str:
        return str(packet.metadata.get("source", "context")).lower()

    def _resolve_source_budgets(self, request: ContextBuildRequest) -> dict[str, float]:
        raw = request.metadata.get("source_budgets")
        if isinstance(raw, dict) and raw:
            total = sum(float(value) for value in raw.values() if float(value) > 0)
            if total > 0:
                return {str(key): float(value) / total for key, value in raw.items() if float(value) > 0}
        profile = request.profile.lower()
        if profile.startswith("chat."):
            return {"history": 0.45, "memory": 0.35, "rag": 0.2}
        if profile == "research.plan":
            return {"memory": 0.15, "rag": 0.15, "notes": 0.1, "history": 0.1}
        if profile == "research.summarize":
            return {"search": 0.45, "memory": 0.15, "rag": 0.15, "notes": 0.1, "history": 0.05}
        if profile == "research.report":
            return {"task_summary": 0.35, "rag": 0.2, "memory": 0.15, "notes": 0.15, "history": 0.05}
        return {"history": 0.35, "memory": 0.25, "rag": 0.2, "notes": 0.1}

    def _dedupe_packets(self, packets: list[ContextPacket]) -> list[ContextPacket]:
        seen: set[str] = set()
        deduped: list[ContextPacket] = []
        for packet in sorted(packets, key=lambda item: item.relevance_score, reverse=True):
            source = self._source_name(packet)
            chunk_id = packet.metadata.get("chunk_id")
            document_id = packet.metadata.get("document_id")
            unique_key = (
                str(chunk_id)
                if chunk_id
                else str(document_id)
                if document_id
                else hashlib.sha1(f"{source}:{packet.content.strip()}".encode("utf-8")).hexdigest()
            )
            if unique_key in seen:
                continue
            seen.add(unique_key)
            deduped.append(packet)
        return deduped

    def _summarize_sources(
        self,
        *,
        gathered: list[ContextPacket],
        selected: list[ContextPacket],
        compressed: list[ContextPacket],
    ) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = {}
        for label, packets in {
            "gathered": gathered,
            "selected": selected,
            "compressed": compressed,
        }.items():
            for packet in packets:
                source = self._source_name(packet)
                source_summary = summary.setdefault(source, {"gathered": 0, "selected": 0, "compressed": 0, "tokens": 0})
                source_summary[label] += 1
                if label == "compressed":
                    source_summary["tokens"] += packet.token_count
        return summary

    @staticmethod
    def _trim_packet_content(content: str, char_limit: int) -> str:
        text = content.strip()
        if len(text) <= char_limit:
            return text
        return text[: max(0, char_limit - 1)].rstrip() + "…"

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text.split()))
