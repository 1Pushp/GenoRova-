# GenorovaAI - Deployment and Ops

Date: April 17, 2026

## Current Deployment Shape

Configured deployment is defined in `render.yaml`:

- service type: Render web service
- service root: `genorova`
- build command:
  - `cd ../app/frontend && npm ci && npm run build`
  - `cd ../../genorova && pip install -r requirements.txt`
- start command:
  - `uvicorn src.api:app --host 0.0.0.0 --port $PORT`

This means the active deployed application is the FastAPI app in
`genorova/src/api.py`, not the alternate backend under `app/backend`.

## Frontend Delivery Model

- frontend is built with Vite
- build output is served by the FastAPI backend
- local development proxies `/api` and `/auth` to `http://localhost:8000`

## Session And Auth Operations

- authenticated sessions are cookie-based
- user and session records are stored in a dedicated SQLite auth database
- auth storage path can be overridden with `GENOROVA_AUTH_DB_PATH`
- default auth storage prefers a local writable app-data path on Windows

## Current Operational Strengths

- one coherent deployment path is now defined
- auth foundation exists for a multi-user product direction
- frontend build currently passes
- backend test suite currently passes
- smoke-check script exists for pre-deploy verification
- `/health` and `/ops/status` expose runtime and degraded-state visibility
- backup and restore workflow exists for core runtime files

## Current Operational Risks

- SQLite files inside OneDrive-backed or reparse-point-heavy paths can produce
  disk I/O failures
- the molecule database is still file-backed SQLite, which is fine for a
  prototype but not a mature multi-tenant SaaS posture
- public uptime was not independently re-verified in this data room
- chat state in `genorova/src/api.py` is still process-memory only
- monitoring and alerting are still local/lightweight rather than production-grade

## What Is Complete

- Render configuration exists
- backend and frontend build path is defined
- protected sessions exist
- local verification is available through tests and frontend build
- runtime status reporting exists
- backup and restore procedure exists

## What Is Partial

- durable user-bound history and report storage
- ops visibility and incident response
- environment hardening around file-backed SQLite
- backup process is manual rather than automated

## What Is Pending

- billing and quota enforcement
- formal logging and alerting stack
- stronger database strategy for long-term multi-user usage
- durable chat/history storage beyond restart

## Deployment Bottom Line

GenorovaAI has a deployable prototype path and a verifiable build/test baseline.
It should be described as a working prototype deployment, not as a fully
hardened production service.
