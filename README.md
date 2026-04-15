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

## Generation Evaluation

Day 4 adds a generation-quality evaluator for trained VAE checkpoints. It
generates a batch of model candidates, measures validity/uniqueness/novelty,
runs the active Genorova scoring logic on valid molecules, and saves CSV/JSON/
Markdown artifacts under `genorova/outputs/evaluation/`.

### Run generation evaluation

```bash
python genorova/src/evaluate_generation.py --num-samples 100
```

### Run with an explicit checkpoint and vocabulary

```bash
python genorova/src/evaluate_generation.py \
  --checkpoint genorova/outputs/models/diabetes/genorova_diabetes_pretrain_best.pt \
  --vocab genorova/outputs/vocabulary_diabetes_pretrain.json \
  --num-samples 100 \
  --reference-dataset moses
```

### Saved outputs

- `generated_molecules.csv`
- `evaluation_metrics.json`
- `evaluation_summary.md`
