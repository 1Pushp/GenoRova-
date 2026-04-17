# Checkpoint Ranking

- Strategy: `guided`
- Temperature: `0.3`
- Samples per checkpoint: `25`
- Reference source: `moses`

## Best Current Checkpoint

`genorova_diabetes_pretrain_best.pt` ranked first because it led on validity (0.0%), then unique valid molecule count (0), with average score `None`.

## Ranking Table

| rank | checkpoint_name | validity_pct | unique_valid_count | novelty_pct_of_unique_valid | average_clinical_score | best_clinical_score |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | genorova_diabetes_pretrain_best.pt | 0.0 | 0 | 0.0 |  |  |
| 2 | genorova_diabetes_pretrain_final.pt | 0.0 | 0 | 0.0 |  |  |
| 3 | genorova_diabetes_finetune_best.pt | 0.0 | 0 | 0.0 |  |  |
| 4 | genorova_diabetes_finetune_final.pt | 0.0 | 0 | 0.0 |  |  |
