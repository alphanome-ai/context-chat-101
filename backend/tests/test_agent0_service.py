import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from app.core.agent0 import Agent0RunRequest, Agent0Service
from app.core.config import Settings


def make_settings() -> Settings:
    return Settings(
        agent0_llm_api_key="primary-key",
        agent0_model="primary-model",
        agent0_recovery_llm_api_key="recovery-key",
        agent0_recovery_model="recovery-model",
        tavily_api_key="tavily-key",
    )


async def collect_events(service: Agent0Service, request: Agent0RunRequest):
    return [event async for event in service.stream(request, db=None, user_id="user-id")]  # type: ignore[arg-type]


class FakeModel:
    def __init__(self, content: str) -> None:
        self.content = content

    async def ainvoke(self, _messages):
        return {"content": self.content}


class FakeModelFactory:
    def __init__(self) -> None:
        self.primary_calls = 0
        self.recovery_calls = 0

    def primary(self) -> FakeModel:
        self.primary_calls += 1
        return FakeModel("primary-answer")

    def recovery(self) -> FakeModel:
        self.recovery_calls += 1
        return FakeModel("recovery-answer")


class FakeAgent:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    async def ainvoke(self, _input):
        if self.error is not None:
            raise self.error
        return self.response


def fake_search_tool(_completed_tool_results, _emit):
    return object()


class Agent0ServiceTests(unittest.TestCase):
    def test_configuration_requires_agent0_settings(self) -> None:
        service = Agent0Service(settings=Settings())

        with self.assertRaisesRegex(Exception, "AGENT0_LLM_API_KEY"):
            service.validate_configuration()

    def test_agent0_uses_internal_model_and_ignores_request_model(self) -> None:
        model_factory = FakeModelFactory()
        captured_models = []

        def agent_factory(model, _tools, _system_prompt):
            captured_models.append(model)
            return FakeAgent({"messages": [{"content": "primary-answer"}]})

        service = Agent0Service(
            settings=make_settings(),
            model_factory=model_factory,  # type: ignore[arg-type]
            agent_factory=agent_factory,
            search_tool_factory=fake_search_tool,
        )

        events = asyncio.run(
            collect_events(
                service,
                Agent0RunRequest(message="hello", model="user-selected-model"),
            )
        )

        self.assertEqual(model_factory.primary_calls, 1)
        self.assertEqual(model_factory.recovery_calls, 0)
        self.assertEqual(captured_models[0].content, "primary-answer")
        self.assertEqual(events[-2].type, "message_delta")
        self.assertEqual(events[-2].message, "primary-answer")

    def test_recoverable_primary_failure_uses_final_answer_recovery(self) -> None:
        model_factory = FakeModelFactory()

        def agent_factory(_model, _tools, _system_prompt):
            return FakeAgent(error=RuntimeError("primary failed"))

        service = Agent0Service(
            settings=make_settings(),
            model_factory=model_factory,  # type: ignore[arg-type]
            agent_factory=agent_factory,
            search_tool_factory=fake_search_tool,
        )

        with patch("app.core.agent.service._is_recoverable_model_error", return_value=True):
            events = asyncio.run(
                collect_events(service, Agent0RunRequest(message="hello"))
            )

        self.assertEqual(model_factory.primary_calls, 1)
        self.assertEqual(model_factory.recovery_calls, 1)
        self.assertIn("recovery_started", [event.type for event in events])
        self.assertIn("recovery_completed", [event.type for event in events])
        self.assertEqual(
            [event.message for event in events if event.type == "message_delta"],
            ["recovery-answer"],
        )

    def test_non_recoverable_primary_failure_streams_error(self) -> None:
        model_factory = FakeModelFactory()

        def agent_factory(_model, _tools, _system_prompt):
            return FakeAgent(error=ValueError("bad request"))

        service = Agent0Service(
            settings=make_settings(),
            model_factory=model_factory,  # type: ignore[arg-type]
            agent_factory=agent_factory,
            search_tool_factory=fake_search_tool,
        )

        events = asyncio.run(collect_events(service, Agent0RunRequest(message="hello")))

        self.assertEqual(model_factory.recovery_calls, 0)
        self.assertEqual(events[-1].type, "error")
        self.assertEqual(events[-1].message, "bad request")


if __name__ == "__main__":
    unittest.main()
