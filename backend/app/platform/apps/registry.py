from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from app.apps.chat.manifest import CHAT_APP_MANIFEST
from app.apps.deep_research.manifest import DEEP_RESEARCH_APP_MANIFEST
from app.config import get_settings
from app.platform.apps.manifest import AppManifest


class AppRegistry:
    def __init__(self) -> None:
        self._apps: dict[str, AppManifest] = {}

    def register(self, manifest: AppManifest) -> None:
        self._apps[manifest.app_id] = manifest

    def get(self, app_id: str) -> AppManifest:
        return self._apps[app_id]

    def list_apps(self) -> list[AppManifest]:
        return list(self._apps.values())


@lru_cache(maxsize=1)
def get_app_registry() -> AppRegistry:
    settings = get_settings()
    registry = AppRegistry()
    for manifest in [CHAT_APP_MANIFEST, DEEP_RESEARCH_APP_MANIFEST]:
        app_config = settings.get_app_config(manifest.app_id)
        if not app_config.enabled:
            continue
        capability_updates = {
            key: value
            for key, value in app_config.capabilities.items()
            if hasattr(manifest.capabilities, key)
        }
        capabilities = replace(manifest.capabilities, **capability_updates)
        permissions = replace(
            manifest.permissions,
            allowed_tools=app_config.allowed_tools or manifest.permissions.allowed_tools,
            allowed_mcp_servers=app_config.allowed_mcp_servers or manifest.permissions.allowed_mcp_servers,
            knowledge_scopes=app_config.knowledge_scopes or manifest.permissions.knowledge_scopes,
        )
        registry.register(replace(manifest, capabilities=capabilities, permissions=permissions))
    return registry
