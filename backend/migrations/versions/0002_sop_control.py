"""SOP control and change control tables: RLS and append-only grants.

Revision ID: 0002
"""
from alembic import op

from app.core.database import Base

revision = "0002"
down_revision = "0001"

NEW_TABLES = ["sop", "sop_revision", "training_assignment", "acknowledgment", "change_control"]


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)  # checkfirst: creates only what 0001 did not
    if bind.dialect.name != "postgresql":
        return
    for t in NEW_TABLES:
        op.execute(f"alter table {t} enable row level security")
        op.execute(f"alter table {t} force row level security")
        op.execute(
            f"create policy tenant_isolation on {t} using (tenant_id::text = current_setting('app.tenant_id', true)) "
            f"with check (tenant_id::text = current_setting('app.tenant_id', true))"
        )
    op.execute("grant select, insert, update, delete on all tables in schema public to veraplex_app")
    op.execute("revoke update, delete, truncate on acknowledgment from veraplex_app")
    # re-assert 0001's append-only revokes: the blanket grant above would otherwise undo them
    for t in ("audit_event", "signature", "record_state_transition", "reauth_event"):
        op.execute(f"revoke update, delete, truncate on {t} from veraplex_app")


def downgrade():
    raise NotImplementedError("Not reversible; restore from backup.")
