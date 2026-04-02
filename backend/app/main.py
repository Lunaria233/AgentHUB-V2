from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api.routes.apps import router as apps_router
from app.api.routes.chat import router as chat_router
from app.api.routes.context import router as context_router
from app.api.routes.memory import router as memory_router
from app.api.routes.mcp import router as mcp_router
from app.api.routes.rag import router as rag_router
from app.api.routes.research import router as research_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.skills import router as skills_router
from app.config import get_settings


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(apps_router, prefix="/api/apps", tags=["apps"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(context_router, prefix="/api/context", tags=["context"])
app.include_router(memory_router, prefix="/api/memory", tags=["memory"])
app.include_router(mcp_router, prefix="/api/mcp", tags=["mcp"])
app.include_router(rag_router, prefix="/api/rag", tags=["rag"])
app.include_router(research_router, prefix="/api/research", tags=["research"])
app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
app.include_router(skills_router, prefix="/api/skills", tags=["skills"])


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
