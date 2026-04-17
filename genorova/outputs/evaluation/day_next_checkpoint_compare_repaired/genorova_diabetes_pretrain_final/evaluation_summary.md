# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_pretrain_final.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `300`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `pretrain`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 4 / 300 |
| Validity | 1.33% |
| Unique valid molecules | 4 / 4 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 4 / 4 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 4 / 4 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.8471 |
| Best clinical score (unique valid) | 0.9183 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 4 |
| Filtered computational candidates | 4 |
| Filter pass rate | 100.0% |
| Rejection reasons | `{}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | 0.9346 | 1.4569 | 277.34 | 2.804 | True | passed_all_filters |
| CCOC(=O)Cc1ccc(NCc2ccc(F)cn2)cn1 | 0.8633 | 0.8269 | 2.2435 | 289.31 | 2.333 | True | passed_all_filters |
| CCCCc1cccc(NC(=O)c2ccccc2)c1C#N | 0.8375 | 0.8927 | 1.8737 | 278.36 | 4.153 | True | passed_all_filters |
| Cc1cc(N)ccc1CCCOCc1ccccn1 | 0.7693 | 0.6378 | 2.0877 | 256.35 | 3.122 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | Strong candidate | 0.9346 | 1.4569 | 277.34 | 2.804 |
| CCOC(=O)Cc1ccc(NCc2ccc(F)cn2)cn1 | 0.8633 | Strong candidate | 0.8269 | 2.2435 | 289.31 | 2.333 |
| CCCCc1cccc(NC(=O)c2ccccc2)c1C#N | 0.8375 | Strong candidate | 0.8927 | 1.8737 | 278.36 | 4.153 |
| Cc1cc(N)ccc1CCCOCc1ccccn1 | 0.7693 | Strong candidate | 0.6378 | 2.0877 | 256.35 | 3.122 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 214, 'ring_closure_mismatch': 54, 'long_repetitive_fragment': 16, 'unbalanced_brackets': 7, 'rdkit_parse_failure': 5}`
- Top decoded tokens: `{'c': 2842, 'C': 2320, ')': 1098, '(': 1073, '1': 827, 'O': 502, '2': 483, '=': 386, 'n': 355, 'N': 300}`
