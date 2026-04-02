from __future__ import annotations

from app.apps.deep_research.models import ResearchState
from app.apps.deep_research.prompts import REPORTER_PROMPT
from app.platform.models.base import BaseModelClient, ModelRequest


class ReportWriter:
    def __init__(self, model_client: BaseModelClient, model_name: str) -> None:
        self.model_client = model_client
        self.model_name = model_name

    def write_report(self, state: ResearchState) -> str:
        summaries = "\n\n".join(f"## {task.title}\n{task.summary}" for task in state.tasks)
        prompt = f"{REPORTER_PROMPT}\n\nResearch topic: {state.topic}\n\nTask findings:\n{summaries}"
        return self.write_report_from_prompt(prompt, state=state)

    def write_report_from_prompt(self, prompt: str, *, state: ResearchState) -> str:
        try:
            response = self.model_client.generate(
                ModelRequest(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=900,
                )
            )
            return response.text.strip()
        except Exception:
            return self._fallback_report(state)

    @staticmethod
    def _fallback_report(state: ResearchState) -> str:
        sections = [f"# {state.topic}", "", "## Overview", f"This report covers the topic `{state.topic}` through the tasks below.", ""]
        for task in state.tasks:
            sections.extend([f"## {task.title}", task.summary, ""])
        sections.extend(["## Conclusion", "This is a V1 auto-generated report. Retrieval and citation quality can be improved further."])
        return "\n".join(sections).strip()
