import unittest
from collections.abc import AsyncIterator
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.llm.base import BaseChatModel
from app.core.llm.errors import LLMModelError
from app.core.llm.registry import LLMRegistry, ModelDefinition, ProviderDefinition
from app.core.llm.schemas import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    DeltaContent,
    InferenceRequest,
    StreamChoice,
)
from app.services.llm.api.v1 import router


class FakeChatModel(BaseChatModel):
    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id="fake-completion",
            created=123,
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
                created=123,
                model=request.model,
                choices=[
                    StreamChoice(
                        delta=DeltaContent(role="assistant", content=f"streamed:{request.model}"),
                        finish_reason=None,
                    )
                ],
            )

        return _iterator()


class StreamErrorChatModel(FakeChatModel):
    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        async def _iterator() -> AsyncIterator[ChatCompletionChunk]:
            raise LLMModelError(
                "Upstream streaming failed",
                error_code="UPSTREAM_ERROR",
                status_code=502,
            )
            yield

        return _iterator()


def make_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def make_registry() -> LLMRegistry:
    return LLMRegistry(
        (
            ProviderDefinition(
                id="fake",
                name="Fake Provider",
                type="fake",
                default_model="fake-default",
                models=(
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
            ),
        )
    )


class LLMApiTests(unittest.TestCase):
    def test_providers_endpoint_lists_registry_models(self) -> None:
        client = make_test_client()

        with patch("app.services.llm.api.v1.get_llm_registry", return_value=make_registry()):
            response = client.get("/providers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
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

    def test_non_streaming_completion_returns_fake_model_response(self) -> None:
        client = make_test_client()

        with patch("app.services.llm.api.v1.get_llm_registry", return_value=make_registry()):
            response = client.post(
                "/inference/request",
                json={
                    "model": "default",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "fake-completion")
        self.assertEqual(response.json()["model"], "fake-default")
        self.assertEqual(
            response.json()["choices"][0]["message"]["content"],
            "completed:fake-default",
        )

    def test_unknown_model_returns_structured_error(self) -> None:
        client = make_test_client()

        with patch("app.services.llm.api.v1.get_llm_registry", return_value=make_registry()):
            response = client.post(
                "/inference/request",
                json={
                    "model": "missing-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_MODEL")
        self.assertEqual(response.json()["error"]["message"], "Unsupported model: missing-model")

    def test_streaming_completion_wraps_chunks_as_sse(self) -> None:
        client = make_test_client()

        with patch("app.services.llm.api.v1.get_llm_registry", return_value=make_registry()):
            with client.stream(
                "POST",
                "/inference/request",
                json={
                    "model": "fake-other",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            ) as response:
                body = response.read().decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("data: ", body)
        self.assertIn('"model":"fake-other"', body)
        self.assertIn('"content":"streamed:fake-other"', body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))

    def test_streaming_completion_wraps_stream_errors_as_sse(self) -> None:
        client = make_test_client()
        registry = LLMRegistry(
            (
                ProviderDefinition(
                    id="fake",
                    name="Fake Provider",
                    type="fake",
                    default_model="fake-error",
                    models=(ModelDefinition(id="fake-error", model_cls=StreamErrorChatModel),),
                ),
            )
        )

        with patch("app.services.llm.api.v1.get_llm_registry", return_value=registry):
            with client.stream(
                "POST",
                "/inference/request",
                json={
                    "model": "fake-error",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            ) as response:
                body = response.read().decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('"error":', body)
        self.assertIn('"message":"Upstream streaming failed"', body)
        self.assertIn('"code":"UPSTREAM_ERROR"', body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))


if __name__ == "__main__":
    unittest.main()
