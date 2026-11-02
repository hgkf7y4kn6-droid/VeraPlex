from alembic import context
from sqlalchemy import create_engine

import app.main  # noqa: F401  (registers all tables)
from app.core.config import settings
from app.core.database import Base

target_metadata = Base.metadata


def run_migrations_online():
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
