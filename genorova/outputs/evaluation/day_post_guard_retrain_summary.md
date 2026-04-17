# Post-Guard Retrain Summary

## Training Run

- New label: `diabetes_guarded_retrain`
- Command path: `genorova/src/run_pipeline.py`
- Pretrain dataset: `moses`
- Pretrain sample cap: `5000`
- Pretrain epochs: `20`
- Fine-tune CSV: `genorova/data/raw/diabetes_molecules.csv`
- Fine-tune epochs: `10`
- Generation/scoring skipped during training so post-train evaluation could use the newer guarded evaluator

## Why This Retrain Used 5000 MOSES Molecules

This machine is CPU-only, so the retrain used a practical MOSES cap of `5000` to keep the run feasible while preserving the repaired schedule shape (`20` pretrain epochs + `10` fine-tune epochs).

## New Checkpoint Ranking

Evaluation settings:

- Strategy: `guided`
- Temperature: `0.25`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- Reference set: `genorova/data/raw/diabetes_molecules.csv`
- Samples per checkpoint: `1000`
- Seed: `42`

New checkpoint ranking result:

1. `genorova_diabetes_guarded_retrain_finetune_final.pt`
   - Validity: `9.0%`
   - Valid molecules: `90`
   - Unique valid molecules: `73`
   - Filtered computational candidates: `54`
   - Average clinical score: `0.8178`
2. `genorova_diabetes_guarded_retrain_finetune_best.pt`
   - Validity: `8.8%`
   - Valid molecules: `88`
   - Unique valid molecules: `79`
   - Filtered computational candidates: `59`
   - Average clinical score: `0.8331`
3. `genorova_diabetes_guarded_retrain_pretrain_best.pt`
   - Validity: `3.0%`
4. `genorova_diabetes_guarded_retrain_pretrain_final.pt`
   - Validity: `3.0%`

Fine-tuning still helps strongly versus pretraining alone.

## Old Best vs New Best

Direct comparison under the same guarded decode settings:

- Existing best checkpoint: `genorova_diabetes_finetune_best.pt`
  - Validity: `9.8%`
  - Valid molecules: `98`
  - Unique valid molecules: `86`
  - Filtered computational candidates: `72`
  - Average clinical score: `0.8340`
- Best fresh retrain checkpoint: `genorova_diabetes_guarded_retrain_finetune_final.pt`
  - Validity: `9.0%`
  - Valid molecules: `90`
  - Unique valid molecules: `73`
  - Filtered computational candidates: `54`
  - Average clinical score: `0.8178`

## Verdict

The fresh retrain did **not** materially outperform the current decode-improved winner.

- It beats the earlier pre-guard training regime in absolute validity terms.
- It does **not** beat the current best post-guard baseline.
- The best checkpoint to keep using right now remains:
  - `genorova/outputs/models/diabetes/genorova_diabetes_finetune_best.pt`
  - with `guided`, `temperature=0.25`, `top_k=5`, `repetition_penalty=0.75`, `structural_guard_strength=1.0`

## Main Interpretation

The guarded decode improvements are real and still important, but this fresh retrain did not unlock a second major jump in validity on top of them. That suggests the next bottleneck is less about missing guards and more about model quality / decoder expressiveness / training signal quality.

