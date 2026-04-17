# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `..\outputs\models\ar\smilesvae_ar_best.pt`
- Vocabulary: `..\outputs\vocab_ar.json`
- Strategy: `random`
- Temperature: `0.3`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- Requested samples: `500`
- Reference source for novelty: `dataset:moses`
- Checkpoint stage: `None`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 40 / 500 |
| Validity | 8.0% |
| Unique valid molecules | 32 / 40 |
| Uniqueness among valid | 80.0% |
| Novel valid molecules | 40 / 40 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 32 / 32 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.6725 |
| Best clinical score (unique valid) | 0.8528 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 32 |
| Filtered computational candidates | 1 |
| Filter pass rate | 3.12% |
| Rejection reasons | `{'mw_out_of_range': 31, 'qed_below_threshold': 31, 'logp_out_of_range': 3, 'sa_above_threshold': 3}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CCc1ccsc1C(=O)NC | 0.8528 | 0.7166 | 2.2238 | 169.25 | 1.67 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CCc1ccsc1C(=O)NC | 0.8528 | Strong candidate | 0.7166 | 2.2238 | 169.25 | 1.67 |
| CCOC=O | 0.7086 | Strong candidate | 0.4366 | 3.0432 | 74.08 | 0.179 |
| C=CN | 0.7047 | Strong candidate | 0.4088 | 3.7858 | 43.07 | 0.089 |
| CNC1=CC1 | 0.6961 | Strong candidate | 0.4723 | 3.6643 | 69.11 | 0.493 |
| CCOC | 0.6904 | Strong candidate | 0.4315 | 1.9457 | 60.1 | 0.653 |
| Br | 0.686 | Strong candidate | 0.3997 | 6.964 | 80.91 | 0.578 |
| CN1CCC1 | 0.6856 | Strong candidate | 0.3973 | 1.4454 | 71.12 | 0.322 |
| COC | 0.6832 | Strong candidate | 0.38 | 1.9569 | 46.07 | 0.263 |
| CS | 0.6831 | Strong candidate | 0.3795 | 4.4454 | 48.11 | 0.546 |
| C=S | 0.6804 | Strong candidate | 0.3602 | 4.7277 | 46.09 | 0.616 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 290, 'unbalanced_parentheses': 127, 'too_short': 20, 'long_repetitive_fragment': 13, 'ring_closure_mismatch': 10}`
- Invalid reason percentages: `{'rdkit_parse_failure': 63.04, 'unbalanced_parentheses': 27.61, 'too_short': 4.35, 'long_repetitive_fragment': 2.83, 'ring_closure_mismatch': 2.17}`
- Avg invalid length: `34.5761`
- Common invalid endings: `{'(C)c': 5, 'C)C2': 4, '1c1c': 4, '=F': 4, '-F1)': 3, '-C#B': 3, 'C-#F': 3, '#F1)': 3, 'C2)1': 3, '-B#B': 3}`
- Top decoded tokens: `{'C': 2093, '#': 1723, '-': 1717, 'c': 1513, '(': 1502, '=': 1256, '1': 1209, ')': 1189, 'B': 1057, 'F': 822}`
