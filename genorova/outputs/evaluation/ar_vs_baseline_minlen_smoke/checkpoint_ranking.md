# Checkpoint Ranking

- Strategy: `guided`
- Temperature: `0.25`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- AR minimum generation length: `20`
- Samples per checkpoint: `200`
- Reference source: `genorova\data\raw\diabetes_molecules.csv`
- Candidate filters: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Best Current Checkpoint

`smilesvae_ar_best.pt` ranked first because it led on validity (72.0%), then unique valid molecule count (143), with average score `0.8437`.

## Best For Validity

`smilesvae_ar_best.pt` had the strongest validity result at `72.0%` (144 valid / 200 requested).

## Best For Score Quality

`smilesvae_ar_best.pt` had the strongest score profile with average score `0.8437` and best score `0.9568`.

## Pretrain vs Fine-tune

_Stage comparison unavailable._

## Ranking Table

| rank | checkpoint_name | validity_pct | filtered_candidate_count | unique_valid_count | mean_valid_length | mean_valid_molecular_weight | mean_valid_qed | novelty_pct_of_unique_valid | average_clinical_score | best_clinical_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | smilesvae_ar_best.pt | 72.0 | 135 | 143 | 36.4306 | 304.2104 | 0.7998 | 100.0 | 0.8437 | 0.9568 |
| 2 | genorova_diabetes_finetune_best.pt | 12.0 | 20 | 24 | 27.6667 | 249.5992 | 0.7087 | 79.17 | 0.8342 | 0.9191 |
