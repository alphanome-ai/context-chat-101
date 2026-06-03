"""add chat message events json

Revision ID: a6c9e3d1b824
Revises: f6a1c2b9d4e7
Create Date: 2026-05-22 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a6c9e3d1b824"
down_revision: str | None = "f6a1c2b9d4e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = _chat_message_columns()
    if "events_json" not in columns:
        op.add_column("chat_messages", sa.Column("events_json", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = _chat_message_columns()
    if "events_json" in columns:
        op.drop_column("chat_messages", "events_json")


def _chat_message_columns() -> set[str]:
    rows = op.get_bind().exec_driver_sql("PRAGMA table_info(chat_messages)")
    return {row[1] for row in rows}
