from __future__ import annotations

import json

from app.apps.deep_research.models import ResearchTask
from app.apps.deep_research.prompts import SUMMARIZER_PROMPT
from app.platform.models.base import BaseModelClient, ModelRequest


class TaskSummarizer:
    def __init__(self, model_client: BaseModelClient, model_name: str) -> None:
        self.model_client = model_client
        self.model_name = model_name

    def summarize_task(self, topic: str, task: ResearchTask) -> str:
        sources_blob = json.dumps(task.sources, ensure_ascii=False, indent=2)
        prompt = (
            f"{SUMMARIZER_PROMPT}\n\n"
            f"Research topic: {topic}\n"
            f"Task title: {task.title}\n"
            f"Task goal: {task.goal}\n"
            f"Search evidence:\n{sources_blob}"
        )
        return self.summarize_from_prompt(prompt, task=task)

    def summarize_from_prompt(self, prompt: str, *, task: ResearchTask) -> str:
        try:
            response = self.model_client.generate(
                ModelRequest(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=420,
                )
            )
            return response.text.strip()
        except Exception:
            return self._fallback_summary(task)

    @staticmethod
    def _fallback_summary(task: ResearchTask) -> str:
        if not task.sources:
            return f"{task.title}: not enough evidence was retrieved yet, so this task needs more sources."
        snippets = "\n".join(f"- {item.get('title', '')}: {item.get('snippet', '')}" for item in task.sources[:3])
        return f"{task.title}\n\nBased on the initial search, the following signals were found:\n{snippets}"
