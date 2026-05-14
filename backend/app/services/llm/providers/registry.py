from app.services.llm.providers.base import LLMProvider, LLMProviderError
from app.services.llm.providers.openai_provider import OpenAICompatibleProvider

_registry: dict[str, type[LLMProvider]] = {
    "openai": OpenAICompatibleProvider,
}
_instances: dict[str, LLMProvider] = {}


def get_provider(provider: str) -> LLMProvider:
    provider_cls = _registry.get(provider)
    if provider_cls is None:
        raise LLMProviderError(
            f"Unsupported LLM provider: {provider}",
            error_code="UNSUPPORTED_PROVIDER",
            status_code=404,
        )
    if provider not in _instances:
        _instances[provider] = provider_cls()
    return _instances[provider]
