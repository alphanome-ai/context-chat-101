"""add chat session mode

Revision ID: d0f4e7b9a2c1
Revises: 8f7c4f1b2a90
Create Date: 2026-05-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d0f4e7b9a2c1"
down_revision: str | None = "8f7c4f1b2a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = _chat_session_columns()
    if "mode" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column("mode", sa.String(length=24), nullable=False, server_default="chat"),
        )
    op.execute("UPDATE chat_sessions SET mode = 'chat' WHERE mode IS NULL OR mode = ''")


def downgrade() -> None:
    columns = _chat_session_columns()
    if "mode" in columns:
        op.drop_column("chat_sessions", "mode")


def _chat_session_columns() -> set[str]:
    rows = op.get_bind().exec_driver_sql("PRAGMA table_info(chat_sessions)")
    return {row[1] for row in rows}
