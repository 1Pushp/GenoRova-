# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_finetune_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `20`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `finetune`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 1 / 20 |
| Validity | 5.0% |
| Unique valid molecules | 1 / 1 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 1 / 1 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 1 / 1 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.9191 |
| Best clinical score (unique valid) | 0.9191 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 1 |
| Filtered computational candidates | 1 |
| Filter pass rate | 100.0% |
| Rejection reasons | `{}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COC1C=C2C=CC(C)=CC2CNCC(=O)NC1CO | 0.9191 | 0.6719 | 5.0211 | 278.35 | 0.14 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| COC1C=C2C=CC(C)=CC2CNCC(=O)NC1CO | 0.9191 | Strong candidate | 0.6719 | 5.0211 | 278.35 | 0.14 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 11, 'unbalanced_brackets': 4, 'ring_closure_mismatch': 2, 'rdkit_parse_failure': 1, 'long_repetitive_fragment': 1}`
- Top decoded tokens: `{'c': 206, 'C': 194, ')': 91, '(': 88, 'O': 55, '1': 52, '[': 41, '2': 39, '=': 37, ']': 37}`
