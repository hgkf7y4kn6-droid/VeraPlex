# VeraPlex

A compliance-first pharmaceutical intelligence platform. The first vertical slice is **Quality**: deviation → investigation → CAPA → SOP change control, with an AI assistant that drafts and never decides.

Built from the *Pharmaceutical Intelligence Platform — Build Plan*. It is greenfield: the reference repositories in the plan's Phase 1 were never supplied.

> **Not validated.** Nothing in this repository makes a product Part 11 / Annex 11 compliant or GxP-validated. That requires customer-specific validation, procedures and independent review. See [Known gaps](#known-gaps).

## Architecture

A single FastAPI **modular monolith** (`backend/`). Modules own their tables and may import only modules below them; `import-linter` enforces this in CI.

```
ai          Quality agent: non-human principal, read-scoped tools, draft-only writes
admin       user provisioning (Supabase invite), role changes, deactivation
quality     deviation, investigation, CAPA, change control, deterministic risk + recurrence rules
documents   SOPs as controlled revisions, training assignment, acknowledgments, reminders
records     versioned controlled records, state machines, re-auth e-signatures
audit       hash-chained append-only audit trail
identity    tenant, user, membership
core        config, auth provider, principals, permissions, DB session
```

Key controls:

- **Tenancy:** the tenant comes from the verified token's user, never the request. Postgres row-level security is the backstop (`app.tenant_id`); the app role is not the table owner.
- **Audit:** every state change writes a SHA-256 hash-chained `audit_event` in the same transaction. UPDATE/DELETE are revoked in Postgres (triggers on SQLite). `GET /audit/verify` finds the first break.
- **E-signatures:** require a fresh, single-use re-authentication for the same subject, a stated meaning, and are bound to the record version's content hash. Authors cannot approve their own records.
- **Immutability:** locked versions never change; revisions go through change control.
- **AI governance:** the AI runs as its own principal. Regulated permissions are on a backend human-only allowlist, so approve/sign/triage endpoints return 403 to it whatever the orchestrator asks. Drafts are labeled, cite source records, and adoption by a human is audited.
- **Auth:** Supabase JWTs verified against the project JWKS (ES256/RS256/EdDSA) with issuer check; legacy HS256 only if a secret is configured. Production refuses to start with the dev secret.

## Repository layout

```
backend/
  app/{core,modules,api,workers}/   application code
  migrations/versions/              Alembic: schema, RLS policies, append-only grants
  tests/                            pytest suite (SQLite + real Postgres)
.github/workflows/ci.yml            import-linter + pytest against a Postgres service
```

## Running it

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
lint-imports && pytest -q                      # SQLite
```

Run the suite against real Postgres as a non-owner role under RLS (a superuser URL; the tests create `veraplex_test` and the `veraplex_app` role):

```bash
VERAPLEX_TEST_PG_URL='postgresql+psycopg://postgres:postgres@localhost:5432/postgres' pytest -q
```

Configuration is via `VERAPLEX_*` environment variables (`backend/app/core/config.py`): `DATABASE_URL`, `ENVIRONMENT`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_KEY`, and the rule parameters (recurrence window, training due days, ...). Apply the schema with Alembic (`alembic upgrade head`) and create the `veraplex_app` role first; connect the app as that role.

## API at a glance (`/api/v1`)

| Area | Endpoints |
|---|---|
| Deviations | `POST/GET /deviations`, `POST /deviations/{id}/triage`, `.../investigation`, `.../capas`, `.../ai-draft` |
| Investigations | `PUT /investigations/{id}`, `POST .../complete` (e-sign) |
| CAPA | `GET /capas/{id}`, `.../submit`, `.../sign`, `.../transition/{state}`, `.../change-controls` |
| SOPs | `POST/GET /sops`, `.../revisions`, `/sop-revisions/{id}/{submit,sign,approve,make-effective}`, `/sops/reminders` |
| Training | `GET /me/training`, `POST /training/{id}/acknowledge` (re-auth) |
| AI | `POST /ai-drafts/{id}/adopt` |
| Audit | `GET /audit/events`, `GET /audit/verify` |
| Admin | `POST /admin/users`, `PATCH /admin/users/{id}`, `GET /admin/users` |

## Known gaps

- **Auth and invites** are tested with generated keys, not a live Supabase project. The Supabase invite call is untested against the real Admin API.
- **Managed Postgres** specifics (Supabase roles, pooler transaction mode with `set_config(..., true)`) are unverified. `membership` is deliberately outside RLS because the tenant is derived from it.
- **No real LLM.** `StubModelProvider` returns a deterministic skeleton. LangGraph, the model gateway and pgvector SOP search are not built.
- **AI draft adoption** is audited but not separately e-signed; the human signs when completing the investigation.
- **SOP control:** effective date is always "now"; no attachments/PDF rendering; reminders are a function/endpoint with no scheduler or notifications.
- **Risk-matrix cut-offs** (`quality/rules.py`) are provisional pending QA-lead sign-off.
- **Not built:** Expo client and offline capture, S3 documents, Celery jobs / transactional outbox, entitlements and billing, site-scoped roles, 3D views, the other modules.
- The requirements matrix (clause → control → test → evidence) is not generated yet.
