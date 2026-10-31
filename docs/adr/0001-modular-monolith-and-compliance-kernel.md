# ADR 0001: Modular monolith with a compliance kernel

Status: accepted

One FastAPI service; modules own their tables and may only import downward
(`signatures > records > audit > identity`, enforced by import-linter in CI).
Audit trail, e-signatures, versioned controlled records and tenant isolation are built
before any business module. The AI principal is a non-human `Principal(kind="ai")` that
the backend refuses for sign/approve/state-change regardless of what an orchestrator asks.

Known gaps (Phase 2 scaffold): Supabase re-authentication is a stub; RLS policies are in
migration 0001 but the per-request `SET LOCAL app.tenant_id` is not yet wired and the policies
are untested against a real Postgres; no requirements matrix yet; no UI.
