from __future__ import annotations

from pathlib import Path

from app.apps.software_engineering.archive import SERunStore
from app.apps.software_engineering.runtime import SoftwareEngineeringRuntime
from app.platform.apps.profiles import SkillBinding
from app.platform.runtime.factory import BaseRuntimeFactory, RuntimeBuildContext


class SoftwareEngineeringRuntimeFactory(BaseRuntimeFactory):
    @property
    def factory_id(self) -> str:
        return "software_engineering"

    def create(self, build_context: RuntimeBuildContext) -> SoftwareEngineeringRuntime:
        app_config = build_context.settings.get_app_config(build_context.manifest.app_id)
        return SoftwareEngineeringRuntime(
            app_id=build_context.manifest.app_id,
            session_id=build_context.session_id,
            user_id=build_context.user_id,
            model_client=build_context.model_client,
            model_name=build_context.model_name,
            history_service=build_context.history_service,
            memory_service=build_context.memory_service,
            rag_service=build_context.rag_service,
            context_builder=build_context.context_builder,
            tool_registry=build_context.tool_registry,
            tool_executor=build_context.tool_executor,
            trace_service=build_context.trace_service,
            context_profiles=build_context.manifest.profiles.context_profiles,
            memory_profile=build_context.manifest.profiles.memory_profile,
            rag_profile=build_context.manifest.profiles.rag_profile,
            skill_runtime=build_context.skill_runtime,
            skill_bindings=list(build_context.manifest.profiles.skills or []),
            run_store=build_context.dependencies["se_run_store"],
            repo_root=Path(build_context.dependencies.get("repo_root", ".")),
            default_max_iterations=max(2, app_config.tool_iterations or build_context.settings.default_tool_iterations + 2),
        )


def default_skill_bindings() -> list[SkillBinding]:
    return [
        SkillBinding(skill_id="requirement_to_plan", stage="se.plan", priority=100),
        SkillBinding(skill_id="tool_use_hygiene", stage="se.retrieve", priority=110),
        SkillBinding(skill_id="source_grounding", stage="se.retrieve", priority=120),
        SkillBinding(skill_id="patch_summary", stage="se.code", priority=120),
        SkillBinding(skill_id="tool_use_hygiene", stage="se.code", priority=130),
        SkillBinding(skill_id="error_summary", stage="se.diagnose", priority=120),
        SkillBinding(skill_id="final_report", stage="se.report", priority=140),
        SkillBinding(skill_id="source_grounding", stage="se.report", priority=150),
    ]
