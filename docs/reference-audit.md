# Phase 1: reference repository audit

Read-only audit of six repos (shallow clones, 2026-10-31). None has a LICENSE file; they are all
the owner's own code, so reuse is a decision, not a legal block. Reuse means porting patterns or
small modules, not vendoring whole apps.

| Repo | What it is | Stack | Reuse for VeraPlex |
|---|---|---|---|
| `pool-project-workflow` | Pool-construction PM, offline-first, 7 roles | Expo + Fastify/TS + Postgres/Supabase, Turborepo, Python `crew` service | **High.** See below. |
| `mmm` (KaventaFi) | Subscriptions + dividend research | Expo SDK 54 + FastAPI + SQLAlchemy + Celery, Clerk, Stripe, Plaid | **High for backend plumbing**: `entitlements.py`, `billing.py` (webhook verification), `tasks.py`, `guard.py`, CI. |
| `capstone-healthcare-agent` | Prescription-refill / feedback triage agents | CrewAI, local transformers, FAISS, Celery, SQLite | **Low-medium.** Eval harness and monitoring ideas only. |
| `dfs-riches` | DraftKings DFS explorer | FastAPI, Expo, Neon | **Low.** Only the staged `PRO_GATING` rollout idea. |
| `cost-comparison-tool` (VectorSales) | Sales/proposal tool | FastAPI single service, Render | **Low.** Render deploy config. |
| `gsap-web-dom` | Vite/React animation site | React + Vite + GSAP | **Low.** Possible marketing site. |

## Highest-value items

1. **Offline sync (`pool-project-workflow/packages/sync`, `docs/offline-sync.md`)**: platform-agnostic
   TS engine (queue, backoff, coalesce, merge, conflict records, ~465 lines) with the rule
   "never silently drop edits". Directly satisfies the Quality slice's "offline deviation capture with
   conflict-safe sync". Port the engine as-is; the server side must be rewritten for FastAPI.
2. **Postgres lockdown (`packages/database/migrations/0002_supabase_lockdown.sql`)**: enable RLS on every
   table with no policies, revoke from `anon`/`authenticated`, and a test that fails if a new table skips RLS.
   This matches our "never use Supabase's auto API" rule. **Conflict with our scaffold:** migration 0001 here
   uses tenant policies keyed on `app.tenant_id` and `FORCE ROW LEVEL SECURITY`. Decide one model
   (recommended: keep FORCE + tenant policy for a non-owner app role, and add their lockdown and their
   "every table has RLS" test).
3. **Authorization conventions (`AGENTS.md`, `services/access.ts`)**: capability check plus row-level check on
   every service call, 404 for inaccessible rows, redacted client portal. Same shape as ours.
4. **Deterministic intelligence + LLM-only-writes-language (`docs/intelligence.md`, `services/crew`)**: rules
   decide, agents only phrase, output re-validated by the API. Same principle as our AI governance section;
   use as the template for the Quality agent.
5. **Entitlements (`mmm/backend/entitlements.py`, `billing.py`)**: server-side `require_feature`, 402 before
   data is computed, grace periods, Stripe HMAC webhook verification with timestamp tolerance. Port to our
   `organization_entitlements` model.
6. **Repo hygiene**: version-bump script, ADR-style docs, mmm `ci.yml`, Render yaml/Dockerfile in several repos.

## Gaps and conflicts to resolve

- **Auth:** `mmm` and `dfs-riches` use Clerk. Our plan says Supabase Auth. Pick one before wiring re-authentication
  (e-signatures need a reliable re-auth primitive; verify which provider supports it cleanly).
- **Language split:** pool-project-workflow's API is Node/TS; ours is Python. Port patterns, not code, except `packages/sync`.
- **Signatures:** pool's change-order e-signature stores a drawn-signature PNG and name only. It has no
  re-authentication, no meaning, no content-hash binding, so it is not Part 11 shaped. Keep our implementation.
- **Audit trail:** pool has activity feeds and a readiness audit, but nothing hash-chained or append-only. Keep ours.
- **Healthcare repo:** `capstone-healthcare-agent` ships `patients.db` and `data/patients.json`. Do not copy
  those or any patient-like data into VeraPlex. It runs a local model with CrewAI, which our plan defers; reuse only
  `evaluation/` structure and `monitoring/` for AI-run logging.
- No repo has Part 11 / Annex 11 controls, validation documentation, or a requirements matrix. Those stay net-new.

## Suggested next steps

1. Port `packages/sync` into a `packages/sync` workspace for the Expo client.
2. Add the "every table has RLS" test and tenant-context wiring to the backend against real Postgres.
3. Port `entitlements` + Stripe webhook verification as a `commercial` module.
4. Decide Clerk vs Supabase Auth.
