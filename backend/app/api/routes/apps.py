from __future__ import annotations

from fastapi import APIRouter

from app.platform.apps.registry import get_app_registry


router = APIRouter()


@router.get("")
def list_apps() -> list[dict[str, object]]:
    registry = get_app_registry()
    return [manifest.to_public_dict() for manifest in registry.list_apps()]
