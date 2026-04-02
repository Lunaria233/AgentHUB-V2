from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MemorySchema:
    schema_id: str
    description: str
    durable_tags: list[str] = field(default_factory=list)
    relation_hints: dict[str, str] = field(default_factory=dict)
    preferred_memory_types: list[str] = field(default_factory=list)


class MemorySchemaRegistry:
    def __init__(self) -> None:
        self._schemas = {
            "default": MemorySchema(
                schema_id="default",
                description="General agent memory schema.",
                durable_tags=["preference", "identity", "constraint", "fact"],
            ),
            "chat_user_profile": MemorySchema(
                schema_id="chat_user_profile",
                description="User-profile memory for the universal chat agent.",
                durable_tags=["preference", "identity", "constraint", "ongoing_goal"],
                relation_hints={"prefers": "user preference graph", "constraint": "user constraint graph"},
                preferred_memory_types=["semantic", "episodic", "working", "perceptual"],
            ),
            "research_workflow": MemorySchema(
                schema_id="research_workflow",
                description="Workflow memory for multi-step research tasks.",
                durable_tags=["research_topic", "task_observation", "task_result", "report_conclusion", "source_claim"],
                relation_hints={"supports": "claim support graph", "contradicts": "claim conflict graph"},
                preferred_memory_types=["semantic", "episodic", "working"],
            ),
            "travel_planner": MemorySchema(
                schema_id="travel_planner",
                description="Travel-oriented memory schema with destination and preference tracking.",
                durable_tags=["destination", "budget", "date", "companion", "hotel_preference", "transit_preference"],
                relation_hints={"travels_to": "destination graph", "prefers": "travel preference graph"},
                preferred_memory_types=["semantic", "episodic", "working", "perceptual"],
            ),
        }

    def get(self, schema_id: str | None) -> MemorySchema:
        if schema_id and schema_id in self._schemas:
            return self._schemas[schema_id]
        return self._schemas["default"]
