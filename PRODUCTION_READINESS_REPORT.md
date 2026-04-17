# Genorova AI Production Readiness Report

**Updated audit date:** 2026-04-15  
**Baseline compared against:** April 14 audit  
**Scope for this refresh:** only changes that materially affect production readiness

> **Updated verdict:** Improved prototype, still not production-ready.  
> The biggest improvement is that the training code now has a real MOSES-backed path and `scorer.py` is no longer a stub file. The biggest remaining blocker is still scientific validity: reported "binding affinity" is still a heuristic formula labeled as kcal/mol, not docking.

---

## 1. Delta Summary Since April 14

| Area | April 14 status | Current status | Net |
|---|---|---|---|
| Dependency pinning | Flagged as needing verification | Root `requirements.txt` now uses exact pins; `genorova/requirements.txt` delegates to root | Improved |
| KL annealing in `train.py` | Reported fixed but runtime path was unclear | Still fixed; live entrypoint uses warmup to 0.5 | Confirmed |
| `/api/stats` | Reported fixed in backend shell | Confirmed live-query implementation exists in both `genorova/src/api.py` and `app/backend/main.py` | Confirmed |
| `MINI_DATASET` blocker | Unverified whether real data path was active | New `data_loader.py` + `train.py` runtime path solve this for direct training runs | Partially improved |
| `scorer.py` | Reported as all stubs | File now contains implemented scoring functions | Major improvement |

---

## 2. Day-1 Fix Verification

| Fix requested on April 14 | Current finding | Evidence |
|---|---|---|
| `requirements.txt` version fixes | Confirmed. Root file is exact-pinned; `genorova/requirements.txt` is just `-r ../requirements.txt`. | `requirements.txt`; `genorova/requirements.txt` |
| KL annealing schedule in `train.py` | Confirmed. Warmup constants are still `KL_WEIGHT_TARGET = 0.5` and `KL_WARMUP_EPOCHS = 50`. The active runtime entrypoint is `main_realdata()`. | `genorova/src/train.py:77`; `genorova/src/train.py:78`; `genorova/src/train.py:1455` |
| Live `/api/stats` queries in both APIs | Confirmed. Both implementations query SQLite first, then fall back to CSV-derived aggregates. | `genorova/src/api.py:407`; `genorova/src/api.py:428`; `genorova/src/api.py:441`; `app/backend/main.py:106`; `app/backend/main.py:126`; `app/backend/main.py:142`; `app/backend/main.py:206` |

**Important nuance:** `genorova/src/api.py` still hardcodes `best_molecule` and `best_score` in `/health`, even though `/api/stats` is now live. That is not a regression in the requested fix, but it is still a data-integrity issue. Evidence: `genorova/src/api.py:277`, `genorova/src/api.py:302`, `genorova/src/api.py:303`.

---

## 3. New `data_loader.py` Assessment

| Question | Finding |
|---|---|
| What does `genorova/src/data_loader.py` now do? | It now has a modern dataset loader that can download/cache MOSES, load a ChEMBL subset, strip empties, de-duplicate SMILES, filter by length, validate with RDKit, canonicalize via `Chem.MolToSmiles(..., canonical=True)`, and attach load stats in `df.attrs["load_stats"]`. |
| Does it solve blocker #2 (`MINI_DATASET`)? | **Partially yes.** It solves it for the direct training entrypoint in `train.py`, because `main_realdata()` calls `load_smiles_dataset(dataset_name="moses")`. |
| Is the blocker fully gone systemwide? | **No.** `run_pipeline.py` still uses a separate path that trains from disease CSVs in `genorova/data/raw/diabetes_molecules.csv` and `infection_molecules.csv`, not from the new MOSES loader. So the "toy dataset" risk is gone for `train.py` runs, but the end-to-end pipeline is still split across two training paths. |

### Evidence

| Evidence point | File |
|---|---|
| MOSES downloader exists | `genorova/src/data_loader.py:471` |
| New dataset loader exists | `genorova/src/data_loader.py:528` |
| Deduplication exists | `genorova/src/data_loader.py:554` |
| Canonicalization exists | `genorova/src/data_loader.py:573` |
| Loader stats attached | `genorova/src/data_loader.py:581` |
| `train.py` imports new loader | `genorova/src/train.py:1150` |
| `train.py` defaults to MOSES | `genorova/src/train.py:1244` |
| `train.py` active entrypoint is `main_realdata()` | `genorova/src/train.py:1455` |
| `run_pipeline.py` still trains from disease CSVs | `genorova/src/run_pipeline.py:871`; `genorova/src/run_pipeline.py:886` |

---

## 4. Re-ranked Top 5 Blockers

| Rank | Blocker | Why it is still blocking production |
|---|---|---|
| 1 | Scientific validity: "binding affinity" is still a heuristic mislabeled as kcal/mol | `validate.py` explicitly says the implementation is a simplified heuristic and "in real system, use proper docking." This remains the highest-risk credibility issue. Evidence: `genorova/src/validate.py:409`, `genorova/src/validate.py:428`, `genorova/src/validate.py:429`, `genorova/src/validate.py:656`. |
| 2 | Training/data path is still split | `train.py` is now MOSES-backed, but `run_pipeline.py` still uses disease CSVs. That means the repo has two materially different training stories, and the production pipeline is not aligned with the improved loader. |
| 3 | No real test or CI safety net | I found no project test suite, no `pytest` config, and no `.github` workflow directory in the workspace. That keeps regressions invisible and blocks trustworthy deployment. |
| 4 | API security hardening is still absent | `app/backend/main.py` still has `allow_origins=["*"]`, no auth, and no rate limiting. That remains unacceptable for any external exposure. Evidence: `app/backend/main.py:39`. |
| 5 | Response integrity still includes hardcoded/stale values outside `/api/stats` | `genorova/src/api.py` still hardcodes `best_molecule` and `best_score` in `/health`, which undermines trust in the live-stat work and creates conflicting truths across endpoints. Evidence: `genorova/src/api.py:302`; `genorova/src/api.py:303`. |

### What dropped out of the old top 5

| Old blocker | New status |
|---|---|
| `scorer.py` is 100% stub functions | Resolved enough to remove from top blockers. Implemented functions now exist for Lipinski, QED, SA score, novelty, clinical score, reporting, and ranking. |
| MOSES integration unverified at runtime | No longer true for direct `train.py` execution. It is now a narrower split-training-path issue rather than a total unknown. |

---

## 5. Updated Maturity Verdict

| Dimension | April 14 view | Current view |
|---|---|---|
| ML/training readiness | Good bones, dataset integration unverified | Better. Direct training path is now real-data backed and seeded. |
| Scientific validity | Weak | Still weak. No meaningful improvement on affinity/docking claims. |
| Codebase coherence | Weak due to stub scorer + duplicate paths | Improved, but still fragmented because old and new paths coexist in `train.py`, `data_loader.py`, and `run_pipeline.py`. |
| Production hardening | Weak | Unchanged: no auth, no rate limiting, no CI, no tests. |

| Final call | Status |
|---|---|
| Ready for external users | No |
| Ready for internal experimentation | Yes, with explicit scientific caveats |
| Current maturity label | Improved prototype / pre-production alpha |

**Bottom line:** the April 14 report was too pessimistic about `scorer.py` and too uncertain about the direct training path. The project has improved. But it is still not production-ready because the science claims are overstated, the pipeline is split between old and new data paths, and the deployment surface is still unsecured and untested.

---

## 6. Recommended Next Moves

| Priority | Action |
|---|---|
| 1 | Unify on one training path: either make `run_pipeline.py` call the new MOSES-backed loader/train flow or delete the duplicate training implementation. |
| 2 | Rename current affinity output to a heuristic label immediately, or wire real docking into validation before any external demo. |
| 3 | Add a minimal test suite plus CI before further architectural changes. |
| 4 | Lock down backend exposure: restricted CORS, API auth, and rate limiting. |
| 5 | Remove remaining hardcoded `best_molecule` values from `/health` and any chat defaults that imply live truth. |

---

*This refresh is based on static inspection of the current workspace on 2026-04-15. I did not run full training, endpoint smoke tests, or docking jobs in this pass.*
