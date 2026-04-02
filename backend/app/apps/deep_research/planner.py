from __future__ import annotations

import json
import re

from app.apps.deep_research.models import ResearchTask
from app.apps.deep_research.prompts import PLANNER_PROMPT
from app.platform.models.base import BaseModelClient, ModelRequest


class ResearchPlanner:
    def __init__(self, model_client: BaseModelClient, model_name: str) -> None:
        self.model_client = model_client
        self.model_name = model_name

    def plan_tasks(self, topic: str) -> list[ResearchTask]:
        prompt = f"{PLANNER_PROMPT}\n\nResearch topic: {topic}"
        return self.plan_tasks_from_prompt(prompt, topic=topic)

    def plan_tasks_from_prompt(self, prompt: str, *, topic: str) -> list[ResearchTask]:
        try:
            response = self.model_client.generate(
                ModelRequest(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=420,
                )
            )
            parsed = self._parse_tasks(response.text)
            if parsed:
                return parsed
        except Exception:
            pass
        return self._fallback_plan(topic)

    def _parse_tasks(self, text: str) -> list[ResearchTask]:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group(0))
        tasks: list[ResearchTask] = []
        for index, item in enumerate(data, start=1):
            tasks.append(
                ResearchTask(
                    task_id=index,
                    title=str(item.get("title", f"Task {index}")),
                    query=str(item.get("query", "")) or str(item.get("title", "")),
                    goal=str(item.get("goal", "")),
                )
            )
        return tasks

    def _fallback_plan(self, topic: str) -> list[ResearchTask]:
        titles = [
            "Background and definition",
            "Current progress and state",
            "Key players and case studies",
            "Challenges and outlook",
        ]
        return [
            ResearchTask(task_id=index, title=title, query=f"{topic} {title}", goal=f"Analyze {title.lower()}")
            for index, title in enumerate(titles, start=1)
        ]
