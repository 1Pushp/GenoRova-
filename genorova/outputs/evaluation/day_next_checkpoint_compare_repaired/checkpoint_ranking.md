# Checkpoint Ranking

- Strategy: `guided`
- Temperature: `0.3`
- Samples per checkpoint: `300`
- Reference source: `genorova\data\raw\diabetes_molecules.csv`
- Candidate filters: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Best Current Checkpoint

`genorova_diabetes_finetune_best.pt` ranked first because it led on validity (6.0%), then unique valid molecule count (18), with average score `0.8462`.

## Best For Validity

`genorova_diabetes_finetune_best.pt` had the strongest validity result at `6.0%` (18 valid / 300 requested).

## Best For Score Quality

`genorova_diabetes_pretrain_best.pt` had the strongest score profile with average score `0.8471` and best score `0.9183`.

## Pretrain vs Fine-tune

Fine-tuning is currently stronger under this controlled setting because the highest-ranked checkpoint is `genorova_diabetes_finetune_best.pt`. Best pretrain validity: `1.33%`; best fine-tune validity: `6.0%`.

## Ranking Table

| rank | checkpoint_name | validity_pct | filtered_candidate_count | unique_valid_count | novelty_pct_of_unique_valid | average_clinical_score | best_clinical_score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | genorova_diabetes_finetune_best.pt | 6.0 | 15 | 18 | 72.22 | 0.8462 | 0.9299 |
| 2 | genorova_diabetes_finetune_final.pt | 6.0 | 15 | 18 | 72.22 | 0.8462 | 0.9299 |
| 3 | genorova_diabetes_pretrain_best.pt | 1.33 | 4 | 4 | 100.0 | 0.8471 | 0.9183 |
| 4 | genorova_diabetes_pretrain_final.pt | 1.33 | 4 | 4 | 100.0 | 0.8471 | 0.9183 |
