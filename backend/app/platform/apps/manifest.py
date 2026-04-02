from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.platform.apps.profiles import AppCapabilityProfiles


@dataclass(slots=True)
class CapabilityFlags:
    history: bool = True
    memory: bool = False
    rag: bool = False
    mcp: bool = False
    skills: bool = False
    notes: bool = False
    streaming: bool = True
    workflow: bool = False


@dataclass(slots=True)
class AppPermissionProfile:
    allowed_tools: list[str] = field(default_factory=list)
    allowed_mcp_servers: list[str] = field(default_factory=list)
    knowledge_scopes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppManifest:
    app_id: str
    name: str
    description: str
    runtime_kind: str
    runtime_factory: str
    capabilities: CapabilityFlags
    permissions: AppPermissionProfile
    profiles: AppCapabilityProfiles = field(default_factory=AppCapabilityProfiles)
    tags: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, object]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "description": self.description,
            "runtime_kind": self.runtime_kind,
            "runtime_factory": self.runtime_factory,
            "capabilities": asdict(self.capabilities),
            "tags": self.tags,
        }
