# VeraPlex

Pharmaceutical intelligence platform. Built from the "Pharmaceutical Intelligence Platform — Build Plan" (greenfield; the reference repositories in Phase 1 were never supplied).

## What exists (Phases 3–4 backbone, backend only)

`backend/` is a FastAPI modular monolith:

| Module | Delivers |
|---|---|
| `core` | settings, provider interfaces (auth, AI model), principal + permission model, human-only allowlist |
| `audit` | hash-chained, append-only `audit_event` per tenant; `verify_chain` (nightly-job entry point) |
| `records` | versioned controlled records, state machines, locked versions, re-auth e-signatures bound to a content hash, segregation of duties |
| `quality` | deviation → triage (deterministic risk score) → investigation → CAPA → dual QA/area-owner approval → auto-scheduled effectiveness check; recurrence rule (3+ per equipment in 90 days) |
| `ai` | Quality agent running as a non-human principal; draft-only write path; cited, labeled drafts; audited human adoption |

Run the checks: `cd backend && pip install -e ".[dev]" && lint-imports && pytest -q`

## Not built yet / disclosed gaps

- **Tested on SQLite only.** The Postgres RLS policies and `REVOKE` grants (`migrations/versions/0001_foundation.py`) are written but have not been run against a live Postgres. Run the isolation suite against Postgres before any pilot.
- **No real LLM.** `StubModelProvider` returns a deterministic skeleton. LangGraph, the model gateway, and pgvector SOP search are Phase 4/5 work.
- **AI draft adoption is audited but not separately e-signed**; the human signs when completing the investigation (`authored`). The plan's "signed adoption" needs a decision on signing an unlocked draft.
- **Not yet implemented:** SOP/document control and change-control → training reassignment, offline mobile capture, Expo client, S3 documents, Celery jobs/outbox, entitlements/billing, Supabase JWKS verification (HS256 secret only), site-scoped roles, 3D, other modules.
- Risk-matrix band cut-offs (`quality/rules.py`) are provisional defaults pending QA-lead sign-off.
- Nothing here makes the product Part 11 compliant or GxP-validated; that needs customer validation and qualified review.
