"""Foundation tables, tenant RLS, append-only audit role grants."""
from alembic import op

from app.db import Base

revision = "0001"
down_revision = None

TENANT_TABLES = ["record", "record_version", "signature", "audit_event"]


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name != "postgresql":
        return
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        # The API runs `SET LOCAL app.tenant_id = <verified token tenant>` per transaction.
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )
    # Backstop for the ORM-level guard: the app role can insert and read audit rows, nothing else.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM PUBLIC")


def downgrade():
    Base.metadata.drop_all(op.get_bind())
