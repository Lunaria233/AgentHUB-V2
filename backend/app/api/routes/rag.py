from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.platform.rag.document import RetrievalQuery
from app.platform.rag.evaluation import RAGEvaluator
from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()

RAG_ANSWER_SYSTEM_PROMPT = (
    "Answer the user's question using only the provided knowledge base evidence. "
    "If the evidence is insufficient, say so. Cite evidence with source tags like [S1], [S2]."
)


class AddTextRequest(BaseModel):
    app_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    user_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    tenant_id: str = "default"
    knowledge_target: str = Field(default="session_temporary")
    source_type: str = Field(default="user_text")
    kb_id: str | None = None
    owner_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class URLImportRequest(BaseModel):
    app_id: str = Field(min_length=1)
    url: str = Field(min_length=5)
    title: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    tenant_id: str = "default"
    knowledge_target: str = "session_temporary"
    source_type: str = "url_import"
    kb_id: str | None = None
    owner_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    app_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    user_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    tenant_id: str = "default"
    limit: int = Field(default=5, ge=1, le=20)
    retrieval_mode: str = "hybrid"
    scope_names: list[str] = Field(default_factory=list)
    kb_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    include_public: bool = True
    include_app_shared: bool = True
    include_user_private: bool = True
    include_session_temporary: bool = True
    query_rewrite_enabled: bool = False
    query_rewrite_mode: str = "hybrid"
    mqe_variants: int = 4
    hyde_enabled: bool = False
    hyde_mode: str = "model"
    rerank_enabled: bool = False
    rerank_strategy: str = "feature"
    rerank_top_n: int = 12


class AnswerRequest(SearchRequest):
    system_prompt: str = RAG_ANSWER_SYSTEM_PROMPT


class DeleteRequest(BaseModel):
    app_id: str = Field(min_length=1)
    user_id: str | None = None
    session_id: str | None = None


class RebuildRequest(BaseModel):
    app_id: str | None = None
    kb_id: str | None = None


def _to_query(request: SearchRequest) -> RetrievalQuery:
    return RetrievalQuery(
        query=request.query,
        app_id=request.app_id,
        user_id=request.user_id,
        session_id=request.session_id,
        agent_id=request.agent_id,
        tenant_id=request.tenant_id,
        limit=request.limit,
        retrieval_mode=request.retrieval_mode,
        scope_names=request.scope_names,
        kb_ids=request.kb_ids,
        source_types=request.source_types,
        include_public=request.include_public,
        include_app_shared=request.include_app_shared,
        include_user_private=request.include_user_private,
        include_session_temporary=request.include_session_temporary,
        query_rewrite_enabled=request.query_rewrite_enabled,
        hyde_enabled=request.hyde_enabled,
        rerank_enabled=request.rerank_enabled,
        metadata={
            "query_rewrite_mode": request.query_rewrite_mode,
            "mqe_variants": request.mqe_variants,
            "hyde_mode": request.hyde_mode,
            "rerank_strategy": request.rerank_strategy,
            "rerank_top_n": request.rerank_top_n,
        },
    )


@router.get("/status")
def get_rag_status() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.rag_service.status()


@router.post("/text")
def add_text(request: AddTextRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.rag_service.ingest_text(
        title=request.title,
        text=request.text,
        app_id=request.app_id,
        user_id=request.user_id,
        session_id=request.session_id,
        knowledge_target=request.knowledge_target,
        source_type=request.source_type,
        kb_id=request.kb_id,
        tenant_id=request.tenant_id,
        agent_id=request.agent_id,
        owner_id=request.owner_id,
        metadata=request.metadata,
    )


@router.post("/document")
async def ingest_document(
    app_id: str = Form(...),
    title: str = Form(...),
    knowledge_target: str = Form("session_temporary"),
    source_type: str = Form("user_upload"),
    user_id: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    agent_id: str | None = Form(default=None),
    tenant_id: str = Form(default="default"),
    kb_id: str | None = Form(default=None),
    owner_id: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    suffix = Path(file.filename or "").suffix
    if suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    temp_path = orchestrator.settings.rag_store_path / "incoming" / f"{orchestrator.trace_service.new_trace_id()}{suffix}"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(await file.read())
    try:
        return orchestrator.rag_service.ingest_file(
            title=title,
            file_path=temp_path,
            app_id=app_id,
            user_id=user_id,
            session_id=session_id,
            knowledge_target=knowledge_target,
            source_type=source_type,
            kb_id=kb_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            owner_id=owner_id,
            metadata={"uploaded_file_name": file.filename or temp_path.name},
        )
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/url")
def import_url(request: URLImportRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.rag_service.ingest_url(
        url=request.url,
        app_id=request.app_id,
        user_id=request.user_id,
        session_id=request.session_id,
        knowledge_target=request.knowledge_target,
        source_type=request.source_type,
        document_id=None,
        kb_id=request.kb_id,
        tenant_id=request.tenant_id,
        agent_id=request.agent_id,
        owner_id=request.owner_id,
        metadata=request.metadata,
    )


@router.get("/documents")
def list_documents(
    app_id: str = Query(...),
    user_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    visibility: list[str] = Query(default_factory=list),
    source_types: list[str] = Query(default_factory=list),
    kb_ids: list[str] = Query(default_factory=list),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    records = orchestrator.rag_service.list_documents(
        app_id=app_id,
        user_id=user_id,
        session_id=session_id,
        visibility=visibility or None,
        source_types=source_types or None,
        kb_ids=kb_ids or None,
        limit=limit,
    )
    return {"documents": [asdict(record) for record in records]}


@router.post("/search")
def search(request: SearchRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    result = orchestrator.rag_service.search(_to_query(request))
    return {
        "query": result.query,
        "mode": result.mode,
        "sources": [asdict(source) for source in result.sources],
        "items": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "title": item.title,
                "page_or_section": item.page_or_section,
                "score": item.score,
                "lexical_score": item.lexical_score,
                "vector_score": item.vector_score,
                "rerank_score": item.rerank_score,
                "preview": item.preview,
                "visibility": item.visibility,
                "source_type": item.source_type,
                "kb_id": item.kb_id,
                "source_uri": item.source_uri,
            }
            for item in result.items
        ],
        "debug": result.debug,
    }


@router.post("/answer")
def answer_with_sources(request: AnswerRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    answer = orchestrator.rag_service.answer_with_sources(
        query=_to_query(request),
        context_builder=orchestrator.build_context_builder(request.app_id),
        system_prompt=request.system_prompt,
    )
    return {
        "answer": answer.answer,
        "sources": [asdict(source) for source in answer.sources],
        "fallback_used": answer.fallback_used,
        "debug": answer.retrieval.debug,
    }


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, request: DeleteRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    deleted = orchestrator.rag_service.delete_document(
        document_id=document_id,
        app_id=request.app_id,
        user_id=request.user_id,
        session_id=request.session_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found or not deletable")
    return {"deleted": True, "document_id": document_id}


@router.post("/rebuild")
def rebuild_index(request: RebuildRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.rag_service.rebuild_index(app_id=request.app_id, kb_id=request.kb_id)


@router.get("/scopes")
def list_scopes(
    app_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    scopes = orchestrator.rag_service.list_knowledge_scopes(app_id=app_id, user_id=user_id, session_id=session_id)
    return {"scopes": [asdict(scope) for scope in scopes]}


@router.post("/eval")
def run_rag_eval(app_id: str = Query(default="chat")) -> dict[str, object]:
    orchestrator = get_orchestrator()
    summary = RAGEvaluator(
        settings=orchestrator.settings,
        embedder=orchestrator.rag_embedder,
        model_client=orchestrator.model_client,
        trace_service=orchestrator.trace_service,
    ).run(app_id=app_id)
    return asdict(summary)
