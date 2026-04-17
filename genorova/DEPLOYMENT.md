# Genorova AI Deployment Guide

This file describes the active prototype deployment path. Do not present this
deployment as a production-ready validated drug-discovery system.

## Active Deploy Path

Configured deployment is defined in the repository-root `render.yaml`:

- service root: `genorova`
- build path: build frontend, then install Python requirements
- start command: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
- health check: `GET /health`

The live application path is `genorova/src/api.py`, not the alternate backend
under `app/backend`.

## What The Deployment Delivers

- protected workspace with signup, login, logout, and `/auth/me`
- evidence-weighted candidate ranking
- scoring, explanation, comparison, and chat workflows
- runtime status via `/health` and `/ops/status`
- static frontend served by the FastAPI backend

## What The Deployment Does Not Prove

- experimental validation
- clinical efficacy
- reliable fresh molecule generation
- production-grade multi-tenant durability

## Required Environment Notes

- `VITE_API_BASE_URL` can remain empty for same-origin deployment
- `GENOROVA_LOG_LEVEL=INFO` is recommended
- auth storage defaults to a writable local app-data path on Windows, or temp storage elsewhere

## Pre-Deploy Checks

Run these before any external demo or deploy:

```bash
python -m pytest -q
python scripts/smoke_check.py
python scripts/runtime_backup.py backup
```

Then build the frontend:

```bash
cd app/frontend
npm run build
```

## Post-Deploy Checks

Verify:

- `GET /health`
- `GET /ops/status`
- signup, login, logout, and `/auth/me`
- one ranked-candidate chat prompt
- one known-molecule scoring request

## Degraded-State Notes

Current honest caveats:

- chat session context in `src.api` is process-memory only and does not survive restart
- generation may fall back to previously scored or comparator molecules
- SQLite remains acceptable for the current prototype but is not the long-term database strategy

## Source Of Truth

For the active external-facing package, use:

- `OPERATIONS_RUNBOOK.md`
- `data_room/`
- `DEMO_SCRIPT.md`
