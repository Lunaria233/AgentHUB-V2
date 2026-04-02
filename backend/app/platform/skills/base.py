from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SkillResource:
    title: str
    resource_type: str
    relative_path: str
    absolute_path: str = ""
    content: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SkillStageConfig:
    stage: str
    prompt_fragments: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SkillBundle:
    skill_id: str
    name: str
    description: str
    prompt_fragments: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    stage_configs: dict[str, SkillStageConfig] = field(default_factory=dict)
    references: list[SkillResource] = field(default_factory=list)
    scripts: list[SkillResource] = field(default_factory=list)
    assets: list[SkillResource] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    source_dir: str = ""
    instructions_markdown: str = ""
    hydrated: bool = False

    def get_stage_config(self, stage: str) -> SkillStageConfig | None:
        return self.stage_configs.get(stage) or self.stage_configs.get("default")


@dataclass(slots=True)
class ResolvedSkill:
    skill_id: str
    name: str
    stage: str
    prompt_fragments: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    references: list[SkillResource] = field(default_factory=list)
    scripts: list[SkillResource] = field(default_factory=list)
    assets: list[SkillResource] = field(default_factory=list)
    instructions_markdown: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
