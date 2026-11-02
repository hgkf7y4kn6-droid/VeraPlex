"""Idempotency keys for offline-queue replays.

Revision ID: 0003
"""
from alembic import op

from app.core.database import Base

revision = "0003"
down_revision = "0002"


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name != "postgresql":
        return
    op.execute("alter table idempotency_key enable row level security")
    op.execute("alter table idempotency_key force row level security")
    op.execute("create policy tenant_isolation on idempotency_key using (tenant_id::text = current_setting('app.tenant_id', true)) "
               "with check (tenant_id::text = current_setting('app.tenant_id', true))")
    op.execute("grant select, insert, update, delete on all tables in schema public to veraplex_app")
    for t in ("audit_event", "signature", "record_state_transition", "reauth_event", "acknowledgment"):
        op.execute(f"revoke update, delete, truncate on {t} from veraplex_app")


def downgrade():
    raise NotImplementedError("Not reversible; restore from backup.")
