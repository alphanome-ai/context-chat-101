import asyncio
import unittest
from collections.abc import AsyncIterator
from types import SimpleNamespace

from app.core.llm.openai_model import (
    GPT52ChatModel,
    GPT52Model,
    GPT53CodexModel,
    GPT55Model,
    KimiK26Model,
)
from app.core.llm.schemas import InferenceRequest


async def collect_async(iterator: AsyncIterator):
    items = []
    async for item in iterator:
        items.append(item)
    return items


class OpenAIModelPayloadTests(unittest.TestCase):
    def test_gpt_52_chat_omits_unsupported_temperature(self) -> None:
        model = GPT52ChatModel(
            provider_id="openai",
            provider_name="OpenAI",
            provider_type="openai-compatible",
            model_id="gpt-5.2-chat",
            client=object(),
        )
        request = InferenceRequest(
            model="gpt-5.2-chat",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            max_tokens=256,
        )

        payload = model._build_payload(request, stream=False)

        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["model"], "gpt-5.2-chat")
        self.assertEqual(payload["max_completion_tokens"], 256)

    def test_other_openai_model_keeps_temperature(self) -> None:
        model = GPT52Model(
            provider_id="openai",
            provider_name="OpenAI",
            provider_type="openai-compatible",
            model_id="gpt-5.2",
            client=object(),
        )
        request = InferenceRequest(
            model="gpt-5.2",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
        )

        payload = model._build_payload(request, stream=False)

        self.assertEqual(payload["temperature"], 0.2)

    def test_kimi_model_uses_responses_payload_shape(self) -> None:
        model = KimiK26Model(
            provider_id="moonshot",
            provider_name="Moonshot AI",
            provider_type="openai-compatible",
            model_id="kimi-k2.6",
            client=object(),
        )
        request = InferenceRequest(
            model="kimi-k2.6",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            max_tokens=256,
        )

        payload = model._build_payload(request, stream=False)

        self.assertEqual(payload["model"], "kimi-k2.6")
        self.assertEqual(payload["input"], [{"role": "user", "content": "hello"}])
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_output_tokens"], 256)
        self.assertNotIn("messages", payload)

    def test_codex_model_uses_responses_payload_shape(self) -> None:
        model = GPT53CodexModel(
            provider_id="openai",
            provider_name="OpenAI",
            provider_type="openai-compatible",
            model_id="gpt-5.3-codex",
            client=object(),
        )
        request = InferenceRequest(
            model="gpt-5.3-codex",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            top_p=0.9,
            max_tokens=256,
        )

        payload = model._build_payload(request, stream=False)

        self.assertEqual(payload["model"], "gpt-5.3-codex")
        self.assertEqual(payload["input"], [{"role": "user", "content": "hello"}])
        self.assertEqual(payload["max_output_tokens"], 256)
        self.assertNotIn("messages", payload)
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)

    def test_gpt_55_model_uses_responses_payload_shape_without_temperature(self) -> None:
        model = GPT55Model(
            provider_id="openai",
            provider_name="OpenAI",
            provider_type="openai-compatible",
            model_id="gpt-5.5",
            client=object(),
        )
        request = InferenceRequest(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            top_p=0.9,
            max_tokens=256,
        )

        payload = model._build_payload(request, stream=False)

        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["input"], [{"role": "user", "content": "hello"}])
        self.assertEqual(payload["max_output_tokens"], 256)
        self.assertEqual(payload["top_p"], 0.9)
        self.assertNotIn("temperature", payload)
        self.assertNotIn("messages", payload)

    def test_codex_response_maps_to_chat_response_shape(self) -> None:
        model = GPT53CodexModel(
            provider_id="openai",
            provider_name="OpenAI",
            provider_type="openai-compatible",
            model_id="gpt-5.3-codex",
            client=object(),
        )
        response = SimpleNamespace(
            id="resp_123",
            created_at=123.4,
            model="gpt-5.3-codex",
            status="completed",
            output_text="hello from responses",
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            ),
            error=None,
        )

        mapped = model._response_to_chat_completion(response)

        self.assertEqual(mapped.id, "resp_123")
        self.assertEqual(mapped.model, "gpt-5.3-codex")
        self.assertEqual(mapped.choices[0].message.content, "hello from responses")
        self.assertEqual(mapped.usage.total_tokens, 15)

    def test_codex_stream_maps_responses_events_to_chat_chunks(self) -> None:
        class FakeResponses:
            async def create(self, **_payload):
                async def _events():
                    yield SimpleNamespace(
                        type="response.created",
                        response=SimpleNamespace(
                            id="resp_123",
                            created_at=123,
                        ),
                    )
                    yield SimpleNamespace(
                        type="response.output_text.delta",
                        delta="hello",
                    )
                    yield SimpleNamespace(
                        type="response.completed",
                        response=SimpleNamespace(
                            id="resp_123",
                            created_at=123,
                            model="gpt-5.3-codex",
                            status="completed",
                            usage=SimpleNamespace(
                                input_tokens=3,
                                output_tokens=2,
                                total_tokens=5,
                            ),
                        ),
                    )

                return _events()

        model = GPT53CodexModel(
            provider_id="openai",
            provider_name="OpenAI",
            provider_type="openai-compatible",
            model_id="gpt-5.3-codex",
            client=SimpleNamespace(responses=FakeResponses()),
        )
        request = InferenceRequest(
            model="gpt-5.3-codex",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )

        chunks = asyncio.run(collect_async(model.stream(request)))

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].id, "resp_123")
        self.assertEqual(chunks[0].choices[0].delta.content, "hello")
        self.assertEqual(chunks[1].choices[0].finish_reason, "stop")
        self.assertEqual(chunks[1].usage.total_tokens, 5)


if __name__ == "__main__":
    unittest.main()
