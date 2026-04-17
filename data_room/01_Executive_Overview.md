# GenorovaAI - Executive Overview

Date: April 17, 2026

## What GenorovaAI Is

GenorovaAI is a prototype computational research-support platform for molecule
scoring, explanation, comparison, and guarded chat-based analysis. The current
product combines:

- a FastAPI backend served from `genorova/src/api.py`
- a React frontend served through the same deployment
- authenticated user sessions and a protected workspace
- a molecule scoring and reporting workflow
- a generation pipeline that is still under active stabilization

## What GenorovaAI Is Not

GenorovaAI should not currently be described as:

- an experimentally validated drug-discovery engine
- a clinical decision tool
- proof of biological activity or safety
- a production-ready platform for regulated use

## Current Snapshot

Complete:

- live full-stack application structure with one canonical frontend entrypoint
- signup, login, logout, session cookies, and `/auth/me`
- protected workspace and authenticated chat flow
- scoring of valid SMILES strings with structured outputs
- explanation, comparison, and trust/limitations messaging
- baseline backend and frontend verification

Partial:

- runtime generation workflow
- user-specific conversation continuity beyond the current deployment instance
- external monitoring and alerting beyond local logs/status
- scientific validation reporting consistency across older repo artifacts

Pending:

- reliable de novo generation quality
- billing and subscription workflows
- external monitoring and alerting stack
- wet-lab validation and external scientific confirmation

## Evidence Used For This Room

This room is based on the most conservative, current project state:

- `README.md`
- `VERSION_STATUS.md`
- `PROJECT_SUMMARY.md`
- `NEXT_ROADMAP.md`
- `DEMO_SCRIPT.md`
- `OPERATIONS_RUNBOOK.md`
- `render.yaml`
- `genorova/docs/scientific_limitations.md`
- current `genorova/src/api.py`, `genorova/src/auth_store.py`, and active frontend
- local verification on April 17, 2026:
  - `venv\\Scripts\\python.exe -m pytest -q` -> `22 passed`
  - `venv\\Scripts\\python.exe scripts\\smoke_check.py` -> passed
  - `npm run build` in `app/frontend` -> passed

## Standardized Positioning Statement

Use this wording consistently:

"GenorovaAI is a prototype computational research-support platform. Its
strongest workflows today are ranked candidate review, molecule scoring,
explanation, comparison, and responsible trust messaging inside an
authenticated web product. Outputs are computational, heuristic, and proxy
signals only. They are not experimental proof, clinical validation, or
evidence of drug efficacy."
