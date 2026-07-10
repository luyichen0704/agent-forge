"""Operation Registry (versioned), permissions, plugins."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Operation(Base, TimestampMixin):
    __tablename__ = "operations"
    __table_args__ = (UniqueConstraint("tenant_id", "op_key", "version", name="uq_op_key_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    # which external system this operation belongs to (null = built-in demo op)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id"), nullable=True, index=True
    )
    op_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)            # query|mutation
    confirm_level: Mapped[str] = mapped_column(String(20), nullable=False)   # auto|confirm|dual
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|active|disabled
    input_schema_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_schema_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    executor_binding: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rollback_binding: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # real external call binding: {"source_id":..,"method":..,"path":..,"params":{..},"body_fields":[..]}
    binding_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    policy_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_from_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exploration_jobs.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationPermission(Base):
    """Role/attribute-based grant for an operation (ABAC condition optional)."""
    __tablename__ = "operation_permissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    operation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operations.id"), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)  # role|user
    subject_id: Mapped[str] = mapped_column(String(80), nullable=False)    # role key or user id
    effect: Mapped[str] = mapped_column(String(10), default="allow", nullable=False)  # allow|deny
    condition_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # {"scope":"self"}


class Plugin(Base, TimestampMixin):
    __tablename__ = "plugins"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    iface: Mapped[str] = mapped_column(String(60), nullable=False)  # Explorer|Executor|...
    sub: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[str] = mapped_column(String(40), nullable=False)
    code_signature: Mapped[str] = mapped_column(Text, nullable=False)


class PluginRegistration(Base, TimestampMixin):
    __tablename__ = "plugin_registrations"

    id: Mapped[uuid.UUID] = uuid_pk()
    plugin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plugins.id"), nullable=False, index=True)
    impl_name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), default="0.1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)  # ok|wait|off
    isolation: Mapped[str] = mapped_column(String(20), default="in-process", nullable=False)
    permissions_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    health: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
