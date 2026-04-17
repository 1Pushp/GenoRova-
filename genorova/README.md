# Genorova AI

Prototype computational research-support platform for molecule ranking,
scoring, explanation, comparison, and conservative report generation.

## Current Product Position

Use this framing consistently:

- active workflow: diabetes / DPP4 / sitagliptin comparator
- strongest product areas: ranked candidate review, scoring, explanation, comparison, protected workspace
- weakest product area: fresh molecule generation
- output type: computational, heuristic, and proxy signals only
- not: experimental proof, clinical validation, or production-ready biotech software

## What This Repo Contains

- FastAPI application in `genorova/src/api.py`
- React frontend in `app/frontend`
- auth/session foundation for a protected workspace
- evidence-weighted candidate ranking and validation ledger
- model-training and evaluation code for the broader research repo
- conservative HTML reporting

## Best External Demo Workflows

- show the ranked candidate set for the active diabetes workflow
- explain the best molecule simply
- score a known molecule such as `CCO`
- compare or optimize within the current trust boundaries

## Important Limitations

- generation remains the weakest scientific area and should not be framed as reliable de novo discovery
- fallback molecules and ranked outputs are still computational product outputs, not validated leads
- some older files in the repo reflect broader historical scope and should not override the active external-facing package

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API:

```bash
cd genorova
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

Build the frontend:

```bash
cd app/frontend
npm install
npm run build
```

Run the smoke suite:

```bash
python scripts/smoke_check.py
```

## Key Docs

- `README.md` in the repo root for testing and operations links
- `OPERATIONS_RUNBOOK.md` for deploy checks, runtime visibility, and backup/restore
- `data_room/` for the current external-facing diligence package
- `DEMO_SCRIPT.md` for the safe 3-5 minute walkthrough

## Short Description

"GenorovaAI is a prototype computational research-support platform that helps
users rank, score, explain, and compare candidate molecules while keeping
scientific limitations explicit."
