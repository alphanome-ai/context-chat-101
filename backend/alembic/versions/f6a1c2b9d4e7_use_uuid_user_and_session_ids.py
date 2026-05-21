"""use uuid user and session ids

Revision ID: f6a1c2b9d4e7
Revises: d0f4e7b9a2c1
Create Date: 2026-05-21 00:00:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "f6a1c2b9d4e7"
down_revision: str | None = "d0f4e7b9a2c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        raise NotImplementedError("UUID id migration currently supports SQLite only")
    if _column_type("users", "id").startswith("VARCHAR"):
        return

    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    _create_uuid_maps()
    _rename_legacy_tables()
    _create_uuid_tables()
    _copy_uuid_data()
    _drop_legacy_tables()
    _create_uuid_indexes()
    bind.exec_driver_sql("DROP TABLE user_uuid_map")
    bind.exec_driver_sql("DROP TABLE chat_session_uuid_map")
    bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise NotImplementedError("Downgrading UUID user/session ids is not supported")


def _create_uuid_maps() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        "CREATE TABLE user_uuid_map (old_id TEXT PRIMARY KEY, new_id VARCHAR(36) NOT NULL)"
    )
    bind.exec_driver_sql(
        "CREATE TABLE chat_session_uuid_map "
        "(old_id TEXT PRIMARY KEY, new_id VARCHAR(36) NOT NULL)"
    )

    for (old_id,) in bind.exec_driver_sql("SELECT id FROM users"):
        bind.execute(
            sa.text("INSERT INTO user_uuid_map (old_id, new_id) VALUES (:old_id, :new_id)"),
            {"old_id": str(old_id), "new_id": str(uuid4())},
        )

    for (old_id,) in bind.exec_driver_sql("SELECT id FROM chat_sessions"):
        bind.execute(
            sa.text(
                "INSERT INTO chat_session_uuid_map (old_id, new_id) "
                "VALUES (:old_id, :new_id)"
            ),
            {"old_id": str(old_id), "new_id": str(uuid4())},
        )


def _rename_legacy_tables() -> None:
    for table in (
        "users",
        "auth_sessions",
        "chat_sessions",
        "quota_usage",
        "chat_messages",
    ):
        op.rename_table(table, f"{table}_int_ids")


def _create_uuid_tables() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE users (
            id VARCHAR(36) NOT NULL,
            email VARCHAR(320) NOT NULL,
            password_hash VARCHAR(512) NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TABLE auth_sessions (
            id INTEGER NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TABLE chat_sessions (
            id VARCHAR(36) NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            title VARCHAR(160) NOT NULL,
            model VARCHAR(120),
            mode VARCHAR(24) DEFAULT 'chat' NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TABLE quota_usage (
            id INTEGER NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            date DATETIME NOT NULL,
            tokens_used INTEGER NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TABLE chat_messages (
            id INTEGER NOT NULL,
            session_id VARCHAR(36) NOT NULL,
            role VARCHAR(24) NOT NULL,
            content TEXT NOT NULL,
            thinking TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            position INTEGER NOT NULL,
            created_at DATETIME,
            PRIMARY KEY (id),
            FOREIGN KEY(session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE,
            UNIQUE (session_id, position)
        )
        """
    )


def _copy_uuid_data() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        INSERT INTO users (id, email, password_hash, created_at)
        SELECT map.new_id, users.email, users.password_hash, users.created_at
        FROM users_int_ids AS users
        JOIN user_uuid_map AS map ON map.old_id = CAST(users.id AS TEXT)
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO auth_sessions (id, user_id, token_hash, created_at, expires_at)
        SELECT auth_sessions.id, users.new_id, auth_sessions.token_hash,
               auth_sessions.created_at, auth_sessions.expires_at
        FROM auth_sessions_int_ids AS auth_sessions
        JOIN user_uuid_map AS users ON users.old_id = CAST(auth_sessions.user_id AS TEXT)
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO chat_sessions (id, user_id, title, model, mode, created_at, updated_at)
        SELECT sessions.new_id, users.new_id, chat_sessions.title, chat_sessions.model,
               chat_sessions.mode, chat_sessions.created_at, chat_sessions.updated_at
        FROM chat_sessions_int_ids AS chat_sessions
        JOIN chat_session_uuid_map AS sessions
            ON sessions.old_id = CAST(chat_sessions.id AS TEXT)
        JOIN user_uuid_map AS users ON users.old_id = CAST(chat_sessions.user_id AS TEXT)
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO quota_usage (id, user_id, date, tokens_used)
        SELECT quota_usage.id, users.new_id, quota_usage.date, quota_usage.tokens_used
        FROM quota_usage_int_ids AS quota_usage
        JOIN user_uuid_map AS users ON users.old_id = CAST(quota_usage.user_id AS TEXT)
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO chat_messages (
            id, session_id, role, content, thinking, input_tokens, output_tokens,
            total_tokens, position, created_at
        )
        SELECT chat_messages.id, sessions.new_id, chat_messages.role,
               chat_messages.content, chat_messages.thinking, chat_messages.input_tokens,
               chat_messages.output_tokens, chat_messages.total_tokens,
               chat_messages.position, chat_messages.created_at
        FROM chat_messages_int_ids AS chat_messages
        JOIN chat_session_uuid_map AS sessions
            ON sessions.old_id = CAST(chat_messages.session_id AS TEXT)
        """
    )


def _drop_legacy_tables() -> None:
    for table in (
        "chat_messages_int_ids",
        "quota_usage_int_ids",
        "chat_sessions_int_ids",
        "auth_sessions_int_ids",
        "users_int_ids",
    ):
        op.drop_table(table)


def _create_uuid_indexes() -> None:
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(
        op.f("ix_auth_sessions_token_hash"),
        "auth_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"])
    op.create_index(op.f("ix_chat_sessions_id"), "chat_sessions", ["id"])
    op.create_index(op.f("ix_chat_sessions_user_id"), "chat_sessions", ["user_id"])
    op.create_index(op.f("ix_quota_usage_id"), "quota_usage", ["id"])
    op.create_index(op.f("ix_quota_usage_user_id"), "quota_usage", ["user_id"])
    op.create_index(op.f("ix_chat_messages_id"), "chat_messages", ["id"])
    op.create_index(op.f("ix_chat_messages_session_id"), "chat_messages", ["session_id"])


def _column_type(table_name: str, column_name: str) -> str:
    rows = op.get_bind().exec_driver_sql(f"PRAGMA table_info({table_name})")
    for row in rows:
        if row[1] == column_name:
            return str(row[2]).upper()
    return ""
