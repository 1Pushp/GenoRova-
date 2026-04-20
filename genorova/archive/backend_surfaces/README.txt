Archived deployment surface
===========================

As of 2026-04-20, `genorova/src/api.py` is no longer the public deployment
entrypoint for Genorova.

Canonical backend:
- `app/backend/main.py`

What remains in `genorova/src/api.py`:
- the core FastAPI route implementation
- internal helpers reused by tests and report generation
- backward-compatible imports during the transition

What changed:
- Render and local production startup should target `app/backend/main.py`
- `src/api.py` should be treated as an internal core module, not the deploy target
