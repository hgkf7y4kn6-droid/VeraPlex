# VeraPlex

A compliance-first pharmaceutical intelligence platform. The first vertical slice is **Quality**: deviation → investigation → CAPA → SOP change control, with an AI assistant that drafts and never decides.

Built from the *Pharmaceutical Intelligence Platform — Build Plan*. It is greenfield: the reference repositories in the plan's Phase 1 were never supplied.

> **Not validated.** Nothing in this repository makes a product Part 11 / Annex 11 compliant or GxP-validated. That requires customer-specific validation, procedures and independent review. See [Known gaps](#known-gaps).

## Architecture

A single FastAPI **modular monolith** (`backend/`). Modules own their tables and may import only modules below them; `import-linter` enforces this in CI.

```
ai          Quality agent: non-human principal, SOP-grounded drafts via Claude (opt-in) or local, citation validation
admin       user provisioning (Supabase invite), role changes, deactivation
quality     deviation, investigation, CAPA, change control, deterministic risk + recurrence rules
documents   SOPs as controlled revisions, training assignment, acknowledgments, reminders, search over effective SOPs
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
mobile/                            Expo client: offline deviation capture, durable outbox, idempotent sync
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

## AI drafting and SOP search

1. `GET /sops/search` ranks passages of **effective** SOP revisions only (a superseded or draft revision is never returned). Passages are indexed when a revision becomes effective; `POST /sops/reindex` rebuilds after an embedder change.
2. `POST /deviations/{id}/ai-draft` runs the Quality agent as the tenant's AI principal: it reads the deviation, prior events on the same equipment and SOP passages (each needs the AI principal's own permissions), then drafts a 5-Whys and fishbone.
3. **Tenants opt in** to sending content to an outside model (`PUT /admin/tenant/ai-settings`, admin only, audited). Without it, or without an API key, the deterministic local provider runs and nothing leaves the system.
4. With opt-in, Claude (`claude-opus-5-5` by default, `VERAPLEX_AI_MODEL`) is called through the official SDK with a JSON-schema-constrained reply. Record text is HTML-escaped inside `<source>` tags and the system prompt treats it as untrusted data.
5. **Output is never trusted:** citations must name a supplied source id; invented ones are dropped, and claims left without support are flagged `unsupported` and downgraded to `insufficient_evidence`. Each run stores provider, model, prompt version, sources, tokens and cost; a per-tenant daily token budget applies.

Embeddings: `VERAPLEX_EMBEDDING_URL` points at a Hugging Face text-embeddings-inference server; unset, an offline lexical hashing embedder is used (scores 8/8 recall@3 on the small fixed eval in `tests/test_sop_search.py`; it is lexical, not semantic).

## Mobile (Expo)

`mobile/` captures deviations offline. Saves go to a durable on-device outbox first; a sync engine sends them with an `Idempotency-Key` (so a lost response or app kill can never create a duplicate), backs off on network/5xx errors, pauses on 401, and marks validation/permission rejections as failed for the user to fix. Client-reported times are stored as claims; the server stamps authoritative time.

```bash
cd mobile && npm ci
npm run typecheck && npm test      # sync-engine unit tests
npm run e2e                        # boots the real backend and runs the sync engine against it
cp .env.example .env && npx expo start
```

## Benchmark

`backend/benchmarks/` is a synthetic, seeded pharma benchmark (retrieval, grounded drafting incl. unanswerable cases, prompt injection, noisy extraction) with provisional Tier 2 gates. `python -m benchmarks.run --check` runs offline in CI; `--draft anthropic` scores a real model. See [`backend/benchmarks/README.md`](backend/benchmarks/README.md) for methodology, baselines and limitations. The labels are unreviewed by any domain expert.

## API at a glance (`/api/v1`)

| Area | Endpoints |
|---|---|
| Deviations | `POST/GET /deviations`, `POST /deviations/{id}/triage`, `.../investigation`, `.../capas`, `.../ai-draft` |
| Investigations | `PUT /investigations/{id}`, `POST .../complete` (e-sign) |
| CAPA | `GET /capas/{id}`, `.../submit`, `.../sign`, `.../transition/{state}`, `.../change-controls` |
| SOPs | `POST/GET /sops`, `GET /sops/search`, `.../revisions`, `/sop-revisions/{id}/{submit,sign,approve,make-effective}`, `/sops/reminders` |
| Training | `GET /me/training`, `POST /training/{id}/acknowledge` (re-auth) |
| AI | `POST /ai-drafts/{id}/adopt` |
| Audit | `GET /audit/events`, `GET /audit/verify` |
| Admin | `POST /admin/users`, `PATCH /admin/users/{id}`, `GET /admin/users`, `PUT /admin/tenant/ai-settings`, `GET /me` |

## Known gaps

- **Auth and invites** are tested with generated keys, not a live Supabase project. The Supabase invite call is untested against the real Admin API.
- **Managed Postgres** specifics (Supabase roles, pooler transaction mode with `set_config(..., true)`) are unverified. `membership` is deliberately outside RLS because the tenant is derived from it.
- **AI drafting** is tested with a fake Anthropic client, not a live call; the real request shape follows the SDK docs but has not been exercised. No server-side refusal fallback is configured (a refusal returns 502). Quality of Claude's 5-Whys on real pharma data is unevaluated: a first synthetic benchmark exists but has never been run against a real model, and its labels are unreviewed. Prices in config are cached values; confirm before billing.
- **SOP search** brute-forces cosine in Python over a tenant's chunks (fine at pilot scale; pgvector is the upgrade path). The TEI embedder is untested against a live server. No reranker.
- **Mobile:** UI is untested on a device or simulator (typecheck, unit tests and an e2e of the sync engine only). No photo capture, no push, and plain state navigation instead of Expo Router. A deviation edited server-side while a device is offline has no conflict UI (creation is conflict-free by idempotency).
- **AI draft adoption** is audited but not separately e-signed; the human signs when completing the investigation.
- **SOP control:** effective date is always "now"; no attachments/PDF rendering; reminders are a function/endpoint with no scheduler or notifications.
- **Risk-matrix cut-offs** (`quality/rules.py`) are provisional pending QA-lead sign-off.
- **Not built:** photos/S3 documents, Celery jobs / transactional outbox, entitlements and billing, site-scoped roles, 3D views, the other modules.
- The requirements matrix (clause → control → test → evidence) is not generated yet.
