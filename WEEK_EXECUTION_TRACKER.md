## Day 3
Done:
- Added a minimum pytest-based baseline test suite for data loading, preprocessing, API stats, chat, rendering, and training smoke coverage.
- Documented how to install `pytest` and `httpx`, plus how to run all tests, one file, and verbose mode from the project root.
- Added a lightweight training smoke test using small local samples and minimal mocking to protect the active training path.
- Fixed a real `/api/chat` reliability bug by defining the fallback `BEST_MOLECULE` constant used in conversation state.
- Ran the Day 3 suite in the project `venv`: 8 tests passed.

Issues:
- FastAPI test execution required `httpx`, which was not installed in the local `venv`.
- The training smoke test surfaces a real PyTorch scheduler-order warning in `train.py` (`lr_scheduler.step()` runs before `optimizer.step()`).
- Some active modules still contain legacy code paths, so tests intentionally target the current active architecture instead of every historical entrypoint.

Next:
- Consider fixing the scheduler-step ordering warning in `genorova/src/train.py`.
- Expand coverage around persistence/report generation only after the active Day 3 baseline stays stable.
