"""add policy_rules

Revision ID: a2c3d4e5f6g7
Revises: b8d5f0a3c216
Create Date: 2025-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2c3d4e5f6g7"
down_revision: Union[str, None] = "b8d5f0a3c216"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("effect", sa.String(20), nullable=False, server_default="deny"),
        sa.Column("confirm_escalation", sa.String(20), nullable=True),
        sa.Column("op_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("capability_tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("risk_levels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("roles", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("op_kinds", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("conditions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("condition_expr", sa.String(1000), nullable=True),
        sa.Column("trace_clause", postgresql.JSONB(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("reason", sa.String(300), nullable=False, server_default=""),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_rules_tenant_id", "policy_rules", ["tenant_id"])
    op.create_index("ix_policy_rules_rule_id", "policy_rules", ["rule_id"])


def downgrade() -> None:
    op.drop_index("ix_policy_rules_rule_id", table_name="policy_rules")
    op.drop_index("ix_policy_rules_tenant_id", table_name="policy_rules")
    op.drop_table("policy_rules")
