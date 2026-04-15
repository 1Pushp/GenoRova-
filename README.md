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
python genorova/src/evaluate_generation.py --num-samples 100 --seed 42
```

### Run with an explicit checkpoint and vocabulary

```bash
python genorova/src/evaluate_generation.py \
  --checkpoint genorova/outputs/models/diabetes/genorova_diabetes_pretrain_best.pt \
  --vocab genorova/outputs/vocabulary_diabetes_pretrain.json \
  --num-samples 100 \
  --reference-dataset moses \
  --seed 42
```

### Compare multiple checkpoints

```bash
python genorova/src/evaluate_generation.py \
  --checkpoints \
    genorova/outputs/models/diabetes/genorova_diabetes_pretrain_best.pt \
    genorova/outputs/models/diabetes/genorova_diabetes_pretrain_final.pt \
    genorova/outputs/models/diabetes/genorova_diabetes_finetune_best.pt \
    genorova/outputs/models/diabetes/genorova_diabetes_finetune_final.pt \
  --num-samples 50 \
  --reference-dataset moses \
  --seed 42 \
  --output-dir genorova/outputs/evaluation/day5_checkpoint_compare
```

### Saved outputs

- `generated_molecules.csv`
- `evaluation_metrics.json`
- `evaluation_summary.md`
- `debug_decoding_samples.csv`
- `debug_summary.json`
- `checkpoint_comparison.csv`
- `checkpoint_metrics.json`
- `checkpoint_ranking.md`

## Current Model Status

Generation quality is still limited. The Day 5 checkpoint comparison found
essentially 0% RDKit-valid molecules across the evaluated checkpoints, so the
current product should be treated as a prototype research-support system rather
than a reliable de novo generator.

For honest demos, prefer these workflows:
- score a known SMILES string
- compare two known molecules
- explain molecule properties and risks
- review previously scored valid molecules or known references

When `/generate` cannot provide a trustworthy fresh result, the active API now
returns explicit fallback messaging and may show previously scored valid
molecules or known reference molecules instead of pretending generation
succeeded.
