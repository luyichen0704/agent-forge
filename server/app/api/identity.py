"""Auth + identity. RBAC (allowed screens, scopes) is decided server-side."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.deps import ALLOWED_SCREENS, Principal, get_principal, user_role_keys
from app.models.identity import Role, Session, Tenant, User, UserRole
from app.services.security import new_token, verify_password

router = APIRouter(tags=["identity"])


async def _issue_session(db: AsyncSession, user: User, acting_role: str) -> str:
    token = new_token()
    db.add(Session(user_id=user.id, token=token, acting_role=acting_role,
                   expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)))
    await db.commit()
    return token


class LoginIn(BaseModel):
    role: str = "admin"  # demo: log in as the seeded user holding this role


@router.post("/auth/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Demo-only role login (no password). Disabled outside dev — use /auth/token."""
    if not settings.demo_login_enabled:
        raise HTTPException(status_code=403, detail="role login disabled; use /auth/token")
    role = (await db.execute(select(Role).where(Role.key == body.role).limit(1))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=400, detail=f"unknown role {body.role}")
    user = (
        await db.execute(
            select(User).join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_id == role.id).limit(1)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="no user for role")
    token = await _issue_session(db, user, body.role)
    return {"token": token, "acting_role": body.role,
            "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name}}


class TokenIn(BaseModel):
    email: str
    password: str
    role: str | None = None  # optional acting role; must be one the user holds


@router.post("/auth/token")
async def token_login(body: TokenIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Production login: email + password → session token."""
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not user.is_active or not user.password_hash \
            or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    roles = await user_role_keys(db, user.id)
    if not roles:
        raise HTTPException(status_code=403, detail="user has no roles")
    acting = body.role or roles[0]
    if acting not in roles:
        raise HTTPException(status_code=403, detail="role not granted to user")
    token = await _issue_session(db, user, acting)
    return {"token": token, "acting_role": acting,
            "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name}}


@router.post("/auth/logout")
async def logout(p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)) -> dict:
    # revoke ONLY the current bearer token's session
    p.session.revoked = True
    await db.commit()
    return {"ok": True}


@router.get("/me")
async def me(p: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)) -> dict:
    tenant = await db.get(Tenant, p.tenant_id)
    roles = await user_role_keys(db, p.user.id)
    return {
        "user": {"id": str(p.user.id), "email": p.user.email, "display_name": p.user.display_name},
        "tenant": {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug},
        "acting_role": p.role,
        "roles": roles,
        "allowed_screens": ALLOWED_SCREENS.get(p.role, []),
    }
