# GenorovaAI Operations Runbook

GenorovaAI is still a prototype research-support platform, not a fully production-grade system. This runbook is the lightweight reliability layer for demo-safe deploys.

## Current Scope

What is hardened today:
- Fast API health and runtime status endpoints
- cookie-based auth sessions backed by SQLite
- fast pre-deploy smoke checks
- explicit logging for startup, auth, degraded generation, and failing routes
- copy-based backup and restore for important runtime files

What remains prototype-grade:
- chat session state in `genorova/src/api.py` is process-memory only
- no external metrics stack or alerting service
- no managed database, queue, or object storage
- no automatic scheduled backups yet

## Quick Commands

Run the fast backend test suite:

```bash
python -m pytest -q
```

Run the pre-deploy smoke suite:

```bash
python scripts/smoke_check.py
```

Build the canonical frontend:

```bash
cd app/frontend
npm run build
```

Create a runtime backup bundle:

```bash
python scripts/runtime_backup.py backup
```

Restore from a backup bundle:

```bash
python scripts/runtime_backup.py restore backups/<bundle>/manifest.json --force
```

## Health And Status Endpoints

### `GET /health`

Use this for a fast liveness check. It now reports:
- service status
- model file presence
- molecule count
- best ranked molecule summary
- `health_status`
- `degraded_states`
- storage summary for auth, molecule DB, frontend build, and chat-session mode

### `GET /ops/status`

Use this for runtime inspection before or after a deploy. It reports:
- startup state and startup warnings
- auth storage status
- molecule DB status
- frontend build status
- report availability
- chat-session durability
- recommended operator actions

## Logging Expectations

The API emits structured JSON-style log lines for the most important operational events:
- `startup_complete`
- `auth_signup_success`
- `auth_signup_conflict`
- `auth_login_success`
- `auth_login_failed`
- `auth_logout`
- `request_result` for 4xx and 5xx responses
- `request_exception` for uncaught failures
- `generate_degraded_result` when generation falls back or returns no trustworthy candidate
- `score_validation_error`
- `score_unexpected_error`
- `chat_request_failed`

Set log verbosity with:

```bash
GENOROVA_LOG_LEVEL=INFO
```

## Degraded States To Watch

The live API can now surface these states clearly:
- `auth_storage_unavailable`
- `cookie_secure_disabled`
- `frontend_dist_missing`
- `molecule_catalog_unavailable`

Important note:
- `genorova/src/api.py` uses process-memory chat session state. That is expected to be ephemeral across restarts and should be explained honestly during demos.

## Backup And Restore

The backup script captures:
- auth DB
- molecule DB
- generated output directory
- HTML report
- optional file-backed chat-memory DB if one exists

It also copies SQLite sidecar files when present:
- `-wal`
- `-shm`
- `-journal`

What it does not back up:
- in-memory chat session state from `genorova/src/api.py`

Recommended backup timing:
- before a deploy
- before a live demo
- before large data regeneration runs

## Pre-Deploy Checklist

1. Run `python -m pytest -q`.
2. Run `python scripts/smoke_check.py`.
3. Run `npm run build` inside `app/frontend`.
4. Run `python scripts/runtime_backup.py backup`.
5. Confirm `/health` reports no unexpected degraded state.
6. Confirm `/ops/status` shows auth storage available and frontend built.
7. Verify `render.yaml` still points at `genorova/src/api.py` and `healthCheckPath: /health`.

## Post-Deploy Verification

1. Open `/health` and confirm `status=running`.
2. Open `/ops/status` and review `degraded_states`.
3. Confirm signup, login, `/auth/me`, and logout on the live instance.
4. Run one score request.
5. Run one ranked-candidate prompt through chat.
6. Confirm logs show startup success and no unexpected 5xx route failures.

## Demo-Safe Fallback Notes

If generation falls back:
- say so explicitly
- show the trust payload and validation ledger
- do not present fallback molecules as fresh discoveries

If auth storage fails:
- treat the deploy as degraded
- do not run private-account demos until fixed

If frontend build is missing:
- do not present the deployment as a full product experience

