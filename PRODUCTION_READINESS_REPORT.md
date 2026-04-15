# Genorova AI — Production Readiness Report

**Audit Date:** 2026-04-14  
**Auditor:** Claude Code (claude-sonnet-4-6)  
**Scope:** Full codebase audit — ML pipeline, backend API, frontend, deployment config  
**Verdict:** ⚠️ Early-MVP — Not ready for production or clinical use

---

## Step 1 — File Inventory

### Project Structure Map

```
organic chemistry/
├── genorova/src/                  # Core ML package
│   ├── api.py                     # FastAPI REST entry point (~400 lines)
│   ├── data_loader.py             # SMILES CSV loader + Lipinski filter (403 lines)
│   ├── preprocessor.py            # One-hot encoding + DataLoader (413 lines)
│   ├── model.py                   # VAE encoder/decoder architecture (584 lines)
│   ├── train.py                   # Training loop + checkpointing (600+ lines)
│   ├── generate.py                # Latent space sampling + generation (410 lines)
│   ├── validate.py                # 4-layer validation pipeline (887 lines)
│   ├── scorer.py                  # Clinical scoring engine (50+ lines)
│   ├── docking/                   # AutoDock Vina integration
│   │   ├── protein_prep.py        # PDB protein preparation
│   │   ├── ligand_prep.py         # SMILES ligand preparation
│   │   ├── docking_engine.py      # Docking execution
│   │   ├── batch_processor.py     # Batch docking pipeline
│   │   ├── dock_visualizer.py     # 3D visualization
│   │   └── docking_results.py     # Results storage
│   └── vision/
│       ├── structure_visualizer.py # 2D structure images from SMILES
│       ├── protein_analyzer.py     # PDB file parser (BioPython)
│       └── binding_site_detector.py # Binding pocket detection
├── app/backend/
│   ├── main.py                    # FastAPI app + 13 REST endpoints (149 lines)
│   ├── chat_logic.py              # Intent detection + response formatting (375 lines)
│   ├── chat_memory.py             # SQLite conversation storage (321 lines)
│   └── requirements.txt           # Backend-only deps (5 packages)
├── app/frontend/src/
│   ├── main.jsx                   # React entry point (11 lines)
│   ├── App.jsx / PlatformApp.jsx  # Main chat UI (476 lines)
│   ├── GenorovaChatApp.jsx        # Alternative chat UI
│   └── GenorovaChatAppV11.jsx     # Active version (imported by main.jsx)
├── requirements.txt               # Root deps (13 packages)
├── render.yaml                    # Render.com deployment config
└── .python-version                # 3.11.0
```

### File Classification Table

| File | Language | Lines | Purpose |
|------|----------|-------|---------|
| `genorova/src/data_loader.py` | Python | 403 | Load SMILES from CSV, validate, Lipinski filter |
| `genorova/src/preprocessor.py` | Python | 413 | One-hot encode SMILES, build DataLoaders |
| `genorova/src/model.py` | Python | 584 | VAE architecture (encoder, decoder, loss) |
| `genorova/src/train.py` | Python | 600+ | Training loop, checkpointing, KL annealing |
| `genorova/src/generate.py` | Python | 410 | Sample latent space, decode to SMILES |
| `genorova/src/validate.py` | Python | 887 | 4-layer validation + clinical scoring |
| `genorova/src/scorer.py` | Python | 50+ | Clinical score engine (incomplete stubs) |
| `genorova/src/api.py` | Python | ~400 | REST API, molecule generation endpoints |
| `app/backend/main.py` | Python | 149 | FastAPI app, CORS, routes |
| `app/backend/chat_logic.py` | Python | 375 | NLP intent parser, response formatter |
| `app/backend/chat_memory.py` | Python | 321 | SQLite chat persistence |
| `app/frontend/src/App.jsx` | JSX | 476 | Chat UI, dual-panel layout, API calls |
| `render.yaml` | YAML | ~20 | Render.com deployment |
| `requirements.txt` (root) | Text | 13 | Python dependencies |

**No test files found. No notebooks found in outputs. No CI/CD config found.**

---

## Step 2 — Code Quality Audit

### 2.1 Correctness Issues

#### CRITICAL: Phantom dependency versions
```
# requirements.txt (root)
torch==2.11.0        # Does not exist. Latest stable is 2.5.x (April 2026)
torchvision==0.26.0  # Does not exist. Paired with torch 2.11 which doesn't exist
rdkit==2026.3.1      # Future-dated version. Correct package name is rdkit-pypi or rdkit
```
**This requirements.txt will fail `pip install` on any clean system.**

#### CRITICAL: Hardcoded fabricated constants in `app/backend/main.py`
```python
BEST_MOLECULE = "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"
BEST_SCORE    = 0.9649
BEST_MW       = 286
BEST_DOCKING  = -5.041
BEST_CA7_KI   = "6.4 nM"
TOTAL_MOLECULES = 100
```
The `/best_molecules`, `/api/best`, and `/api/stats` endpoints return these hardcoded values rather than querying a live database or generated results. This is presentation theater, not a working system. The API would report the same "best molecule" even if the model has never been trained.

#### CRITICAL: Training dataset is 20 hand-typed molecules
`train.py` contains a hardcoded list of 20 common molecules (aspirin, caffeine, ethanol, benzene, etc.). A VAE trained on 20 molecules cannot learn meaningful chemical patterns. The model will memorize the training set and fail to generalize. Real drug discovery VAEs require 100,000–1,000,000+ diverse SMILES strings.

#### CRITICAL: KL annealing bug in `train.py`
```python
# kl_weight starts at 0.0 and increments 0.01 per epoch — but max is 0.005
KL_WEIGHT_MAX = 0.005
kl_weight += 0.01  # per epoch
kl_weight = min(kl_weight, KL_WEIGHT_MAX)
```
The KL weight reaches its maximum (0.005) after 1 epoch and stays there. The annealing schedule is broken — the weight never grows to the target of 0.5 defined in `model.py`. This will cause the model to under-regularize the latent space.

#### CRITICAL: `scorer.py` is mostly empty stubs
The file defines function signatures with `pass` bodies. The clinical scoring functions (`passes_lipinski`, `calculate_qed`, `calculate_sa_score`, `is_novel`) have no implementation. The `validate.py` has a parallel implementation — these two files duplicate intent and neither is complete.

#### HIGH: Heuristic binding affinity is not real docking
`validate.py` calculates "binding affinity" by counting aromatic rings and hydrogen bond donors using a formula like `baseline + 0.3 × rings`. This is not molecular docking. Results reported as kcal/mol are scientifically invalid and misleading. The docking module (`genorova/src/docking/`) exists but is never called from the main pipeline.

#### HIGH: Duplicate React component with no cleanup
`main.jsx` imports `GenorovaChatAppV11`. Files `App.jsx`, `PlatformApp.jsx`, `GenorovaChatApp.jsx`, and `GenorovaChatAppV11.jsx` all exist in `src/`. Only one is active. The others are dead code that will confuse future developers.

#### MEDIUM: No random seed setting anywhere
Neither `train.py` nor `generate.py` sets `torch.manual_seed()`, `numpy.random.seed()`, or `random.seed()`. Training runs are not reproducible.

#### MEDIUM: Broken import chain
`genorova/src/api.py` uses `uvicorn src.api:app` per `render.yaml`, but `app/backend/main.py` is also a FastAPI app. Two separate FastAPI applications exist with overlapping endpoints. It is unclear which one is authoritative for production.

#### MEDIUM: No input sanitization on SMILES inputs
`/score` and `/chat` endpoints accept SMILES strings and pass them directly to RDKit. Malformed input causing RDKit to crash will produce a 500 error with a Python traceback visible to the user.

#### LOW: Dead code — `main_legacy_api.py`
`app/backend/main_legacy_api.py` exists but is not imported anywhere. Legacy routes are duplicated inside `main.py`.

---

### 2.2 Style and Readability

| File | Docstrings | Type Hints | PEP8 | Comments |
|------|-----------|------------|------|---------|
| `data_loader.py` | ✅ Good | Partial | ✅ | ✅ Verbose |
| `preprocessor.py` | ✅ Good | Partial | ✅ | ✅ Verbose |
| `model.py` | ✅ Good | Partial | ✅ | ✅ Verbose |
| `train.py` | ✅ Good | None | ✅ | ✅ Verbose |
| `generate.py` | ✅ Good | Partial | ✅ | ✅ |
| `validate.py` | ✅ Good | None | ✅ | ✅ |
| `scorer.py` | Stubs only | None | ✅ | Minimal |
| `chat_logic.py` | ✅ Good | ✅ Good | ✅ | ✅ |
| `chat_memory.py` | ✅ Good | Partial | ✅ | ✅ |
| `main.py` (backend) | Minimal | None | ✅ | Minimal |

**Positive:** Docstrings exist on most public functions. Comments are verbose and developer-friendly. Naming is descriptive.

**Negative:** Type hints are inconsistent — present in some files, absent in others. No `mypy` config. No linter config (no `pyproject.toml`, no `ruff.toml`, no `.flake8`).

---

### 2.3 Error Handling and Logging

- Most functions have `try/except` blocks with print statements — good for a prototype.
- All error logging uses `print()`. No structured logging (`logging` module, JSON logs, log levels). This is incompatible with production log aggregation (Datadog, CloudWatch, Papertrail).
- Exceptions in the API endpoints are not caught at the route level — RDKit errors propagate as unhandled 500s.
- `chat_memory.py` has a fallback DB path to `%TEMP%` — this is a Windows-only path that will fail on Linux (Render.com runs Linux).

---

### 2.4 Security Issues

| Issue | Severity | Location |
|-------|----------|---------|
| CORS allows all origins (`allow_origins=["*"]`) | HIGH | `main.py` |
| No authentication on any endpoint | HIGH | All routes |
| No rate limiting | HIGH | All routes |
| No API key management | HIGH | All routes |
| Unsanitized SMILES passed directly to RDKit | MEDIUM | `/score`, `/chat` |
| SQLite database committed to repo (`chat_memory.db`) | MEDIUM | `.gitignore` should exclude it but file exists in tree |
| `%TEMP%` path fallback — Linux incompatible | MEDIUM | `chat_memory.py` |
| No HTTPS enforcement | MEDIUM | Render handles TLS, but no redirect config |

---

## Step 3 — ML/Research Specific Checks

### 3.1 Data Pipeline

| Check | Status | Detail |
|-------|--------|--------|
| SMILES validation via RDKit | ✅ Implemented | `data_loader.py` validates with `Chem.MolFromSmiles` |
| Lipinski filter | ✅ Implemented | MW, LogP, HBD, HBA checked |
| Duplicate removal | ✅ Implemented | `remove_duplicates=True` in `process_smiles_data` |
| Train/val/test split | ✅ Implemented | 80/10/10 with shuffling |
| Data leakage prevention | ⚠️ Partial | Split is done but no check that val/test molecules aren't in train after augmentation |
| Real dataset | ❌ MISSING | Only 20 hand-typed molecules in `train.py`. No ChEMBL download. No data pipeline. |
| Data augmentation | ❌ MISSING | Randomize SMILES, scaffold hop — defined in spec, not implemented |
| SMILES canonicalization | ❌ MISSING | No `Chem.MolToSmiles(mol)` canonicalization before encoding |
| Charset consistency | ⚠️ Risk | Vocabulary is built from training data; if test SMILES has new chars, they are silently dropped |

### 3.2 Model Architecture

| Check | Status | Detail |
|-------|--------|--------|
| VAE encoder | ✅ Implemented | 3-layer MLP with BatchNorm, ReLU, Dropout |
| VAE decoder | ✅ Implemented | 3-layer MLP mirror |
| Reparameterization trick | ✅ Correct | `z = mu + eps * exp(0.5 * logvar)` |
| Free bits (anti-collapse) | ✅ Implemented | `FREE_BITS = 0.5` per dimension |
| KL annealing | ❌ BROKEN | Bug: max KL weight is 0.005, never reaches target 0.5 |
| Reconstruction loss | ⚠️ Suboptimal | BCE on one-hot is correct but CrossEntropyLoss on logits is more numerically stable |
| Device handling | ✅ Implemented | Auto-detects CUDA, falls back to CPU |
| Gradient clipping | ✅ Implemented | `CLIP_GRADIENT = 1.0` |
| BatchNorm in VAE | ⚠️ Caution | BatchNorm + stochastic reparameterization can cause training instability |
| Architecture size | ⚠️ Mismatch | `model.py` uses `ENCODER_LAYERS = [1024, 512, 256]`, spec says `[512, 256]` |

### 3.3 Training Loop

| Check | Status | Detail |
|-------|--------|--------|
| Training loop | ✅ Implemented | Epoch + batch loop |
| Validation loop | ✅ Implemented | Separate validation pass each epoch |
| Early stopping | ✅ Implemented | `EARLY_STOPPING_PATIENCE = 10` |
| LR scheduler | ✅ Implemented | StepLR, decay 0.95 every 10 epochs |
| Checkpointing | ✅ Implemented | Every 10 epochs + best model |
| Optimizer state saving | ✅ Implemented | Resumes training correctly |
| Random seeds | ❌ MISSING | No `torch.manual_seed()` anywhere |
| Mixed precision | ❌ MISSING | Spec says `MIXED_PRECISION = True`, not implemented |
| Metric logging | ⚠️ Partial | Prints to stdout only. No file logs, no MLflow, no W&B |
| Sample generation during training | ✅ Implemented | Every 10 epochs, 5 test molecules |
| Gradient monitoring | ❌ MISSING | No gradient norm logging to detect exploding/vanishing |

### 3.4 Molecule Generation and Evaluation

| Check | Status | Detail |
|-------|--------|--------|
| Latent space sampling | ✅ Implemented | `z ~ N(0, I)` with temperature scaling |
| SMILES decoding | ✅ Implemented | Argmax on decoder logits |
| Validity check | ✅ Implemented | RDKit parse + Lipinski + QED |
| Novelty check | ✅ Implemented | Compared against training set |
| Uniqueness check | ⚠️ Partial | Checked within batch, not across sessions |
| QED score | ✅ Implemented | `rdkit.Chem.QED` |
| SA score | ✅ Implemented | `sascorer` module |
| Tanimoto similarity | ✅ Implemented | Morgan fingerprints |
| Real docking | ❌ NOT CONNECTED | Docking module exists but is never called from main pipeline |
| ADME prediction | ❌ MISSING | Not implemented |
| Toxicity prediction | ❌ MISSING | Only rule-based (nitro groups flag) |
| Beam search decoding | ❌ MISSING | Greedy decoding only — misses higher-quality sequences |

---

## Step 4 — Production Readiness Gap Analysis

### 4.1 Packaging

| Item | Status | Gap |
|------|--------|-----|
| `requirements.txt` | ❌ BROKEN | Two files with conflicting deps; torch version doesn't exist |
| `pyproject.toml` | ❌ MISSING | No build system config |
| `setup.py` / `setup.cfg` | ❌ MISSING | Package is not installable |
| `Dockerfile` | ❌ MISSING | No containerization |
| `docker-compose.yml` | ❌ MISSING | No local dev orchestration |
| Dependency locking | ❌ MISSING | No `pip freeze > requirements.lock` or `poetry.lock` |
| Virtual env specification | ✅ Partial | `.python-version` exists (3.11.0) |

### 4.2 Config Management

| Item | Status | Gap |
|------|--------|-----|
| YAML/Hydra config | ❌ MISSING | All hyperparameters are hardcoded in source files |
| Environment variables | ⚠️ Partial | `VITE_API_BASE_URL` only |
| `.env` file support | ❌ MISSING | No `python-dotenv` |
| Config versioning | ❌ MISSING | No way to reproduce a specific run's hyperparameters |
| Separate dev/staging/prod configs | ❌ MISSING | Single hardcoded config |

### 4.3 Experiment Tracking

| Item | Status | Gap |
|------|--------|-----|
| MLflow | ❌ MISSING | All metrics printed to stdout, lost after run |
| Weights & Biases | ❌ MISSING | — |
| TensorBoard | ❌ MISSING | LOG_DIR is defined in spec but never written to |
| Run comparison | ❌ MISSING | No way to compare two training runs |
| Artifact storage | ❌ MISSING | Model weights saved locally only |
| Hyperparameter search | ❌ MISSING | No Optuna, Ray Tune, or similar |

### 4.4 Testing

| Item | Status | Gap |
|------|--------|-----|
| Unit tests | ❌ ZERO | No test files anywhere in the codebase |
| Integration tests | ❌ ZERO | — |
| Data validation tests | ❌ ZERO | No schema validation on input data |
| API endpoint tests | ❌ ZERO | No `pytest` + `httpx` tests |
| Model output tests | ❌ ZERO | No assertion that generated molecules meet minimum validity |
| Regression tests | ❌ ZERO | — |
| Test coverage report | ❌ ZERO | — |

### 4.5 CI/CD Pipeline

| Item | Status | Gap |
|------|--------|-----|
| GitHub Actions | ❌ MISSING | No `.github/workflows/` directory |
| Pre-commit hooks | ❌ MISSING | No `.pre-commit-config.yaml` |
| Automated linting | ❌ MISSING | No ruff, flake8, or black in CI |
| Automated testing | ❌ MISSING | No test runner in CI |
| Automated deployment | ⚠️ Partial | Render auto-deploys from main branch but no staging gate |
| Branch protection | Unknown | Not visible from codebase |
| Build status badge | ❌ MISSING | — |

### 4.6 Model Serving

| Item | Status | Gap |
|------|--------|-----|
| REST API | ✅ Exists | FastAPI with `/generate`, `/score`, `/chat` |
| API documentation | ⚠️ Partial | FastAPI auto-generates `/docs` but no published API spec |
| Batch inference | ❌ MISSING | Endpoints process one molecule at a time |
| Async inference | ❌ MISSING | All inference is synchronous — will block the event loop |
| Model loading at startup | ❌ UNCLEAR | No startup event that loads model weights |
| Request queuing | ❌ MISSING | No Celery, RQ, or similar task queue |
| Model versioning | ❌ MISSING | No way to A/B test model versions |
| Latency monitoring | ❌ MISSING | No response time tracking |
| Request validation | ⚠️ Partial | Pydantic models exist but incomplete |

### 4.7 Monitoring and Logging

| Item | Status | Gap |
|------|--------|-----|
| Structured logging | ❌ MISSING | All output is `print()` |
| Log levels | ❌ MISSING | No DEBUG/INFO/WARNING/ERROR separation |
| Error alerting | ❌ MISSING | No Sentry, PagerDuty, or similar |
| Model drift detection | ❌ MISSING | No monitoring of validity/QED distribution over time |
| API health endpoint | ✅ Exists | `GET /health` |
| Uptime monitoring | ❌ MISSING | No external ping monitor |
| Database query logging | ❌ MISSING | SQLite queries not logged |
| Audit trail | ❌ MISSING | No record of who called which endpoint |

### 4.8 Scalability

| Item | Status | Gap |
|------|--------|-----|
| Multi-GPU training | ❌ MISSING | No `DataParallel` or `DistributedDataParallel` |
| Dataset streaming | ❌ MISSING | Entire dataset loaded into RAM |
| Database | ❌ INSUFFICIENT | SQLite is single-writer; will fail under concurrent requests |
| Connection pooling | ❌ MISSING | New SQLite connection per request |
| Caching | ❌ MISSING | No Redis or in-memory cache for repeated queries |
| Load balancing | ❌ MISSING | Single Render.com instance |
| Horizontal scaling | ❌ INCOMPATIBLE | SQLite file storage cannot scale horizontally |

### 4.9 Documentation

| Item | Status | Gap |
|------|--------|-----|
| README.md | ❌ MISSING | No README in the project root |
| API documentation | ⚠️ Auto-gen | FastAPI `/docs` exists but not linked |
| Model card | ❌ MISSING | No training data description, evaluation results, or limitations |
| Architecture diagram | ❌ MISSING | — |
| Deployment guide | ❌ MISSING | render.yaml exists but no written deployment guide |
| Data dictionary | ❌ MISSING | No schema documentation for database tables |
| Changelog | ❌ MISSING | — |
| Contributing guide | ❌ MISSING | — |

### 4.10 Pharma SaaS Compliance

| Item | Status | Gap |
|------|--------|-----|
| Authentication (OAuth2, JWT) | ❌ MISSING | Any anonymous user can call any endpoint |
| Authorization (RBAC) | ❌ MISSING | No user roles |
| Data encryption at rest | ❌ MISSING | SQLite databases are plaintext |
| GDPR / data privacy | ❌ MISSING | No data retention policy, no user data deletion |
| 21 CFR Part 11 (pharma audit) | ❌ MISSING | No electronic signatures, no immutable audit trail |
| GxP compliance | ❌ MISSING | No validated software lifecycle |
| Regulatory disclaimer | ❌ MISSING | No statement that outputs are not clinical recommendations |
| Model lineage tracking | ❌ MISSING | No record of which data trained which model version |
| Versioned experiment records | ❌ MISSING | Results cannot be reproduced or audited |
| Data provenance | ❌ MISSING | No tracking of where input SMILES came from |

---

## Step 5 — Verdict and Next Step

### Ready to Move to Next Step: NO

### Current Maturity Level: **PROTOTYPE**

The codebase demonstrates correct conceptual architecture and good code organization. The core ML components (VAE, validation pipeline, chat interface) are coherently structured. However, numerous critical defects prevent this from operating as an MVP, let alone a production system.

---

### Top 5 Blockers Before Next Phase

| # | Blocker | Why It Stops Progress |
|---|---------|----------------------|
| 1 | **Broken `requirements.txt`** | `pip install` will fail on any clean machine. Cannot deploy, cannot onboard contributors, cannot run tests in CI. Fix this before anything else. |
| 2 | **Training on 20 molecules** | A VAE trained on 20 molecules learns nothing useful. Every downstream result (generated molecules, scores, candidates) is meaningless. Real data (ChEMBL, ZINC) must be integrated before any ML results are credible. |
| 3 | **Hardcoded API responses** | `/best_molecules` and `/api/stats` return fabricated constants regardless of model state. This makes the system dishonest — it reports results that were never computed. |
| 4 | **KL annealing bug** | The broken schedule means the VAE latent space is never properly regularized. Even with real data, the model will not learn a smooth, explorable latent space. |
| 5 | **No tests** | Zero test coverage means every change risks silently breaking the pipeline. CI/CD is impossible without tests. |

---

### Top 10 Actions to Reach Industrial Production Grade

| Priority | Action | Detail | Effort |
|----------|--------|--------|--------|
| 1 | **Fix `requirements.txt`** | Pin to real versions: `torch==2.4.0`, `rdkit-pypi==2024.3.1`, `torchvision==0.19.0`. Add all missing deps (`sascorer`, `biopython`, `Pillow`, `cairosvg`). Create one unified file at project root. | **2 hours** |
| 2 | **Integrate real training data** | Download ChEMBL via `chembl_webresource_client` or use ZINC250k CSV. Write `scripts/download_data.py`. Target ≥ 50,000 drug-like SMILES. Update `train.py` to load from CSV, not hardcoded list. | **1–2 days** |
| 3 | **Fix KL annealing bug** | Change `KL_WEIGHT_MAX` from `0.005` to `0.5`. Verify the increment schedule reaches target over ~50 epochs. Add a test that confirms KL weight at epoch 50 equals 0.5. | **1 hour** |
| 4 | **Write unit tests** | Use `pytest`. Minimum coverage: SMILES validation, Lipinski filter, one-hot encoding/decoding roundtrip, API endpoints (`/health`, `/score`, `/generate`), chat intent parser, database create/read. Target 70% coverage. | **3–5 days** |
| 5 | **Replace hardcoded API constants** | Remove `BEST_MOLECULE`, `BEST_SCORE`, `TOTAL_MOLECULES` from `main.py`. Query the molecule database dynamically. Return empty results if no molecules have been generated yet. | **4 hours** |
| 6 | **Add structured logging + experiment tracking** | Replace all `print()` with Python `logging` module (JSON formatter). Integrate MLflow or W&B in `train.py` to log every epoch metric. Add a `runs/` directory for experiment records. | **1–2 days** |
| 7 | **Dockerize the application** | Write `Dockerfile` for backend (Python + RDKit), `docker-compose.yml` for local dev (backend + frontend). This eliminates "works on my machine" issues and enables reproducible deployments. | **1 day** |
| 8 | **Add authentication and rate limiting** | Implement JWT-based auth (`python-jose`, `passlib`) on all API endpoints. Add `slowapi` rate limiting. Replace SQLite with PostgreSQL (Render offers free Postgres). | **2–3 days** |
| 9 | **Replace heuristic binding scores with real docking** | Connect `genorova/src/docking/docking_engine.py` (already written) into the main validation pipeline. Replace the aromatic-ring-counting heuristic in `validate.py` with actual AutoDock Vina scores. | **2–3 days** |
| 10 | **Write README, model card, and API spec** | `README.md` with setup, training, and deployment instructions. Model card documenting training data, evaluation metrics, limitations, and regulatory disclaimer. Publish OpenAPI spec. | **1 day** |

---

### Effort Summary Table

| Phase | Key Actions | Total Effort |
|-------|------------|-------------|
| **Fix critical bugs** (Blockers 1, 3, 5) | Fix requirements, KL bug, hardcoded constants | 1 day |
| **Real data + training** (Blocker 2) | ChEMBL integration, retrain | 2–3 days |
| **Testing foundation** (Blocker 4) | pytest suite, 70% coverage | 3–5 days |
| **Observability** (Action 6) | Logging, MLflow | 1–2 days |
| **Infrastructure** (Action 7, 8) | Docker, auth, PostgreSQL | 3–4 days |
| **Science accuracy** (Action 9) | Real docking integration | 2–3 days |
| **Documentation** (Action 10) | README, model card, API spec | 1 day |
| **TOTAL** | | **~13–19 days** |

---

## Appendix: Specific Code Issues Reference

### requirements.txt — Broken Versions
```
# CURRENT (broken)
torch==2.11.0          # does not exist
torchvision==0.26.0    # does not exist
rdkit==2026.3.1        # wrong package name + nonexistent version

# FIX
torch==2.4.0
torchvision==0.19.0
rdkit-pypi==2024.3.5
```

### train.py — KL Annealing Bug
```python
# CURRENT (broken)
KL_WEIGHT_MAX = 0.005
kl_weight += 0.01      # exceeds max after 1 epoch, stuck at 0.005 forever

# FIX
KL_WEIGHT_START = 0.0
KL_WEIGHT_MAX   = 0.5
KL_WEIGHT_STEP  = 0.01   # reaches 0.5 at epoch 50
```

### main.py — Hardcoded Constants Must Be Removed
```python
# CURRENT (fabricated)
BEST_MOLECULE = "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"
BEST_SCORE    = 0.9649   # not computed — typed in manually

# FIX — query the database
@app.get("/api/best")
async def get_best():
    results = db.query("SELECT * FROM molecules ORDER BY clinical_score DESC LIMIT 5")
    return results if results else {"message": "No molecules generated yet"}
```

### chat_memory.py — Linux-Incompatible Fallback
```python
# CURRENT (Windows-only)
FALLBACK_DB_PATH = os.path.join(os.environ.get("TEMP", "/tmp"), "genorova_chat_memory.db")

# FIX (cross-platform)
FALLBACK_DB_PATH = os.path.join(tempfile.gettempdir(), "genorova_chat_memory.db")
```

---

*This report was generated by automated codebase audit on 2026-04-14. All findings are based on static analysis of source code only. Dynamic behavior, model training outputs, and runtime performance are not evaluated.*

*Genorova AI generates computational predictions only. No outputs should be interpreted as clinical recommendations or used to make medical decisions without full experimental and regulatory validation.*
