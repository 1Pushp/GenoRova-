# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\models\genorova_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocab.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `25`
- Reference source for novelty: `dataset:moses`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 0 / 25 |
| Validity | 0.0% |
| Unique valid molecules | 0 / 1 |
| Uniqueness among valid | 0.0% |
| Novel valid molecules | 0 / 1 |
| Novelty among valid | 0.0% |
| Novel unique molecules | 0 / 1 |
| Novelty among unique valid | 0.0% |
| Average clinical score (unique valid) | None |
| Best clinical score (unique valid) | None |

## Top Candidates

_No candidates available._

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.
