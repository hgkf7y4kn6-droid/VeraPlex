import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.modules.audit import models as _a  # noqa: F401
from app.modules.identity.principal import Principal
from app.modules.records import models as _r  # noqa: F401
from app.modules.signatures import models as _s  # noqa: F401


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


class FakeAuth:
    def verify_token(self, token):
        raise NotImplementedError

    def verify_reauth(self, user_id, credential):
        if credential != "ok":
            raise PermissionError("re-auth failed")
        return f"reauth-{user_id}"


@pytest.fixture
def auth():
    return FakeAuth()


def P(user, tenant="t1", kind="human"):
    return Principal(user_id=user, tenant_id=tenant, kind=kind)
