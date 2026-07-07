"""operations.source_id — attribute each operation to its data source

Revision ID: a7c3e9f21b40
Revises: f2a4c8e1d905
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op

revision = "a7c3e9f21b40"
down_revision = "f2a4c8e1d905"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operations", sa.Column("source_id", sa.Uuid(), nullable=True))
    op.create_index("ix_operations_source_id", "operations", ["source_id"])
    op.create_foreign_key("fk_operations_source_id", "operations", "data_sources",
                          ["source_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_operations_source_id", "operations", type_="foreignkey")
    op.drop_index("ix_operations_source_id", table_name="operations")
    op.drop_column("operations", "source_id")
