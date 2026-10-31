from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.db import Base
from app.modules.audit import models as _a  # noqa: F401
from app.modules.records import models as _r  # noqa: F401
from app.modules.signatures import models as _s  # noqa: F401

with create_engine(settings.database_url).connect() as conn:
    context.configure(connection=conn, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
