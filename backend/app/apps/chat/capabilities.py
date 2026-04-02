from __future__ import annotations

from app.platform.apps.manifest import AppManifest
from app.platform.context.providers import (
    HistoryContextProvider,
    MemoryContextProvider,
    NotesContextProvider,
    RAGContextProvider,
)
from app.platform.history.service import HistoryService
from app.platform.memory.service import MemoryService
from app.platform.rag.service import RAGService
from app.platform.tools.builtin_note import FileNoteStore


def build_chat_context_providers(
    *,
    manifest: AppManifest,
    history_service: HistoryService,
    memory_service: MemoryService,
    rag_service: RAGService,
    note_store: FileNoteStore,
) -> list[object]:
    providers: list[object] = []
    if manifest.capabilities.history:
        providers.append(HistoryContextProvider(history_service))
    if manifest.capabilities.memory:
        providers.append(MemoryContextProvider(memory_service))
    if manifest.capabilities.rag:
        providers.append(RAGContextProvider(rag_service))
    if manifest.capabilities.notes:
        providers.append(NotesContextProvider(note_store))
    return providers
