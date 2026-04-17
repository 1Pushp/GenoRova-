# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `25`
- Reference source for novelty: `dataset:moses`
- Checkpoint stage: `None`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 1 / 25 |
| Validity | 4.0% |
| Unique valid molecules | 1 / 1 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 1 / 1 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 1 / 1 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.5059 |
| Best clinical score (unique valid) | 0.5059 |

## Top Candidates

| canonical_smiles | clinical_score | recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CCCCCCCCCCC(C)C1C=CC=CC=CC=CC=CC=CC=CC=CCC=C1 | 0.5059 | Borderline | 0.2387 | 4.499 | 430.72 | 10.179 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 18, 'ring_closure_mismatch': 4, 'unbalanced_brackets': 2}`
- Top decoded tokens: `{'c': 366, 'C': 202, ')': 69, '(': 49, '1': 42, 'O': 34, '=': 21, 'N': 17, '2': 16, 'n': 4}`
