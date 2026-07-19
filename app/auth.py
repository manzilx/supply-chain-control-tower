"""JWT auth + role-based permission matrix for M7.

Tokens are HS256 JWTs signed with JWT_SECRET. They carry `sub` (user_id) and
`tid` (tenant_id) — the tenant is looked up fresh on every request so a role
or tenant change on the server takes effect without a re-login.

Permission matrix is a simple role -> set[str] map where each permission is
a `"resource:action"` or `"resource:*"` pattern. A wildcard `"*"` grants all.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable, Optional, Set

import jwt  # PyJWT
from fastapi import Depends, Header, HTTPException, status

from .schemas import Role, Tenant, User
from .tenants import get_tenant, get_user


_DEFAULT_SECRET = "dev-secret-change-me"


def _is_production_env() -> bool:
    return os.getenv("APP_ENV", "dev").lower() in ("prod", "production")


def validate_jwt_secret_for_production() -> None:
    """Fail fast when prod runs with a missing or default JWT secret."""
    if not _is_production_env():
        return
    raw = os.getenv("JWT_SECRET")
    if not raw or not raw.strip() or raw == _DEFAULT_SECRET:
        raise RuntimeError(
            "JWT_SECRET must be set to a long random value in production "
            f"(APP_ENV={os.getenv('APP_ENV')}). "
            "Generate one with: openssl rand -hex 32"
        )


SECRET: str = os.getenv("JWT_SECRET", _DEFAULT_SECRET)
validate_jwt_secret_for_production()
ALG: str = "HS256"
TTL = timedelta(hours=8)


# --- Permission matrix -------------------------------------------------------


_PERMS: dict[str, Set[str]] = {
    "admin": {"*"},
    "procurement_head": {
        "*:read",
        "pr:*",
        "rfq:*",
        "quote:*",
        "award:*",
        "po:*",
        "approval:decide",
        "followup:create",
        "shipment_event:create",
        "bom:create",
        "vendor:*",
        "ingest:*",
    },
    "buyer": {
        "*:read",
        "pr:create",
        "rfq:create",
        "quote:create",
        "award:create",
        "followup:create",
        "bom:create",
        "vendor:create",
        "ingest:preview",
        "ingest:commit",
    },
    "expeditor": {
        "*:read",
        "followup:create",
        "shipment_event:create",
    },
    "viewer": {
        "*:read",
    },
}


def permissions_for(role: Role) -> list[str]:
    """Flat list form used for UI gating."""

    return sorted(_PERMS.get(role, set()))


def has_perm(role: Role, resource: str, action: str) -> bool:
    grants = _PERMS.get(role, set())
    if "*" in grants:
        return True
    candidates = {
        f"{resource}:{action}",
        f"{resource}:*",
        f"*:{action}",
    }
    return bool(grants & candidates)


# --- Token helpers -----------------------------------------------------------


def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.user_id,
        "tid": user.tenant_id,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + TTL).timestamp()),
    }
    return jwt.encode(payload, SECRET, algorithm=ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=[ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# --- FastAPI dependencies ----------------------------------------------------


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
        )
    return parts[1]


def current_user(
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
    x_tenant_override: Annotated[Optional[str], Header(alias="X-Tenant-Override")] = None,
) -> User:
    token = _extract_token(authorization)
    payload = decode_token(token)
    user_id = payload.get("sub")
    user = get_user(user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    # Admins can override tenant scope with a header — used by the admin tenant
    # switcher without re-issuing a token. Non-admins ignore the header.
    if x_tenant_override and user.role == "admin":
        target = get_tenant(x_tenant_override)
        if target is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown tenant")
        return user.model_copy(update={"tenant_id": x_tenant_override})
    return user


def current_tenant(user: Annotated[User, Depends(current_user)]) -> Tenant:
    tenant = get_tenant(user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown tenant")
    return tenant


def require_role(*roles: Role) -> Callable[[User], User]:
    allowed = set(roles)

    def dep(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted (need one of: {', '.join(sorted(allowed))})",
            )
        return user

    return dep


def require_perm(resource: str, action: str) -> Callable[[User], User]:
    def dep(user: Annotated[User, Depends(current_user)]) -> User:
        if not has_perm(user.role, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action}",
            )
        return user

    return dep
