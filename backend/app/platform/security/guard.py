from __future__ import annotations

from app.platform.core.errors import PermissionDeniedError
from app.platform.security.policy import SecurityPolicy


class PermissionGuard:
    def __init__(self, policy: SecurityPolicy) -> None:
        self.policy = policy

    def check_tool_allowed(self, tool_name: str) -> None:
        allowed = self.policy.tool_permission.allowed_tools
        if allowed and tool_name not in allowed:
            raise PermissionDeniedError(f"Tool '{tool_name}' is not allowed")

    def check_knowledge_allowed(self, scope: str) -> None:
        allowed = self.policy.knowledge_scope.allowed_scopes
        if allowed and scope not in allowed:
            raise PermissionDeniedError(f"Knowledge scope '{scope}' is not allowed")
