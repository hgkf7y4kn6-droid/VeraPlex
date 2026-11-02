import os
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core import database
from app.core.config import settings
from app.main import APPEND_ONLY_TABLES, create_app
from app.modules.identity.models import Membership, Tenant, User

PG_ADMIN_URL = os.environ.get("VERAPLEX_TEST_PG_URL")  # superuser URL, e.g. postgresql+psycopg://postgres@/postgres?host=/tmp&port=54329
BACKENDS = ["sqlite"] + (["postgres"] if PG_ADMIN_URL else [])


def _run_migration(admin_engine):
    import glob
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    for path in sorted(glob.glob("migrations/versions/*.py")):
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with admin_engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.upgrade()


@pytest.fixture(scope="session")
def pg_urls():
    if not PG_ADMIN_URL:
        pytest.skip("no postgres")
    admin = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("drop database if exists veraplex_test with (force)"))
        c.execute(text("create database veraplex_test"))
        if not c.execute(text("select 1 from pg_roles where rolname='veraplex_app'")).first():
            c.execute(text("create role veraplex_app login password 'app' nosuperuser nobypassrls"))
    admin_url = create_engine(PG_ADMIN_URL).url.set(database="veraplex_test")
    admin_engine = create_engine(admin_url)
    import app.main  # noqa: F401
    _run_migration(admin_engine)
    return admin_engine, admin_url.set(username="veraplex_app", password="app")


@pytest.fixture(params=BACKENDS)
def db_env(request):
    """Yields (app_engine, admin_engine). On Postgres the app connects as a non-owner role under RLS."""
    if request.param == "sqlite":
        eng = database.make_engine("sqlite://")
        database.Base.metadata.create_all(eng)
        with eng.begin() as c:
            database.install_append_only(c, APPEND_ONLY_TABLES)
        yield eng, eng, "sqlite"
        return
    admin_engine, app_url = request.getfixturevalue("pg_urls")
    with admin_engine.begin() as c:
        names = ", ".join(t.name for t in database.Base.metadata.sorted_tables)
        c.execute(text(f"truncate {names} cascade"))
    yield create_engine(app_url), admin_engine, "postgres"


@pytest.fixture()
def engine(db_env):
    return db_env[0]


@pytest.fixture()
def dialect(db_env):
    return db_env[2]


@pytest.fixture()
def admin_engine(db_env):
    return db_env[1]


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


@pytest.fixture()
def world(Session):
    return World(Session)
