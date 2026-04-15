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

## Day 5
Done:
- Extended `evaluate_generation.py` to compare multiple checkpoints in one run and save ranking artifacts (`checkpoint_comparison.csv`, `checkpoint_metrics.json`, `checkpoint_ranking.md`).
- Added debug artifacts for failed generation runs, including raw decoded strings, token-id traces, invalid-reason counts, and top decoded token summaries.
- Fixed checkpoint/vocab resolution so evaluation matches vocab files to checkpoint metadata instead of relying on brittle filename heuristics.

Issues:
- The seeded Day 5 checkpoint comparison still shows 0% RDKit-valid molecules across the evaluated diabetes checkpoints in `day5_checkpoint_compare_seed42`.
- The older `genorova_diabetes_best.pt` can occasionally produce a rare valid molecule when paired with the correct 39-token vocab, but the result is unstable and not production-usable.

Next:
- Fix sequence-generation quality at the model/decoding level before trusting any generation ranking based on sparse accidental valid outputs.
- Prioritize BOS/EOS-aware decoding or a more generation-stable sequence objective over further UI work.

## Day 6
Done:
- Added safer trust messaging across the active API and frontend so outputs are framed as prototype computational research-support results rather than validated drug discoveries.
- Implemented explicit fallback behavior in the product flow so weak generation returns honest fallback molecules or an empty result instead of implying a fresh valid candidate.
- Hardened runtime checkpoint/vocab handling in `genorova/src/generate.py` to resolve vocab files by checkpoint metadata and stop on incompatibility instead of silently generating from an unloaded model.

Issues:
- Day 5 generation-quality findings still stand: valid de novo generation remains weak, so demo value currently comes more from scoring and analysis than from fresh molecule generation.
- Some legacy UI copy and internal field names still use `clinical_score` for compatibility even though the user-facing wording now presents it as a model score.

Next:
- Add BOS/EOS-aware sequence handling and generation-time validity checks before treating fresh generation as a trustworthy product capability.

## Day 7
Done:
- Added `VERSION_STATUS.md` to summarize what Genorova currently is, what works, what is partial, what is unsolved, and the safest demo workflows.
- Added `NEXT_ROADMAP.md`, `DEMO_SCRIPT.md`, and `PROJECT_SUMMARY.md` to package the project for demos, LinkedIn, incubator forms, and early founder conversations.
- Updated `README.md` so readers can quickly find the project status, roadmap, demo guide, and summary documents.

Issues:
- The main scientific blocker is unchanged: fresh de novo generation quality is still weak, with Day 5 evaluation showing essentially 0% RDKit-valid molecules across the compared seeded checkpoint runs.
- The current product is strongest as a computational analysis and trust-aware demo prototype, not yet as a reliable molecule generator.

Next:
- Improve sequence generation quality, then refresh the version-status and demo materials once validity improves materially.
