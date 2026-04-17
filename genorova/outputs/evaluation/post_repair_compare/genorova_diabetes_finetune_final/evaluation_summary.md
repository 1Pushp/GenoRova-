# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_finetune_final.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `100`
- Reference source for novelty: `dataset:moses`
- Checkpoint stage: `finetune`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 0 / 100 |
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
- Top invalid reasons: `{'unbalanced_parentheses': 69, 'ring_closure_mismatch': 19, 'unbalanced_brackets': 7, 'long_repetitive_fragment': 4, 'rdkit_parse_failure': 1}`
- Top decoded tokens: `{'c': 1066, 'C': 694, '(': 382, ')': 376, '1': 281, 'O': 219, '=': 170, 'N': 132, '2': 130, 'n': 51}`
