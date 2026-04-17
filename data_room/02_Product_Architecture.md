# GenorovaAI - Product Architecture

Date: April 17, 2026

## Active System Topology

Configured deployed path:

- frontend source: `app/frontend`
- frontend production bundle: built by Vite and served by FastAPI
- deployed backend entrypoint: `genorova/src/api.py`
- Render start command: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`

Important repo note:

- `app/backend` exists as a secondary backend path and contains useful
  reliability work, but it is not the configured Render entrypoint today.
- The diligence narrative in this room is based on the deployed path above.

## Frontend

Canonical app shell:

- `app/frontend/src/App.jsx`
- `app/frontend/src/GenorovaChatAppV11.jsx`
- `app/frontend/src/auth.jsx`

Current frontend responsibilities:

- boot authenticated session state from `/auth/me`
- show login and signup flow
- gate the protected workspace when unauthenticated
- submit scoring and chat requests to the backend
- present trust messaging that labels outputs as computational and non-clinical

## Backend

Primary backend responsibilities in `genorova/src/api.py`:

- serve the frontend bundle
- expose public API routes such as stats and scoring
- expose auth endpoints:
  - `POST /auth/signup`
  - `POST /auth/login`
  - `POST /auth/logout`
  - `GET /auth/me`
- protect the chat workspace behind authenticated sessions
- provide computational analysis routes for scoring, chat, reports, and
  validation

## Auth and Session Model

Auth implementation:

- user records and session records are stored in SQLite
- password hashing is performed with PBKDF2-HMAC
- the frontend uses a cookie-backed authenticated session
- the auth database path is configurable with `GENOROVA_AUTH_DB_PATH`
- default auth storage prefers a local writable application path on Windows

What is complete:

- account creation
- login and logout
- cookie session persistence across refresh
- `/auth/me` bootstrap
- protected chat access

What is still partial:

- conversation context is protected, but not yet a full durable multi-device
  user history product
- role/permission models are intentionally not implemented yet

## Data Stores

Active stores:

- auth SQLite database for users and sessions
- file-backed molecule database used by the Genorova backend
- deployment-local in-memory chat context for the protected workspace

Operational caution:

- file-backed SQLite inside OneDrive-backed paths can trigger disk I/O issues in
  this environment
- this room therefore avoids claiming hardened database operations beyond the
  current prototype scope

## Public vs Protected Product Surfaces

Public:

- landing/product framing
- platform stats
- safe scientific positioning

Protected:

- workspace chat
- authenticated session handling
- user-only interactive analysis flow

## Current Architecture Bottom Line

GenorovaAI now has a coherent full-stack product shape: one frontend, one
configured deployment backend, and a real auth/session foundation. The system
is suitable for demos, advisor review, and early product diligence, but it
still needs stronger persistence, ops hardening, and scientific evidence before
being presented as a mature SaaS platform.
