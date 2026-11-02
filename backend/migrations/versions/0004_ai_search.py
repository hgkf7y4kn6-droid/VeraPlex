"""SOP search chunks, AI provider audit columns, per-tenant external-inference consent.

Revision ID: 0004
"""
from alembic import op

from app.core.database import Base

revision = "0004"
down_revision = "0003"


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name != "postgresql":
        return
    op.execute("alter table tenant add column if not exists ai_external_inference boolean not null default false")
    op.execute("alter table ai_run add column if not exists provider varchar(40) not null default 'local'")
    op.execute("alter table ai_run add column if not exists external boolean not null default false")
    op.execute("alter table sop_chunk enable row level security")
    op.execute("alter table sop_chunk force row level security")
    op.execute("create policy tenant_isolation on sop_chunk using (tenant_id::text = current_setting('app.tenant_id', true)) "
               "with check (tenant_id::text = current_setting('app.tenant_id', true))")
    op.execute("grant select, insert, update, delete on all tables in schema public to veraplex_app")
    for t in ("audit_event", "signature", "record_state_transition", "reauth_event", "acknowledgment"):
        op.execute(f"revoke update, delete, truncate on {t} from veraplex_app")


def downgrade():
    raise NotImplementedError("Not reversible; restore from backup.")
