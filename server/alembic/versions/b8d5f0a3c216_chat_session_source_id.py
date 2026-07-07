"""chat_sessions.source_id — scope planning to one system

Revision ID: b8d5f0a3c216
Revises: a7c3e9f21b40
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op

revision = "b8d5f0a3c216"
down_revision = "a7c3e9f21b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("source_id", sa.Uuid(), nullable=True))
    op.create_index("ix_chat_sessions_source_id", "chat_sessions", ["source_id"])
    op.create_foreign_key("fk_chat_sessions_source_id", "chat_sessions", "data_sources",
                          ["source_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_chat_sessions_source_id", "chat_sessions", type_="foreignkey")
    op.drop_index("ix_chat_sessions_source_id", table_name="chat_sessions")
    op.drop_column("chat_sessions", "source_id")
