"""Request dependencies — server-enforced identity & RBAC."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.identity import Role, Session, User, UserRole
from app.policies.engine import Identity

# server-side source of truth for which screens a role may see
ALLOWED_SCREENS = {
    "customer": ["chat", "flow"],
    "employee": ["chat", "flow", "live", "ops"],
    "admin": ["explore", "live", "chat", "flow", "ops", "audit", "plugins"],
}


class Principal:
    def __init__(self, user: User, role: str, tenant_id: uuid.UUID, session: Session):
        self.user = user
        self.role = role
        self.tenant_id = tenant_id
        self.session = session

    @property
    def identity(self) -> Identity:
        return Identity(user_id=str(self.user.id), role=self.role, display_name=self.user.display_name)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def _resolve_token(token: str | None, db: AsyncSession) -> Principal:
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    sess = (
        await db.execute(select(Session).where(Session.token == token, Session.revoked.is_(False)))
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=401, detail="invalid token")
    if sess.expires_at and sess.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="session expired")
    user = await db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user inactive")
    # re-verify the acting role still belongs to this user (revocation safety)
    roles = await user_role_keys(db, user.id)
    if sess.acting_role not in roles:
        raise HTTPException(status_code=403, detail="acting role no longer granted")
    return Principal(user=user, role=sess.acting_role, tenant_id=user.tenant_id, session=sess)


async def get_principal(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return await _resolve_token(authorization.split(" ", 1)[1].strip(), db)


async def get_principal_qs(
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """Auth for EventSource/SSE: token may arrive as a query param (EventSource
    can't set headers). Falls back to the Authorization header."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    return await _resolve_token(token, db)


async def user_role_keys(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = (
        await db.execute(
            select(Role.key)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
    ).scalars().all()
    return list(rows)
