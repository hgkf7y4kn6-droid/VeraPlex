"""Foundation: schema, row-level security, append-only grants.

Revision ID: 0001
"""
from alembic import op

from app.core.database import Base

revision = "0001"
down_revision = None

TENANT_TABLES = [
    "audit_event", "record", "record_version", "record_state_transition", "reauth_event", "signature",
    "deviation", "investigation", "capa", "ai_run", "ai_draft", "membership",
]
APPEND_ONLY = ["audit_event", "signature", "record_state_transition", "reauth_event"]


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name != "postgresql":
        return
    for t in TENANT_TABLES:
        op.execute(f"alter table {t} enable row level security")
        op.execute(f"alter table {t} force row level security")
        op.execute(
            f"create policy tenant_isolation on {t} using (tenant_id::text = current_setting('app.tenant_id', true)) "
            f"with check (tenant_id::text = current_setting('app.tenant_id', true))"
        )
    # The application role (create it as `veraplex_app`, NOT a superuser/owner) may only INSERT/SELECT these.
    for t in APPEND_ONLY:
        op.execute(f"revoke update, delete, truncate on {t} from veraplex_app")


def downgrade():
    raise NotImplementedError("Foundation migration is not reversible; restore from backup.")
