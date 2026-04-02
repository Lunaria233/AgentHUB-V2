from __future__ import annotations

from app.config import Settings
from app.platform.models.base import BaseModelClient
from app.platform.models.openai_compat import OpenAICompatClient


def build_model_client(settings: Settings) -> BaseModelClient:
    provider = settings.llm_provider.strip().lower()
    if provider in {"openai_compat", "openai-compatible", "dashscope", "qwen"}:
        return OpenAICompatClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
