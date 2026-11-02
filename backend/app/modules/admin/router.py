import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Principal, require
from app.modules.admin import service
from app.modules.identity.models import Membership, User

router = APIRouter(prefix="/admin", tags=["admin"])


class InviteIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=2)
    role: str


class PatchIn(BaseModel):
    role: str | None = None
    active: bool | None = None
    reason: str = Field(min_length=3)


@router.post("/users", status_code=201)
def invite(body: InviteIn, p: Principal = Depends(require("user.manage")), db: Session = Depends(get_db)):
    u, m = service.invite_user(db, p, body.email, body.display_name, body.role)
    return {"user_id": u.id, "email": u.email, "role": m.role}


@router.get("/users")
def users(p: Principal = Depends(require("user.manage")), db: Session = Depends(get_db)):
    rows = db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id).where(
        Membership.tenant_id == p.tenant_id, Membership.active.is_(True)).order_by(User.display_name))
    return [{"user_id": u.id, "email": u.email, "name": u.display_name, "kind": u.kind, "role": m.role} for u, m in rows]


@router.patch("/users/{user_id}")
def patch(user_id: uuid.UUID, body: PatchIn, p: Principal = Depends(require("user.manage")), db: Session = Depends(get_db)):
    if body.role:
        service.change_role(db, p, user_id, body.role, body.reason)
    if body.active is False:
        service.deactivate(db, p, user_id, body.reason)
    return {"ok": True}
