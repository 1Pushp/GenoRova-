# Organic Chemistry Workspace

This workspace contains the Genorova codebase and Day 3 stabilization work.

## Testing

The baseline reliability suite uses `pytest` plus `httpx` for FastAPI's `TestClient`.

### Install test dependencies

```bash
python -m pip install pytest httpx
```

### Run all tests

```bash
python -m pytest
```

### Run one test file

```bash
python -m pytest tests/test_api.py
```

### Run in verbose mode

```bash
python -m pytest -v
```

The suite is intentionally small and fast:
- no large downloads
- no full training runs
- no GPU dependency
- minimal mocking around expensive or unstable paths
