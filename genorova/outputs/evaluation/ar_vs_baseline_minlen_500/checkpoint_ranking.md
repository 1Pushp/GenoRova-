# Checkpoint Ranking

- Strategy: `guided`
- Temperature: `0.25`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- AR minimum generation length: `20`
- Samples per checkpoint: `500`
- Reference source: `genorova\data\raw\diabetes_molecules.csv`
- Candidate filters: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Best Current Checkpoint

`smilesvae_ar_best.pt` ranked first because it led on validity (74.2%), then unique valid molecule count (367), with average score `0.8456`.

## Best For Validity

`smilesvae_ar_best.pt` had the strongest validity result at `74.2%` (371 valid / 500 requested).

## Best For Score Quality

`smilesvae_ar_best.pt` had the strongest score profile with average score `0.8456` and best score `0.9591`.

## Pretrain vs Fine-tune

_Stage comparison unavailable._

## Ranking Table

| rank | checkpoint_name | validity_pct | filtered_candidate_count | unique_valid_count | mean_valid_length | mean_valid_molecular_weight | mean_valid_qed | novelty_pct_of_unique_valid | average_clinical_score | best_clinical_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | smilesvae_ar_best.pt | 74.2 | 349 | 367 | 36.5849 | 305.6385 | 0.8016 | 100.0 | 0.8456 | 0.9591 |
| 2 | genorova_diabetes_finetune_best.pt | 10.0 | 43 | 50 | 27.8 | 248.6668 | 0.7077 | 74.0 | 0.8366 | 0.9191 |
