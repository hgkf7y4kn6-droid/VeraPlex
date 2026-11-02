import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import providers
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.identity.models import Membership, User

HUMAN_ROLES = sorted(r for r in ROLE_PERMISSIONS if r != "ai_agent")


def _audit(db, p, action, m: Membership, old=None, new=None, reason=None):
    audit.record_event(db, tenant_id=p.tenant_id, actor_id=p.user_id, actor_kind=p.kind, action=action,
                       entity_type="membership", entity_id=m.id, old=old, new=new, reason=reason)


def invite_user(db: Session, p: Principal, email: str, name: str, role: str) -> tuple[User, Membership]:
    if role not in HUMAN_ROLES:
        raise HTTPException(422, f"role must be one of {HUMAN_ROLES}")
    email = email.strip().lower()
    dup = db.scalars(select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.tenant_id == p.tenant_id, func.lower(User.email) == email)).first()
    if dup:
        raise HTTPException(409, "this email already has access to the tenant")
    try:
        sub = uuid.UUID(providers.user_directory.invite(email))
    except providers.AuthError as exc:
        raise HTTPException(502, "could not invite user with the identity provider") from exc
    user = db.get(User, sub)
    if user and (user.kind != "human" or db.scalars(select(Membership).where(Membership.user_id == sub, Membership.active.is_(True))).first()):
        raise HTTPException(409, "this identity already belongs to another tenant or principal")  # one active tenant per user
    if not user:
        user = User(id=sub, email=email, display_name=name, kind="human")
        db.add(user)
    user.active = True
    db.flush()  # user row must exist before the membership FK
    m = Membership(tenant_id=p.tenant_id, user_id=sub, role=role)
    db.add(m)
    db.flush()
    _audit(db, p, "user.invite", m, new={"email": email, "role": role}, reason="user invited")
    return user, m


def _member(db, p, user_id) -> tuple[User, Membership]:
    row = db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id).where(
        Membership.tenant_id == p.tenant_id, User.id == user_id, Membership.active.is_(True))).first()
    if not row:
        raise HTTPException(404, "not found")
    return row


def _active_admins(db, tenant_id) -> int:
    return db.scalar(select(func.count()).select_from(Membership).where(
        Membership.tenant_id == tenant_id, Membership.role == "admin", Membership.active.is_(True))) or 0


def change_role(db: Session, p: Principal, user_id: uuid.UUID, role: str, reason: str) -> Membership:
    user, m = _member(db, p, user_id)
    if user.kind != "human" or role not in HUMAN_ROLES:
        raise HTTPException(422, "invalid role or principal")
    if user_id == p.user_id:
        raise HTTPException(403, "you cannot change your own role")
    if m.role == "admin" and role != "admin" and _active_admins(db, p.tenant_id) <= 1:
        raise HTTPException(409, "cannot remove the last administrator")
    old, m.role = m.role, role
    _audit(db, p, "user.role_change", m, old={"role": old}, new={"role": role}, reason=reason)
    return m


def deactivate(db: Session, p: Principal, user_id: uuid.UUID, reason: str) -> Membership:
    user, m = _member(db, p, user_id)
    if user_id == p.user_id:
        raise HTTPException(403, "you cannot deactivate yourself")
    if m.role == "admin" and _active_admins(db, p.tenant_id) <= 1:
        raise HTTPException(409, "cannot remove the last administrator")
    m.active = False  # records stay attributable; access ends
    _audit(db, p, "user.deactivate", m, old={"active": True}, new={"active": False}, reason=reason)
    return m
