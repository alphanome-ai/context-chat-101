import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from app.core.agent1 import Agent1RunRequest, Agent1Service
from app.core.config import Settings


def make_settings() -> Settings:
    return Settings(
        agent1_llm_api_key="primary-key",
        agent1_model="primary-model",
        agent1_recovery_llm_api_key="recovery-key",
        agent1_recovery_model="recovery-model",
        tavily_api_key="tavily-key",
        supermemory_api_key="",
    )


async def collect_events(service: Agent1Service, request: Agent1RunRequest):
    return [
        event async for event in service.stream(request, db=None, user_id="user-id")
    ]  # type: ignore[arg-type]


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


class Agent1ServiceTests(unittest.TestCase):
    def test_configuration_requires_agent1_settings(self) -> None:
        service = Agent1Service(
            settings=Settings(
                agent1_llm_api_key="",
                agent1_model="",
                agent1_recovery_llm_api_key="",
                agent1_recovery_model="",
                tavily_api_key="",
                supermemory_api_key="",
            )
        )

        with self.assertRaisesRegex(Exception, "AGENT1_LLM_API_KEY"):
            service.validate_configuration()

    def test_agent1_uses_internal_model_and_ignores_request_model(self) -> None:
        model_factory = FakeModelFactory()
        captured_prompts = []

        def agent_factory(_model, _tools, system_prompt):
            captured_prompts.append(system_prompt)
            return FakeAgent({"messages": [{"content": "primary-answer"}]})

        service = Agent1Service(
            settings=make_settings(),
            model_factory=model_factory,  # type: ignore[arg-type]
            agent_factory=agent_factory,
            search_tool_factory=fake_search_tool,
        )

        events = asyncio.run(
            collect_events(
                service,
                Agent1RunRequest(message="hello", model="user-selected-model"),
            )
        )

        self.assertEqual(model_factory.primary_calls, 1)
        self.assertEqual(model_factory.recovery_calls, 0)
        self.assertIn("Agent1", captured_prompts[0])
        self.assertEqual(events[0].message, "Agent1 started.")
        self.assertEqual(events[-2].type, "message_delta")
        self.assertEqual(events[-2].message, "primary-answer")

    def test_recoverable_primary_failure_uses_agent1_recovery(self) -> None:
        model_factory = FakeModelFactory()

        def agent_factory(_model, _tools, _system_prompt):
            return FakeAgent(error=RuntimeError("primary failed"))

        service = Agent1Service(
            settings=make_settings(),
            model_factory=model_factory,  # type: ignore[arg-type]
            agent_factory=agent_factory,
            search_tool_factory=fake_search_tool,
        )

        with patch(
            "app.core.agent1.service._is_recoverable_model_error", return_value=True
        ):
            events = asyncio.run(
                collect_events(service, Agent1RunRequest(message="hello"))
            )

        self.assertEqual(model_factory.primary_calls, 1)
        self.assertEqual(model_factory.recovery_calls, 1)
        self.assertIn("recovery_started", [event.type for event in events])
        self.assertEqual(
            [event.message for event in events if event.type == "message_delta"],
            ["recovery-answer"],
        )


if __name__ == "__main__":
    unittest.main()
