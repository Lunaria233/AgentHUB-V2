from __future__ import annotations

from dataclasses import dataclass

from app.platform.capabilities.contracts import BaseCapabilityContext
from app.platform.skills.registry import SkillRegistry
from app.platform.skills.runtime import PlatformSkillRuntime


@dataclass(slots=True)
class SkillEvalCase:
    case_id: str
    app_id: str
    stage: str
    expected_skill_ids: list[str]


class SkillEvaluator:
    def __init__(self, registry: SkillRegistry, runtime: PlatformSkillRuntime, orchestrator) -> None:
        self.registry = registry
        self.runtime = runtime
        self.orchestrator = orchestrator

    def evaluate(self) -> dict[str, object]:
        cases = [
            SkillEvalCase(case_id="chat.reply", app_id="chat", stage="chat.reply", expected_skill_ids=["general_qa", "tool_use_hygiene", "source_grounding"]),
            SkillEvalCase(case_id="research.plan", app_id="deep_research", stage="research.plan", expected_skill_ids=["research_planning"]),
            SkillEvalCase(case_id="research.summarize", app_id="deep_research", stage="research.summarize", expected_skill_ids=["source_grounding", "research_synthesis"]),
            SkillEvalCase(case_id="research.report", app_id="deep_research", stage="research.report", expected_skill_ids=["source_grounding", "research_synthesis"]),
        ]
        case_results: list[dict[str, object]] = []
        precision_sum = 0.0
        recall_sum = 0.0
        reference_coverage_sum = 0.0
        resource_inventory_sum = 0.0

        catalog = self.registry.list_skills()
        for case in cases:
            manifest = self.orchestrator.app_registry.get(case.app_id)
            tool_registry = self.orchestrator.build_tool_registry(case.app_id)
            resolved = self.runtime.resolve(
                BaseCapabilityContext(app_id=case.app_id, session_id="skills-eval", user_id="eval-user", stage=case.stage),
                bindings=manifest.profiles.skills,
                available_tool_names={tool.name for tool in tool_registry.list_tools()},
            )
            actual_ids = [item.skill_id for item in resolved]
            expected = set(case.expected_skill_ids)
            actual = set(actual_ids)
            true_positive = len(expected & actual)
            precision = true_positive / max(1, len(actual))
            recall = true_positive / max(1, len(expected))
            references_total = sum(1 for item in resolved if item.references)
            references_loaded = sum(1 for item in resolved if any(reference.content for reference in item.references))
            resource_inventory_total = sum(len(item.references) + len(item.scripts) + len(item.assets) for item in resolved)
            resource_inventory_counted = sum(
                len([resource for resource in item.references if resource.relative_path])
                + len([resource for resource in item.scripts if resource.relative_path])
                + len([resource for resource in item.assets if resource.relative_path])
                for item in resolved
            )
            precision_sum += precision
            recall_sum += recall
            reference_coverage_sum += references_loaded / max(1, references_total)
            resource_inventory_sum += resource_inventory_counted / max(1, resource_inventory_total)
            case_results.append(
                {
                    "case_id": case.case_id,
                    "expected_skill_ids": case.expected_skill_ids,
                    "resolved_skill_ids": actual_ids,
                    "precision": precision,
                    "recall": recall,
                    "reference_loading_coverage": references_loaded / max(1, references_total),
                    "resource_inventory_coverage": resource_inventory_counted / max(1, resource_inventory_total),
                }
            )
        denominator = max(1, len(cases))
        return {
            "catalog_skill_count": len(catalog),
            "average_precision": precision_sum / denominator,
            "average_recall": recall_sum / denominator,
            "average_reference_loading_coverage": reference_coverage_sum / denominator,
            "average_resource_inventory_coverage": resource_inventory_sum / denominator,
            "cases": case_results,
        }
