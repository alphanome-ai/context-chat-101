"""rename token usage columns

Revision ID: 8f7c4f1b2a90
Revises: 25b58e7a4d9c
Create Date: 2026-05-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "8f7c4f1b2a90"
down_revision: str | None = "25b58e7a4d9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = _chat_message_columns()
    if "prompt_tokens" in columns and "input_tokens" not in columns:
        op.execute("ALTER TABLE chat_messages RENAME COLUMN prompt_tokens TO input_tokens")
    if "completion_tokens" in columns and "output_tokens" not in columns:
        op.execute("ALTER TABLE chat_messages RENAME COLUMN completion_tokens TO output_tokens")


def downgrade() -> None:
    columns = _chat_message_columns()
    if "output_tokens" in columns and "completion_tokens" not in columns:
        op.execute("ALTER TABLE chat_messages RENAME COLUMN output_tokens TO completion_tokens")
    if "input_tokens" in columns and "prompt_tokens" not in columns:
        op.execute("ALTER TABLE chat_messages RENAME COLUMN input_tokens TO prompt_tokens")


def _chat_message_columns() -> set[str]:
    rows = op.get_bind().exec_driver_sql("PRAGMA table_info(chat_messages)")
    return {row[1] for row in rows}
