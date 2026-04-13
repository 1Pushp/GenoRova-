# Genorova Backend MVP

This backend wraps the existing `genorova/src/api.py` logic and adds:

- `POST /chat`
- SQLite-backed lightweight conversation memory
- CORS for the frontend

Run locally:

```bash
cd app/backend
python -m uvicorn main:app --reload --port 8000
```
