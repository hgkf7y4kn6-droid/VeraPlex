import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core import database
from app.core.config import settings
from app.main import APPEND_ONLY_TABLES, create_app
from app.modules.identity.models import Membership, Tenant, User


@pytest.fixture()
def engine():
    eng = database.make_engine("sqlite://")
    database.Base.metadata.create_all(eng)
    with eng.begin() as c:
        database.install_append_only(c, APPEND_ONLY_TABLES)
    return eng


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def client(Session):
    app = create_app()

    def _db():
        s = Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[database.get_db] = _db
    return TestClient(app)


def token(user_id, *, age=0, jti=None):
    now = int(time.time()) - age
    return jwt.encode(
        {"sub": str(user_id), "aud": settings.jwt_audience, "iat": now, "exp": now + 3600, "jti": jti or uuid.uuid4().hex},
        settings.supabase_jwt_secret, algorithm="HS256",
    )


class World:
    def __init__(self, Session):
        self.Session = Session

    def tenant(self, name):
        with self.Session() as s:
            t = Tenant(name=name)
            s.add(t)
            s.commit()
            return t.id

    def user(self, tenant_id, role, name=None, kind="human"):
        with self.Session() as s:
            u = User(email=f"{uuid.uuid4().hex[:6]}@x.test", display_name=name or role, kind=kind)
            s.add(u)
            s.flush()
            s.add(Membership(tenant_id=tenant_id, user_id=u.id, role=role))
            s.commit()
            return u.id

    @staticmethod
    def h(user_id, **kw):
        return {"Authorization": f"Bearer {token(user_id, **kw)}"}


@pytest.fixture()
def world(Session):
    return World(Session)
