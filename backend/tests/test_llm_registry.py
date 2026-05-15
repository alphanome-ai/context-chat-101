import unittest
from collections.abc import AsyncIterator

from app.core.llm.base import BaseChatModel
from app.core.llm.errors import LLMModelError
from app.core.llm.registry import (
    DEFAULT_PROVIDERS,
    LLMRegistry,
    ModelDefinition,
    ProviderDefinition,
)
from app.core.llm.schemas import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    DeltaContent,
    InferenceRequest,
    StreamChoice,
)


class FakeChatModel(BaseChatModel):
    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id="fake-completion",
            created=1,
            model=request.model,
            choices=[
                Choice(
                    message=AssistantMessage(content=f"completed:{request.model}"),
                    finish_reason="stop",
                )
            ],
        )

    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        async def _iterator() -> AsyncIterator[ChatCompletionChunk]:
            yield ChatCompletionChunk(
                id="fake-chunk",
                created=1,
                model=request.model,
                choices=[
                    StreamChoice(
                        delta=DeltaContent(role="assistant", content=f"streamed:{request.model}"),
                        finish_reason=None,
                    )
                ],
            )

        return _iterator()


class OtherFakeChatModel(FakeChatModel):
    pass


def make_provider(
    *,
    provider_id: str = "fake",
    default_model: str = "fake-default",
    models: tuple[ModelDefinition, ...] | None = None,
) -> ProviderDefinition:
    return ProviderDefinition(
        id=provider_id,
        name=f"{provider_id.title()} Provider",
        type="fake",
        default_model=default_model,
        models=models
        or (
            ModelDefinition(
                id="fake-default",
                name="Fake Default",
                display_name="Fake Default Display",
                model_cls=FakeChatModel,
            ),
            ModelDefinition(
                id="fake-other",
                name="Fake Other",
                display_name="Fake Other Display",
                model_cls=FakeChatModel,
            ),
        ),
    )


class LLMRegistryTests(unittest.TestCase):
    def test_provider_metadata_comes_from_registry(self) -> None:
        registry = LLMRegistry((make_provider(),))

        response = registry.providers_response()
        data = response.model_dump(by_alias=True)

        self.assertEqual(
            data,
            {
                "providers": [
                    {
                        "id": "fake",
                        "name": "Fake Provider",
                        "type": "fake",
                        "models": [
                            {
                                "id": "fake-default",
                                "name": "Fake Default",
                                "displayName": "Fake Default Display",
                                "isDefault": True,
                            },
                            {
                                "id": "fake-other",
                                "name": "Fake Other",
                                "displayName": "Fake Other Display",
                                "isDefault": False,
                            },
                        ],
                    }
                ]
            },
        )

    def test_default_resolves_to_registered_default_model(self) -> None:
        registry = LLMRegistry((make_provider(),))

        model, resolved_model = registry.resolve("default")

        self.assertIsInstance(model, FakeChatModel)
        self.assertEqual(resolved_model, "fake-default")

    def test_known_model_routes_to_registered_provider(self) -> None:
        first_provider = make_provider(
            provider_id="first",
            default_model="first-default",
            models=(ModelDefinition(id="first-default", model_cls=FakeChatModel),),
        )
        second_provider = make_provider(
            provider_id="second",
            default_model="second-default",
            models=(
                ModelDefinition(id="second-default", model_cls=FakeChatModel),
                ModelDefinition(id="second-other", model_cls=OtherFakeChatModel),
            ),
        )
        registry = LLMRegistry((first_provider, second_provider))

        model, resolved_model = registry.resolve("second-other")

        self.assertIsInstance(model, OtherFakeChatModel)
        self.assertEqual(model.provider_id, "second")
        self.assertEqual(resolved_model, "second-other")

    def test_models_in_same_provider_can_use_different_model_classes(self) -> None:
        provider = make_provider(
            default_model="fake-default",
            models=(
                ModelDefinition(id="fake-default", model_cls=FakeChatModel),
                ModelDefinition(id="fake-new-version", model_cls=OtherFakeChatModel),
            ),
        )
        registry = LLMRegistry((provider,))

        model, resolved_model = registry.resolve("fake-new-version")

        self.assertIsInstance(model, OtherFakeChatModel)
        self.assertEqual(model.provider_id, "fake")
        self.assertEqual(resolved_model, "fake-new-version")

    def test_unknown_model_returns_structured_error(self) -> None:
        registry = LLMRegistry((make_provider(),))

        with self.assertRaises(LLMModelError) as error:
            registry.resolve("missing-model")

        self.assertEqual(error.exception.error_code, "UNSUPPORTED_MODEL")
        self.assertEqual(error.exception.status_code, 400)

    def test_duplicate_model_ids_fail_validation(self) -> None:
        first_provider = make_provider(
            provider_id="first",
            default_model="shared-model",
            models=(ModelDefinition(id="shared-model", model_cls=FakeChatModel),),
        )
        second_provider = make_provider(
            provider_id="second",
            default_model="shared-model",
            models=(ModelDefinition(id="shared-model", model_cls=FakeChatModel),),
        )

        with self.assertRaises(LLMModelError) as error:
            LLMRegistry((first_provider, second_provider))

        self.assertEqual(error.exception.error_code, "CONFIGURATION_ERROR")
        self.assertIn("Duplicate LLM model id", error.exception.message)

    def test_default_registry_routes_gpt_55_through_responses_adapter(self) -> None:
        provider = DEFAULT_PROVIDERS[0]
        model_classes = {model.id: model.model_cls.__name__ for model in provider.models}

        self.assertEqual(model_classes["gpt-5.5"], "GPT55Model")

    def test_default_registry_routes_codex_model_through_responses_adapter(self) -> None:
        provider = DEFAULT_PROVIDERS[0]
        model_classes = {model.id: model.model_cls.__name__ for model in provider.models}

        self.assertEqual(model_classes["gpt-5.3-codex"], "GPT53CodexModel")

    def test_default_registry_routes_kimi_through_responses_adapter(self) -> None:
        model_classes = {
            model.id: model.model_cls.__name__
            for provider in DEFAULT_PROVIDERS
            for model in provider.models
        }

        self.assertEqual(model_classes["kimi-k2.6"], "KimiK26Model")


if __name__ == "__main__":
    unittest.main()
