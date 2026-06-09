"""partial unique index on executions.idempotency_key

Revision ID: a1b2c3d4e5f6
Revises: 62527d79c8f6
Create Date: 2026-06-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "62527d79c8f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # drop the non-unique index, replace with a partial UNIQUE index (NULLs allowed)
    op.drop_index("ix_executions_idempotency_key", table_name="executions")
    op.create_index(
        "uq_executions_idempotency_key",
        "executions",
        ["idempotency_key"],
        unique=True,
        postgresql_where="idempotency_key IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_executions_idempotency_key", table_name="executions")
    op.create_index("ix_executions_idempotency_key", "executions", ["idempotency_key"])
