"""Chat sessions, messages, execution plans and steps."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), default="新会话", nullable=False)
    # optional: scope planning to one system so the P-LLM catalogue isn't diluted
    # by operations from other registered systems (null = all systems in scope)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id"), nullable=True, index=True
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user|assistant|system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("execution_plans.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExecutionPlan(Base, TimestampMixin):
    """A P-LLM produced plan draft, bound to a trace once executed."""
    __tablename__ = "execution_plans"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    trace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("traces.id"), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    writes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_confirm_level: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    policy_hints_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # draft | awaiting_confirm | confirmed | executing | done | cancelled | denied
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    pllm_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_runs.id"), nullable=True)


class PlanStep(Base):
    __tablename__ = "plan_steps"
    __table_args__ = (UniqueConstraint("plan_id", "step_no", name="uq_plan_step_no"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("execution_plans.id"), nullable=False, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # query|parse|write
    op_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    input_refs_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    capability_in: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    capability_out: Mapped[str] = mapped_column(String(20), nullable=False)  # trusted|data|parsed|write
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
