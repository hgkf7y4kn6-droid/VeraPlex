import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import providers
from app.core.database import get_db, set_tenant_guc
from app.core.permissions import HUMAN_ONLY, ROLE_PERMISSIONS
from app.modules.identity.models import Membership, User


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    name: str
    kind: str  # human | ai
    tenant_id: uuid.UUID
    role: str
    permissions: frozenset[str]
    token_jti: str | None = None

    def can(self, perm: str) -> bool:
        if self.kind != "human" and perm in HUMAN_ONLY:
            return False
        return perm in self.permissions


def principal_from_user(db: Session, user_id: uuid.UUID) -> Principal:
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(401, "unknown or inactive user")
    m = db.scalars(
        select(Membership).where(Membership.user_id == user_id, Membership.active.is_(True)).limit(1)
    ).first()
    if not m:
        raise HTTPException(403, "no active membership")
    perms = frozenset(ROLE_PERMISSIONS.get(m.role, set()))
    return Principal(user.id, user.display_name, user.kind, m.tenant_id, m.role, perms)


def get_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Principal:
    """Tenant comes from the verified token's user, never from the request body or query."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        claims = providers.auth_provider.verify(authorization[7:])
        uid = uuid.UUID(claims.sub)
    except (providers.AuthError, ValueError) as exc:
        raise HTTPException(401, "invalid token") from exc
    p = principal_from_user(db, uid)
    set_tenant_guc(db, p.tenant_id)
    return p


def require(perm: str):
    def dep(p: Principal = Depends(get_principal)) -> Principal:
        if not p.can(perm):
            raise HTTPException(403, f"missing permission: {perm}")
        return p
    return dep
