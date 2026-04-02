from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    TOOL_RESULT = "tool_result"


@dataclass(slots=True)
class Message:
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_openai_dict(self) -> dict[str, str]:
        if self.role == MessageRole.TOOL_RESULT:
            tool_name = str(self.metadata.get("tool_name", "")).strip()
            header = f"[TOOL_RESULT:{tool_name}]" if tool_name else "[TOOL_RESULT]"
            instructions = (
                "Use this tool result to continue the task. "
                "If another tool is needed, emit [TOOL_CALL:tool_name:{...}]. "
                "Otherwise, answer the user directly."
            )
            return {
                "role": MessageRole.USER.value,
                "content": f"{header}\n{self.content}\n\n{instructions}",
            }
        return {"role": self.role.value, "content": self.content}

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_openai_dict(cls, payload: dict[str, Any]) -> "Message":
        return cls(
            role=MessageRole(payload["role"]),
            content=str(payload.get("content", "")),
            metadata={},
        )
