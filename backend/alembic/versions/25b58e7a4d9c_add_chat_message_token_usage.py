"""add chat message token usage

Revision ID: 25b58e7a4d9c
Revises: 81333648a6c7
Create Date: 2026-05-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "25b58e7a4d9c"
down_revision: str | None = "81333648a6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("total_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "total_tokens")
    op.drop_column("chat_messages", "completion_tokens")
    op.drop_column("chat_messages", "prompt_tokens")
