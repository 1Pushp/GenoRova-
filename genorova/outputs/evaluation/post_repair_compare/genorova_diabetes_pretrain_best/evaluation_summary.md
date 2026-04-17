# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_pretrain_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `100`
- Reference source for novelty: `dataset:moses`
- Checkpoint stage: `pretrain`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 1 / 100 |
| Validity | 1.0% |
| Unique valid molecules | 1 / 1 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 1 / 1 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 1 / 1 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.9311 |
| Best clinical score (unique valid) | 0.9311 |

## Top Candidates

| canonical_smiles | clinical_score | recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| COc1ncccc1CNS(=O)(=O)c1ccccc1 | 0.9311 | Strong candidate | 0.9011 | 1.841 | 278.33 | 1.569 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 64, 'ring_closure_mismatch': 27, 'long_repetitive_fragment': 7, 'rdkit_parse_failure': 1}`
- Top decoded tokens: `{'c': 1016, 'C': 700, '(': 355, ')': 339, '1': 308, 'O': 178, '2': 147, '=': 146, 'N': 119, 'n': 75}`
