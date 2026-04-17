# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_finetune_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `300`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `finetune`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 18 / 300 |
| Validity | 6.0% |
| Unique valid molecules | 18 / 18 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 13 / 18 |
| Novelty among valid | 72.22% |
| Novel unique molecules | 13 / 18 |
| Novelty among unique valid | 72.22% |
| Average clinical score (unique valid) | 0.8462 |
| Best clinical score (unique valid) | 0.9299 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 18 |
| Filtered computational candidates | 15 |
| Filter pass rate | 83.33% |
| Rejection reasons | `{'qed_below_threshold': 2, 'mw_out_of_range': 1}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CCC(C)C(N)C(=O)N1CCCC1C#N | 0.9299 | 0.7495 | 3.3801 | 209.29 | 0.874 | True | passed_all_filters |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |
| NCCC(N)C(=O)N1CCCCC1 | 0.8785 | 0.6324 | 2.5359 | 185.27 | -0.325 | True | passed_all_filters |
| CC(=O)NC(=O)NCCc1ccccc1 | 0.8763 | 0.7769 | 1.6266 | 206.25 | 1.075 | True | passed_all_filters |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1C | 0.8643 | 0.9413 | 1.6185 | 291.37 | 3.113 | True | passed_all_filters |
| CNC(=O)Cc1cccc2cnccc12 | 0.8643 | 0.7983 | 1.9453 | 200.24 | 1.523 | True | passed_all_filters |
| N#Cc1c(NC(=O)c2ccccc2)sc2c1CCCC2 | 0.8601 | 0.9116 | 1.9496 | 282.37 | 3.751 | True | passed_all_filters |
| CC(Cc1ccccc1)C(=O)N1CCCC1 | 0.8591 | 0.7614 | 2.1071 | 217.31 | 2.488 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCCCC1 | 0.8567 | 0.7442 | 2.6619 | 198.31 | 1.372 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CCC(C)C(N)C(=O)N1CCCC1C#N | 0.9299 | Strong candidate | 0.7495 | 3.3801 | 209.29 | 0.874 |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | Strong candidate | 0.7609 | 4.8104 | 272.37 | 1.521 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |
| NCCC(N)C(=O)N1CCCCC1 | 0.8785 | Strong candidate | 0.6324 | 2.5359 | 185.27 | -0.325 |
| CC(=O)NC(=O)NCCc1ccccc1 | 0.8763 | Strong candidate | 0.7769 | 1.6266 | 206.25 | 1.075 |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1C | 0.8643 | Strong candidate | 0.9413 | 1.6185 | 291.37 | 3.113 |
| CNC(=O)Cc1cccc2cnccc12 | 0.8643 | Strong candidate | 0.7983 | 1.9453 | 200.24 | 1.523 |
| N#Cc1c(NC(=O)c2ccccc2)sc2c1CCCC2 | 0.8601 | Strong candidate | 0.9116 | 1.9496 | 282.37 | 3.751 |
| CC(Cc1ccccc1)C(=O)N1CCCC1 | 0.8591 | Strong candidate | 0.7614 | 2.1071 | 217.31 | 2.488 |
| CCC(C)C(N)C(=O)N1CCCCC1 | 0.8567 | Strong candidate | 0.7442 | 2.6619 | 198.31 | 1.372 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 198, 'ring_closure_mismatch': 47, 'unbalanced_brackets': 23, 'rdkit_parse_failure': 9, 'long_repetitive_fragment': 5}`
- Top decoded tokens: `{'c': 2901, 'C': 2509, ')': 1244, '(': 1209, '1': 768, 'O': 712, '=': 455, 'N': 425, '2': 417, '<unk>': 400}`
