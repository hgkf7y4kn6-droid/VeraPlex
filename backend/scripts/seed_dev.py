"""Dev/e2e only: create the schema and one tenant with an operator and a QA user. Prints their ids as JSON."""
import json

from app.core.database import SessionLocal
from app.main import init_dev_schema
from app.modules.identity.models import Membership, Tenant, User

init_dev_schema()
with SessionLocal() as db:
    t = Tenant(name="E2E Pharma")
    db.add(t)
    db.flush()
    out = {"tenant": str(t.id)}
    for role in ("operator", "qa", "admin"):
        u = User(email=f"{role}@e2e.test", display_name=role.title(), kind="human")
        db.add(u)
        db.flush()
        db.add(Membership(tenant_id=t.id, user_id=u.id, role=role))
        out[role] = str(u.id)
    db.commit()
print(json.dumps(out))
