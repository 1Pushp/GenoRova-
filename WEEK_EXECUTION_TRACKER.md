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

## Day 4
Done:
- Added `genorova/src/evaluate_generation.py` to evaluate generated batches with RDKit validity, uniqueness, novelty, property summaries, and active scoring summaries.
- Added reusable output artifacts for generation evaluation: `generated_molecules.csv`, `evaluation_metrics.json`, and `evaluation_summary.md`.
- Updated the root README with commands for running generation evaluation on the current checkpoint/vocabulary setup.

Issues:
- A real verification run against `genorova/outputs/models/diabetes/genorova_diabetes_pretrain_best.pt` produced 0% RDKit-valid molecules in the sampled batch, which is an important model-quality warning.
- Scoring summaries depend on valid RDKit molecules; when validity is 0, the score section is necessarily empty.

Next:
- Run the evaluator against additional checkpoints and compare validity/uniqueness/novelty before trusting any generation demo.
- Use the new evaluation outputs in future readiness reports instead of relying on training loss alone.
