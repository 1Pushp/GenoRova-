# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `50`
- Reference source for novelty: `dataset:moses`
- Checkpoint stage: `None`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 0 / 50 |
| Validity | 0.0% |
| Unique valid molecules | 0 / 0 |
| Uniqueness among valid | 0.0% |
| Novel valid molecules | 0 / 0 |
| Novelty among valid | 0.0% |
| Novel unique molecules | 0 / 0 |
| Novelty among unique valid | 0.0% |
| Average clinical score (unique valid) | N/A |
| Best clinical score (unique valid) | N/A |

## Top Candidates

_No candidates available._

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 35, 'ring_closure_mismatch': 9, 'long_repetitive_fragment': 6}`
- Top decoded tokens: `{'c': 885, 'C': 329, ')': 142, '(': 117, '1': 86, 'O': 55, '2': 43, '=': 36, 'N': 22, 'n': 8}`
