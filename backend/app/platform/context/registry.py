from __future__ import annotations

from app.platform.context.providers import BaseContextProvider


class ContextProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseContextProvider] = {}

    def register(self, provider: BaseContextProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> BaseContextProvider | None:
        return self._providers.get(provider_id)

    def list_provider_ids(self) -> list[str]:
        return list(self._providers.keys())

    def resolve(self, provider_order: list[str] | None = None) -> list[BaseContextProvider]:
        if not provider_order:
            return list(self._providers.values())
        return [provider for provider_id in provider_order if (provider := self._providers.get(provider_id)) is not None]
