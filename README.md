# VeraPlex

Pharmaceutical intelligence platform. Built from the "Pharmaceutical Intelligence Platform — Build Plan" (greenfield; the reference repositories in Phase 1 were never supplied).

## What exists (Phases 3–4 backbone, backend only)

`backend/` is a FastAPI modular monolith:

| Module | Delivers |
|---|---|
| `core` | settings, provider interfaces (auth, AI model), principal + permission model, human-only allowlist |
| `audit` | hash-chained, append-only `audit_event` per tenant; `verify_chain` (nightly-job entry point) |
| `records` | versioned controlled records, state machines, locked versions, re-auth e-signatures bound to a content hash, segregation of duties |
| `documents` | SOPs as controlled revisions (draft → review → approved → effective → superseded), reviewed/approved e-signatures, auto training assignment, re-auth read-and-understood acknowledgments, review/training reminders |
| `quality` | deviation → triage (deterministic risk score) → investigation → CAPA → dual QA/area-owner approval → auto-scheduled effectiveness check; recurrence rule (3+ per equipment in 90 days); CAPA → change control → new SOP revision |
| `ai` | Quality agent running as a non-human principal; draft-only write path; cited, labeled drafts; audited human adoption |

Run the checks: `cd backend && pip install -e ".[dev]" && lint-imports && pytest -q`. Set `VERAPLEX_TEST_PG_URL` (a superuser URL) to also run the whole suite against real Postgres as a non-owner role under RLS; CI does this.

## Not built yet / disclosed gaps

- **Postgres is tested** (RLS, REVOKE on append-only tables, a guard that every tenant table has RLS). `membership` is deliberately outside RLS because the tenant is derived from it. Managed-Postgres specifics (Supabase roles, pooler transaction mode with `set_config(..., true)`) are unverified.
- **No real LLM.** `StubModelProvider` returns a deterministic skeleton. LangGraph, the model gateway, and pgvector SOP search are Phase 4/5 work.
- **AI draft adoption is audited but not separately e-signed**; the human signs when completing the investigation (`authored`). The plan's "signed adoption" needs a decision on signing an unlocked draft.
- **Auth:** Supabase JWKS (ES256/RS256/EdDSA) and legacy HS256 verification are unit-tested with generated keys, not against a live Supabase project. Users/memberships are not yet provisioned from Supabase sign-up; there is no invite flow.
- **SOP control:** effective date is always "now" (no scheduled go-live), no file attachments or PDF rendering, reminders are an endpoint/function with no scheduler or notifications yet.
- **Not yet implemented:** offline mobile capture, Expo client, S3 documents, Celery jobs/outbox, entitlements/billing, site-scoped roles, 3D, other modules.
- Risk-matrix band cut-offs (`quality/rules.py`) are provisional defaults pending QA-lead sign-off.
- Nothing here makes the product Part 11 compliant or GxP-validated; that needs customer validation and qualified review.
