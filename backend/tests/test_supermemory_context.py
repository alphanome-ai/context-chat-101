import unittest

from app.core.config import Settings
from app.core.services.supermemory_context import SupermemoryContextChatManager


class FakeContextManager:
    def __init__(self) -> None:
        self.validated = []

    def validate_session(
        self, *, user_id: str, session_id: str | None, session_mode: str
    ) -> None:
        self.validated.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "session_mode": session_mode,
            }
        )


class FakeSupermemoryClient:
    def __init__(self) -> None:
        self.profile_calls = []
        self.add_calls = []

    def profile(self, **kwargs):
        self.profile_calls.append(kwargs)
        return {
            "profile": {
                "static": ["The user prefers terse answers."],
                "dynamic": ["The user is testing Agent1."],
            },
            "search_results": {"results": [{"content": "Past Agent1 context"}]},
        }

    def add(self, **kwargs):
        self.add_calls.append(kwargs)
        return {"id": "memory-id"}


class SupermemoryContextChatManagerTests(unittest.TestCase):
    def test_build_messages_profiles_user_context(self) -> None:
        context_manager = FakeContextManager()
        client = FakeSupermemoryClient()
        manager = SupermemoryContextChatManager(
            context_manager,  # type: ignore[arg-type]
            settings=Settings(
                supermemory_api_key="supermemory-key",
                supermemory_profile_threshold=0.42,
            ),
            memory_client_factory=lambda: client,
        )

        messages = manager.build_messages(
            user_id="user-id",
            session_id="session-id",
            user_message="hello",
            session_mode="agent1",
        )

        self.assertEqual(
            context_manager.validated,
            [
                {
                    "user_id": "user-id",
                    "session_id": "session-id",
                    "session_mode": "agent1",
                }
            ],
        )
        self.assertEqual(
            client.profile_calls,
            [
                {
                    "container_tag": "user-id",
                    "q": "hello",
                    "threshold": 0.42,
                }
            ],
        )
        self.assertEqual(messages[0].role, "system")
        self.assertEqual(
            messages[0].content,
            (
                "User context from Supermemory:\n\n"
                "Static profile:\n"
                "The user prefers terse answers.\n\n"
                "Dynamic profile:\n"
                "The user is testing Agent1.\n\n"
                "Relevant memories:\n"
                "Past Agent1 context\n\n"
                "Use these memories only when they are relevant to the current request."
            ),
        )
        self.assertEqual(messages[1].content, "hello")

    def test_remember_exchange_adds_conversation_to_user_container(self) -> None:
        client = FakeSupermemoryClient()
        manager = SupermemoryContextChatManager(
            FakeContextManager(),  # type: ignore[arg-type]
            settings=Settings(supermemory_api_key="supermemory-key"),
            memory_client_factory=lambda: client,
        )

        manager.remember_exchange(
            user_id="user-id",
            session_id="session-id",
            user_message="hello",
            assistant_message="answer",
        )

        self.assertEqual(len(client.add_calls), 1)
        self.assertEqual(client.add_calls[0]["container_tag"], "user-id")
        self.assertEqual(client.add_calls[0]["metadata"], {"session_id": "session-id"})
        self.assertIn("User: hello", client.add_calls[0]["content"])
        self.assertIn("Assistant: answer", client.add_calls[0]["content"])


if __name__ == "__main__":
    unittest.main()
