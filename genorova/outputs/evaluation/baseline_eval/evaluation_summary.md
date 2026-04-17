# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `..\outputs\models\diabetes\genorova_diabetes_finetune_best.pt`
- Vocabulary: `..\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `random`
- Temperature: `0.3`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- Requested samples: `500`
- Reference source for novelty: `dataset:moses`
- Checkpoint stage: `finetune`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 4 / 500 |
| Validity | 0.8% |
| Unique valid molecules | 4 / 4 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 4 / 4 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 4 / 4 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.7879 |
| Best clinical score (unique valid) | 0.832 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 4 |
| Filtered computational candidates | 2 |
| Filter pass rate | 50.0% |
| Rejection reasons | `{'qed_below_threshold': 2}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CC(C)NCC(CCC1CC=CC=CC1)C(N)=O | 0.832 | 0.7287 | 3.4896 | 250.39 | 2.389 | True | passed_all_filters |
| C#CC1(CC2CCC2O)CC2=C1C1C(=O)C1CC(C)CC2 | 0.785 | 0.6247 | 5.153 | 284.4 | 3.102 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CC(C)NCC(CCC1CC=CC=CC1)C(N)=O | 0.832 | Strong candidate | 0.7287 | 3.4896 | 250.39 | 2.389 |
| CC1=C(CCCOC(C)O)C1C | 0.8069 | Strong candidate | 0.3887 | 3.7273 | 170.25 | 2.088 |
| C#CC1(CC2CCC2O)CC2=C1C1C(=O)C1CC(C)CC2 | 0.785 | Strong candidate | 0.6247 | 5.153 | 284.4 | 3.102 |
| CCCCCC1CC(=O)CC(CCCC)C1C1CO1 | 0.7275 | Strong candidate | 0.4821 | 3.833 | 266.42 | 4.367 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 305, 'ring_closure_mismatch': 84, 'unbalanced_parentheses': 52, 'long_repetitive_fragment': 32, 'unbalanced_brackets': 23}`
- Invalid reason percentages: `{'rdkit_parse_failure': 61.49, 'ring_closure_mismatch': 16.94, 'unbalanced_parentheses': 10.48, 'long_repetitive_fragment': 6.45, 'unbalanced_brackets': 4.64}`
- Avg invalid length: `94.7762`
- Common invalid endings: `{'2)O1': 7, 'O)C1': 6, 'N1C2': 4, '2HO1': 3, 'CCC1': 3, 'OO)C': 3, 'CC=O': 3, 'C)C1': 3, 'CO)C': 3, 'C1=O': 2}`
- Top decoded tokens: `{'C': 16523, 'c': 4143, 'O': 3958, '(': 3433, ')': 3366, '1': 3183, 'H': 2047, '[': 1824, ']': 1791, '2': 1365}`
