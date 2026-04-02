from __future__ import annotations

from pathlib import Path

from app.platform.skills.base import SkillBundle
from app.platform.skills.loader import SkillFileLoader


class SkillRegistry:
    def __init__(self, loader: SkillFileLoader | None = None) -> None:
        self._skills: dict[str, SkillBundle] = {}
        self._loader = loader

    def register(self, skill: SkillBundle) -> None:
        self._skills[skill.skill_id] = skill

    def get(self, skill_id: str) -> SkillBundle | None:
        skill = self._skills.get(skill_id)
        if skill is None:
            return None
        if not skill.hydrated and self._loader and skill.source_dir:
            hydrated = self._loader.hydrate(skill.skill_id, skill.source_dir)
            self._skills[skill_id] = hydrated
            return hydrated
        return skill

    def list_skills(self) -> list[SkillBundle]:
        return sorted(self._skills.values(), key=lambda item: item.skill_id)

    def scan(self) -> None:
        if self._loader is None:
            return
        for skill in self._loader.scan_metadata():
            self.register(skill)
