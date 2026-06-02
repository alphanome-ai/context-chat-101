import json
import unittest
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.core.transcripts import (
    JsonlTranscriptStore,
    append_chat_session_messages_jsonl,
)
from app.db.models import User
from app.db.session import Base, get_db
from app.services.chat_history.api import router

USER_ID = "11111111-1111-4111-8111-111111111111"


class ChatHistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transcript_dir = TemporaryDirectory()
        self.transcript_root = Path(self.transcript_dir.name)

        async def append_test_transcript(chat_session, messages):
            return await append_chat_session_messages_jsonl(
                chat_session,
                messages,
                store=JsonlTranscriptStore(self.transcript_root),
            )

        self.transcript_patch = patch(
            "app.services.chat_history.api.append_chat_session_messages_jsonl",
            side_effect=append_test_transcript,
        )
        self.transcript_patch.start()

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session_factory = sessionmaker(
            bind=engine, autocommit=False, autoflush=False
        )

        with self.session_factory() as db:
            db.add(User(id=USER_ID, email="user@example.com", password_hash="hash"))
            db.commit()

        app = FastAPI()
        app.include_router(router, prefix="/chat-sessions")
        app.dependency_overrides[get_db] = self._override_db
        app.dependency_overrides[get_current_user] = self._override_user
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.transcript_patch.stop()
        self.transcript_dir.cleanup()

    def _override_db(self) -> Generator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def _override_user(self) -> User:
        with self.session_factory() as db:
            user = db.get(User, USER_ID)
            assert user is not None
            db.expunge(user)
            return user

    def test_create_and_load_session_persists_mode(self) -> None:
        create_response = self.client.post(
            "/chat-sessions",
            json={
                "mode": "agent0",
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["mode"], "agent0")

        load_response = self.client.get(f"/chat-sessions/{created['id']}")

        self.assertEqual(load_response.status_code, 200)
        self.assertEqual(load_response.json()["mode"], "agent0")

        transcript_path = (
            self.transcript_root
            / "agent0"
            / "sessions"
            / str(created["id"])
            / "messages.jsonl"
        )
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        transcript_message = json.loads(lines[0])
        self.assertEqual(transcript_message["session_id"], created["id"])
        self.assertEqual(transcript_message["user_id"], USER_ID)
        self.assertEqual(transcript_message["mode"], "agent0")
        self.assertEqual(transcript_message["model"], "fake-model")
        self.assertEqual(transcript_message["position"], 0)
        self.assertEqual(transcript_message["role"], "user")
        self.assertEqual(transcript_message["content"], "hello")

    def test_assistant_events_are_persisted_and_loaded(self) -> None:
        response = self.client.post(
            "/chat-sessions",
            json={
                "mode": "agent0",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {
                        "role": "assistant",
                        "content": "answer",
                        "events": [
                            {
                                "type": "tool_completed",
                                "tool_name": "web_search",
                                "message": "Search completed",
                                "payload": {"query": "hello"},
                            }
                        ],
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 201)
        assistant_message = response.json()["messages"][1]
        self.assertEqual(
            assistant_message["events"],
            [
                {
                    "type": "tool_completed",
                    "tool_name": "web_search",
                    "message": "Search completed",
                    "payload": {"query": "hello"},
                }
            ],
        )

    def test_session_mode_defaults_to_chat(self) -> None:
        response = self.client.post(
            "/chat-sessions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["mode"], "chat")

    def test_agent1_session_writes_agent1_transcript(self) -> None:
        create_response = self.client.post(
            "/chat-sessions",
            json={
                "mode": "agent1",
                "messages": [{"role": "user", "content": "hello agent1"}],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["mode"], "agent1")

        transcript_path = (
            self.transcript_root
            / "agent1"
            / "sessions"
            / str(created["id"])
            / "messages.jsonl"
        )
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        transcript_message = json.loads(lines[0])
        self.assertEqual(transcript_message["mode"], "agent1")
        self.assertEqual(transcript_message["content"], "hello agent1")


if __name__ == "__main__":
    unittest.main()
