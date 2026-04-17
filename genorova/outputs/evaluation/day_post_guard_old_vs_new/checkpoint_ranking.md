# Checkpoint Ranking

- Strategy: `guided`
- Temperature: `0.25`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- Samples per checkpoint: `1000`
- Reference source: `genorova\data\raw\diabetes_molecules.csv`
- Candidate filters: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Best Current Checkpoint

`genorova_diabetes_finetune_best.pt` ranked first because it led on validity (9.8%), then unique valid molecule count (86), with average score `0.834`.

## Best For Validity

`genorova_diabetes_finetune_best.pt` had the strongest validity result at `9.8%` (98 valid / 1000 requested).

## Best For Score Quality

`genorova_diabetes_finetune_best.pt` had the strongest score profile with average score `0.834` and best score `0.9275`.

## Pretrain vs Fine-tune

_Stage comparison unavailable._

## Ranking Table

| rank | checkpoint_name | validity_pct | filtered_candidate_count | unique_valid_count | novelty_pct_of_unique_valid | average_clinical_score | best_clinical_score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | genorova_diabetes_finetune_best.pt | 9.8 | 72 | 86 | 81.4 | 0.834 | 0.9275 |
| 2 | genorova_diabetes_guarded_retrain_finetune_final.pt | 9.0 | 54 | 73 | 83.56 | 0.8178 | 0.9296 |
| 3 | genorova_diabetes_guarded_retrain_finetune_best.pt | 8.8 | 59 | 79 | 83.54 | 0.8331 | 0.9216 |
