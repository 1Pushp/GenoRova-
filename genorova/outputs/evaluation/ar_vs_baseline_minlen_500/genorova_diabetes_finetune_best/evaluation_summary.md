# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_finetune_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.25`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- AR minimum generation length: `None`
- Requested samples: `500`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `finetune`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 50 / 500 |
| Validity | 10.0% |
| Unique valid molecules | 50 / 50 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 37 / 50 |
| Novelty among valid | 74.0% |
| Novel unique molecules | 37 / 50 |
| Novelty among unique valid | 74.0% |
| Average clinical score (unique valid) | 0.8366 |
| Best clinical score (unique valid) | 0.9191 |
| Mean generated length | 75.704 |
| Mean valid length | 27.8 |
| Mean filtered-candidate length | 28.3953 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 50 |
| Filtered computational candidates | 43 |
| Filter pass rate | 86.0% |
| Mean valid MW | 248.6668 |
| Mean valid QED | 0.7077 |
| Rejection reasons | `{'qed_below_threshold': 4, 'mw_out_of_range': 3, 'lipinski_fail': 1, 'logp_out_of_range': 1}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | 0.6725 | 2.4779 | 199.3 | 0.065 | True | passed_all_filters |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | 0.9346 | 1.4569 | 277.34 | 2.804 | True | passed_all_filters |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | 0.8082 | 2.1281 | 267.28 | 2.81 | True | passed_all_filters |
| C=CNC1(C2CCO2)C(=O)NC(=O)NC(=O)C(C)C1C | 0.8988 | 0.6703 | 4.7161 | 281.31 | -0.115 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | 0.6373 | 2.0615 | 266.3 | 2.686 | True | passed_all_filters |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | 0.6968 | 3.2524 | 215.29 | 0.954 | True | passed_all_filters |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | 0.8151 | 3.1973 | 236.7 | 2.672 | True | passed_all_filters |
| Nc1ncnc2sc3c(c12)CC1CC(C3)N1 | 0.8849 | 0.7137 | 4.4714 | 232.31 | 1.103 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | Strong candidate | 0.6725 | 2.4779 | 199.3 | 0.065 |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | Strong candidate | 0.9346 | 1.4569 | 277.34 | 2.804 |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | Strong candidate | 0.7609 | 4.8104 | 272.37 | 1.521 |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | Strong candidate | 0.8082 | 2.1281 | 267.28 | 2.81 |
| C=CNC1(C2CCO2)C(=O)NC(=O)NC(=O)C(C)C1C | 0.8988 | Strong candidate | 0.6703 | 4.7161 | 281.31 | -0.115 |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | Strong candidate | 0.6373 | 2.0615 | 266.3 | 2.686 |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | Strong candidate | 0.6968 | 3.2524 | 215.29 | 0.954 |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | Strong candidate | 0.8151 | 3.1973 | 236.7 | 2.672 |
| Nc1ncnc2sc3c(c12)CC1CC(C3)N1 | 0.8849 | Strong candidate | 0.7137 | 4.4714 | 232.31 | 1.103 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 296, 'long_repetitive_fragment': 70, 'ring_closure_mismatch': 42, 'unbalanced_parentheses': 28, 'unbalanced_brackets': 14}`
- Invalid reason percentages: `{'rdkit_parse_failure': 65.78, 'long_repetitive_fragment': 15.56, 'ring_closure_mismatch': 9.33, 'unbalanced_parentheses': 6.22, 'unbalanced_brackets': 3.11}`
- Avg invalid length: `81.0267`
- Common invalid endings: `{'ccc1': 8, 'CCC1': 8, 'c1C2': 4, 'c1c2': 4, '2CC1': 4, 'CC)C': 3, 'OCC1': 3, '2)O1': 3, 'CC11': 3, 'c1C1': 3}`
- Top decoded tokens: `{'C': 8913, 'c': 6745, '1': 3360, 'O': 3039, '(': 2877, ')': 2843, '2': 1418, '=': 1254, 'H': 1074, 'N': 1047}`
