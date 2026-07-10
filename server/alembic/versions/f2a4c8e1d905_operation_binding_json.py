"""operations.binding_json — real external API call binding

Revision ID: f2a4c8e1d905
Revises: e075f1384de3
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f2a4c8e1d905"
down_revision = "e075f1384de3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operations", sa.Column("binding_json", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("operations", "binding_json")
