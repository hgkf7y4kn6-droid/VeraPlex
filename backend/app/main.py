from fastapi import FastAPI

from app.core.config import assert_production_safe
from app.core.database import Base, engine, install_append_only
from app.modules.admin.router import me_router, router as admin_router
from app.modules.ai.router import router as ai_router
from app.modules.audit.router import router as audit_router
from app.modules.documents.router import router as documents_router
from app.modules.quality.router import router as quality_router

import app.modules.ai.models  # noqa: F401  (register tables)
import app.modules.audit.models  # noqa: F401
import app.modules.documents.models  # noqa: F401
import app.modules.quality.change_control  # noqa: F401  (registers SOP-effective hook)
import app.modules.identity.models  # noqa: F401
import app.modules.quality.models  # noqa: F401
import app.modules.records.models  # noqa: F401

APPEND_ONLY_TABLES = ["audit_event", "signature", "record_state_transition", "reauth_event", "acknowledgment"]


def create_app() -> FastAPI:
    assert_production_safe()
    api = FastAPI(title="VeraPlex", version="0.1.0")
    for r in (quality_router, documents_router, ai_router, audit_router, admin_router, me_router):
        api.include_router(r, prefix="/api/v1")

    @api.get("/healthz")
    def healthz():
        return {"ok": True}

    return api


def init_dev_schema() -> None:
    """Dev/test only. Production schema comes from Alembic migrations."""
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        install_append_only(conn, APPEND_ONLY_TABLES)


app = create_app()
