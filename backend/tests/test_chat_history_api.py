import unittest
from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import Base, get_db
from app.services.chat_history.api import router


class ChatHistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        with self.session_factory() as db:
            db.add(User(id=1, email="user@example.com", password_hash="hash"))
            db.commit()

        app = FastAPI()
        app.include_router(router, prefix="/chat-sessions")
        app.dependency_overrides[get_db] = self._override_db
        app.dependency_overrides[get_current_user] = self._override_user
        self.client = TestClient(app)

    def _override_db(self) -> Generator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def _override_user(self) -> User:
        with self.session_factory() as db:
            user = db.get(User, 1)
            assert user is not None
            db.expunge(user)
            return user

    def test_create_and_load_session_persists_mode(self) -> None:
        create_response = self.client.post(
            "/chat-sessions",
            json={
                "mode": "agent",
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["mode"], "agent")

        load_response = self.client.get(f"/chat-sessions/{created['id']}")

        self.assertEqual(load_response.status_code, 200)
        self.assertEqual(load_response.json()["mode"], "agent")

    def test_session_mode_defaults_to_chat(self) -> None:
        response = self.client.post(
            "/chat-sessions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["mode"], "chat")


if __name__ == "__main__":
    unittest.main()
