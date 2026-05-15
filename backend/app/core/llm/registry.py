from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from app.core.llm.base import BaseChatModel, ChatModelProtocol
from app.core.llm.errors import LLMModelError
from app.core.llm.openai_compatible import (
    GPT52ChatModel,
    GPT52Model,
    GPT53CodexModel,
    GPT55Model,
    KimiK26Model,
)
from app.core.llm.schemas import LLMModel, LLMProviderInfo, ProvidersResponse


@dataclass(frozen=True)
class ModelDefinition:
    id: str
    model_cls: type[BaseChatModel]
    name: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    type: str
    models: tuple[ModelDefinition, ...]
    default_model: str


class LLMRegistry:
    def __init__(
        self,
        providers: Sequence[ProviderDefinition],
        *,
        default_provider_id: str | None = None,
    ) -> None:
        if not providers:
            raise LLMModelError(
                "At least one LLM provider must be registered",
                error_code="CONFIGURATION_ERROR",
                status_code=500,
            )

        self._providers = tuple(providers)
        self._default_provider_id = default_provider_id or self._providers[0].id
        self._provider_by_id: dict[str, ProviderDefinition] = {}
        self._provider_by_model: dict[str, ProviderDefinition] = {}
        self._model_by_id: dict[str, ModelDefinition] = {}
        self._instances: dict[str, ChatModelProtocol] = {}
        self._validate()

    def _validate(self) -> None:
        for provider in self._providers:
            if provider.id in self._provider_by_id:
                raise LLMModelError(
                    f"Duplicate LLM provider id: {provider.id}",
                    error_code="CONFIGURATION_ERROR",
                    status_code=500,
                )

            provider_models: dict[str, ModelDefinition] = {}
            for model in provider.models:
                if model.id in provider_models:
                    raise LLMModelError(
                        f"Duplicate LLM model id: {model.id}",
                        error_code="CONFIGURATION_ERROR",
                        status_code=500,
                    )
                provider_models[model.id] = model

            if provider.default_model not in provider_models:
                raise LLMModelError(
                    f"Default model {provider.default_model!r} is not registered for {provider.id}",
                    error_code="CONFIGURATION_ERROR",
                    status_code=500,
                )

            self._provider_by_id[provider.id] = provider
            for model_id, model_definition in provider_models.items():
                if model_id in self._provider_by_model:
                    raise LLMModelError(
                        f"Duplicate LLM model id: {model_id}",
                        error_code="CONFIGURATION_ERROR",
                        status_code=500,
                    )
                self._provider_by_model[model_id] = provider
                self._model_by_id[model_id] = model_definition

        if self._default_provider_id not in self._provider_by_id:
            raise LLMModelError(
                f"Default LLM provider is not registered: {self._default_provider_id}",
                error_code="CONFIGURATION_ERROR",
                status_code=500,
            )

    def provider_infos(self) -> list[LLMProviderInfo]:
        return [
            LLMProviderInfo(
                id=provider.id,
                name=provider.name,
                type=provider.type,
                models=[
                    LLMModel(
                        id=model.id,
                        name=model.name,
                        displayName=model.display_name or model.name,
                        isDefault=model.id == provider.default_model,
                    )
                    for model in provider.models
                ],
            )
            for provider in self._providers
        ]

    def providers_response(self) -> ProvidersResponse:
        return ProvidersResponse(providers=self.provider_infos())

    def resolve(self, requested_model: str) -> tuple[ChatModelProtocol, str]:
        if requested_model == "default":
            provider = self._provider_by_id[self._default_provider_id]
            resolved_model = provider.default_model
        else:
            resolved_provider = self._provider_by_model.get(requested_model)
            if resolved_provider is None:
                raise LLMModelError(
                    f"Unsupported model: {requested_model}",
                    error_code="UNSUPPORTED_MODEL",
                    status_code=400,
                )
            provider = resolved_provider
            resolved_model = requested_model

        model_definition = self._model_by_id[resolved_model]
        model = self._model_for_definition(provider, model_definition)
        return model, model.resolve_model(resolved_model)

    def _model_for_definition(
        self,
        provider: ProviderDefinition,
        model: ModelDefinition,
    ) -> BaseChatModel:
        if model.id not in self._instances:
            self._instances[model.id] = model.model_cls(
                provider_id=provider.id,
                provider_name=provider.name,
                provider_type=provider.type,
                model_id=model.id,
                model_name=model.name,
            )
        instance = self._instances[model.id]
        if not isinstance(instance, BaseChatModel):
            raise LLMModelError(
                f"Registered LLM model must extend BaseChatModel: {model.id}",
                error_code="CONFIGURATION_ERROR",
                status_code=500,
            )
        return instance


DEFAULT_PROVIDERS: tuple[ProviderDefinition, ...] = (
    ProviderDefinition(
        id="openai",
        name="OpenAI",
        type="openai-compatible",
        default_model="gpt-5.2-chat",
        models=(
            ModelDefinition(
                id="gpt-5.2-chat",
                display_name="GPT-5.2 Chat",
                model_cls=GPT52ChatModel,
            ),
            ModelDefinition(
                id="gpt-5.5-1",
                display_name="GPT-5.5",
                model_cls=GPT55Model,
            ),
            ModelDefinition(
                id="gpt-5.3-codex",
                display_name="GPT-5.3 Codex",
                model_cls=GPT53CodexModel,
            ),
            ModelDefinition(
                id="gpt-5.2",
                display_name="GPT-5.2",
                model_cls=GPT52Model,
            ),
        ),
    ),
    ProviderDefinition(
        id="moonshot",
        name="Moonshot AI",
        type="openai-compatible",
        default_model="kimi-k2.6",
        models=(
            ModelDefinition(
                id="kimi-k2.6",
                display_name="Kimi K2.6",
                model_cls=KimiK26Model,
            ),
        ),
    ),
)


@lru_cache
def get_llm_registry() -> LLMRegistry:
    return LLMRegistry(DEFAULT_PROVIDERS)
