import uuid
from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def make_engine(url: str):
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def set_tenant_guc(db: Session, tenant_id: uuid.UUID) -> None:
    """Postgres RLS backstop: policies compare tenant_id to this setting."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def install_append_only(bind, tables: list[str]) -> None:
    """DB-level guard. SQLite uses triggers (tests); Postgres uses REVOKE in the migration."""
    if bind.dialect.name != "sqlite":
        return
    for t in tables:
        for op in ("update", "delete"):
            bind.exec_driver_sql(
                f"create trigger if not exists {t}_no_{op} before {op} on {t} "
                f"begin select raise(abort, '{t} is append-only'); end"
            )
