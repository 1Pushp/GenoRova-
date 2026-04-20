# Genorova Backend

This is the canonical deployment entrypoint for Genorova.

It reuses the core implementation from `genorova/src/api.py` and adds:

- `POST /chat`
- SQLite-backed lightweight conversation memory
- CORS for the frontend

Run locally from the repository root:

```bash
python -m uvicorn app.backend.main:app --reload --port 8000
```
