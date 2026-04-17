# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_pretrain_best.pt`
- Vocabulary: `genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `5`
- Reference source for novelty: `dataset:moses`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 0 / 5 |
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
