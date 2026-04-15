# Structural Decoding Improvement Summary

## Controlled Setup

- Checkpoint: `genorova_diabetes_finetune_best.pt`
- Strategy: `guided`
- Reference set: `genorova/data/raw/diabetes_molecules.csv`
- Samples per run: `1000`
- Seed: `42`
- Top-k: `5`
- Repetition penalty: `0.75`

## Before vs After

- Baseline decode (guard 0.0, temp 0.30) validity: `6.3%` with `41` filtered candidates.
- Improved decode (guard 1.0, temp 0.30) validity: `9.1%` with `68` filtered candidates.
- Absolute validity gain at the same temperature: `2.8 percentage points`.

## Best Ablation Run

- Best run: `guard10_temp025`
- Validity: `9.8%`
- Unique valid molecules: `86`
- Filtered computational candidates: `72`
- Average clinical score: `0.834`

## Main Invalidity Shift

- Baseline unbalanced parentheses: `69.26%` of invalid outputs.
- Improved unbalanced parentheses: `6.16%` of invalid outputs.
- Baseline ring mismatch: `17.29%` of invalid outputs.
- Improved ring mismatch: `11.88%` of invalid outputs.

These remain computationally generated molecules for research support only, not experimentally validated candidates.
