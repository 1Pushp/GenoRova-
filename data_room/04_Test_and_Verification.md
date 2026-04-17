# GenorovaAI - Test and Verification

Date: April 17, 2026

## Verification Performed For This Data Room

Backend and test suite:

- command run: `venv\\Scripts\\python.exe -m pytest -q`
- result: `17 passed, 9 warnings`

Frontend build:

- command run: `npm run build` in `app/frontend`
- result: passed

## What The Current Tests Cover

- auth signup, login, logout, and `/auth/me`
- unauthorized access checks for protected chat
- backend chat-memory startup fallback behavior
- API stats behavior
- data loading and preprocessing paths
- training smoke coverage

## Current Warning-Level Issues

Observed during the latest test run:

- FastAPI `on_event` deprecation warnings in the backend startup path
- a PyTorch learning-rate scheduler ordering warning in `train.py`

These warnings do not break the current test suite, but they should be cleaned
up in the next engineering pass.

## What Has Been Verified Functionally

Supportable statements:

- the backend test suite passes locally
- the frontend production bundle builds successfully
- auth and protected chat behavior have automated coverage
- the current repo can support demo and diligence workflows without claiming
  scientific proof

## What Has Not Been Verified In This Room

Not independently verified here:

- public Render uptime from an external URL
- wet-lab or assay results
- clinical outcomes
- universally reliable file-backed SQLite behavior on OneDrive-backed paths

## Known Environment Risk

During this audit, direct access to the file-backed molecule SQLite store hit a
`disk I/O error` in the local OneDrive-backed environment. That does not undo
the current passing test suite, but it is a real operational caution for any
SQLite file that lives in a synced or reparse-point-heavy path.

## Verification Bottom Line

The current codebase has a real, passing software baseline. The strongest
evidence is product and engineering reliability, not scientific validation.
