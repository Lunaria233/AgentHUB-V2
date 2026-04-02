from __future__ import annotations

from dataclasses import asdict

from app.platform.apps.profiles import SkillBinding
from app.platform.capabilities.contracts import BaseCapabilityContext, BaseSkillRuntime
from app.platform.skills.base import ResolvedSkill
from app.platform.skills.registry import SkillRegistry


class PlatformSkillRuntime(BaseSkillRuntime):
    capability_name = "skills"

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def resolve(
        self,
        context: BaseCapabilityContext,
        bindings: list[SkillBinding] | None = None,
        *,
        available_tool_names: set[str] | None = None,
    ) -> list[ResolvedSkill]:
        resolved: list[ResolvedSkill] = []
        selected_bindings = list(bindings or [])
        for binding in sorted(selected_bindings, key=lambda item: item.priority):
            if not binding.enabled:
                continue
            if binding.stage not in {"default", context.stage}:
                continue
            bundle = self.registry.get(binding.skill_id)
            if bundle is None:
                continue
            stage_config = bundle.get_stage_config(context.stage)
            tool_names = list(bundle.tool_names)
            prompt_fragments = list(bundle.prompt_fragments)
            metadata = dict(bundle.metadata)
            if stage_config is not None:
                prompt_fragments.extend(stage_config.prompt_fragments)
                tool_names.extend(stage_config.tool_names)
                metadata.update(stage_config.metadata)
            deduped_tool_names = list(dict.fromkeys(tool_names))
            if available_tool_names is not None:
                deduped_tool_names = [name for name in deduped_tool_names if name in available_tool_names]
            resolved.append(
                ResolvedSkill(
                    skill_id=bundle.skill_id,
                    name=bundle.name,
                    stage=context.stage,
                    prompt_fragments=list(dict.fromkeys(prompt_fragments)),
                    tool_names=deduped_tool_names,
                    references=bundle.references,
                    scripts=bundle.scripts,
                    assets=bundle.assets,
                    instructions_markdown=bundle.instructions_markdown,
                    metadata={**metadata, **binding.metadata},
                )
            )
        return resolved

    def apply(
        self,
        context: BaseCapabilityContext,
        *,
        prompt_fragments: list[str],
        bindings: list[SkillBinding] | None = None,
        available_tool_names: set[str] | None = None,
    ) -> list[str]:
        resolved = self.resolve(context, bindings, available_tool_names=available_tool_names)
        if not resolved:
            return list(prompt_fragments)
        combined_fragments = list(prompt_fragments)
        combined_fragments.append(self._render_skills_block(resolved))
        return [fragment for fragment in combined_fragments if fragment and fragment.strip()]

    @staticmethod
    def _render_skills_block(resolved: list[ResolvedSkill]) -> str:
        lines = ["[Active Skills]"]
        for item in resolved:
            lines.append(f"- {item.name} ({item.skill_id})")
            for fragment in item.prompt_fragments:
                lines.append(f"  - {fragment}")
            if item.tool_names:
                lines.append(f"  - Preferred tools: {', '.join(item.tool_names)}")
            if item.references:
                refs = ", ".join(reference.title for reference in item.references)
                lines.append(f"  - References: {refs}")
            if item.scripts:
                lines.append(f"  - Scripts: {', '.join(resource.title for resource in item.scripts)}")
            if item.assets:
                lines.append(f"  - Assets: {', '.join(resource.title for resource in item.assets)}")
        return "\n".join(lines)

    def describe(
        self,
        context: BaseCapabilityContext,
        bindings: list[SkillBinding] | None = None,
        *,
        available_tool_names: set[str] | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "skill_id": item.skill_id,
                "name": item.name,
                "stage": item.stage,
                "tool_names": item.tool_names,
                "references": [asdict(reference) for reference in item.references],
                "scripts": [asdict(script) for script in item.scripts],
                "assets": [asdict(asset) for asset in item.assets],
                "instructions_markdown": item.instructions_markdown,
                "prompt_fragments": item.prompt_fragments,
                "metadata": item.metadata,
            }
            for item in self.resolve(context, bindings, available_tool_names=available_tool_names)
        ]
