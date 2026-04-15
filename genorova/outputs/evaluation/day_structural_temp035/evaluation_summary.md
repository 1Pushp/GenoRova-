# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_finetune_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.35`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- Requested samples: `1000`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `finetune`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 86 / 1000 |
| Validity | 8.6% |
| Unique valid molecules | 78 / 86 |
| Uniqueness among valid | 90.7% |
| Novel valid molecules | 68 / 86 |
| Novelty among valid | 79.07% |
| Novel unique molecules | 66 / 78 |
| Novelty among unique valid | 84.62% |
| Average clinical score (unique valid) | 0.8347 |
| Best clinical score (unique valid) | 0.9224 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 78 |
| Filtered computational candidates | 65 |
| Filter pass rate | 83.33% |
| Rejection reasons | `{'qed_below_threshold': 6, 'logp_out_of_range': 5, 'mw_out_of_range': 5, 'lipinski_fail': 3}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CN1C(=O)N1C(=O)NCC(CCN)C1CCC1 | 0.9224 | 0.6958 | 3.6095 | 240.31 | 0.743 | True | passed_all_filters |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | 0.6725 | 2.4779 | 199.3 | 0.065 | True | passed_all_filters |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | 0.9346 | 1.4569 | 277.34 | 2.804 | True | passed_all_filters |
| CCC(CO)C(=O)C1=CC=C(C)C(=O)OCC(Cl)=C1Cl | 0.9183 | 0.8094 | 4.4006 | 319.18 | 2.693 | True | passed_all_filters |
| NC(=O)c1cc2c(-c3ccc(F)cc3)cnc-2ns1 | 0.9142 | 0.7797 | 2.5072 | 273.29 | 2.548 | True | passed_all_filters |
| CC(=O)NC(=O)CNCc1ccccc1 | 0.9127 | 0.7511 | 1.7457 | 206.25 | 0.439 | True | passed_all_filters |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True | passed_all_filters |
| NCCCCC(N)C(=O)N1CCCC1 | 0.9111 | 0.6152 | 2.464 | 199.3 | 0.065 | True | passed_all_filters |
| CNCC1=CC=C(C(C)C(=O)O)C(=O)CC1 | 0.91 | 0.7498 | 3.6536 | 223.27 | 1.142 | True | passed_all_filters |
| CCOc1cc2ccc1C(=O)C(OCC(C)=O)C1CCC21 | 0.9045 | 0.8357 | 4.3497 | 288.34 | 2.749 | True | passed_all_filters |
| CC(C)OC(=O)C1CCCOCCNO1 | 0.9038 | 0.6878 | 3.9229 | 217.26 | 0.638 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | 0.8082 | 2.1281 | 267.28 | 2.81 | True | passed_all_filters |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | 0.5366 | 1.6474 | 179.17 | 0.711 | True | passed_all_filters |
| C=CNC1(C2CCO2)C(=O)NC(=O)NC(=O)C(C)C1C | 0.8988 | 0.6703 | 4.7161 | 281.31 | -0.115 | True | passed_all_filters |
| CC(C)C(=O)NOC(=O)C1CC1C | 0.8984 | 0.6494 | 3.4804 | 185.22 | 0.873 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | 0.6373 | 2.0615 | 266.3 | 2.686 | True | passed_all_filters |
| CC1NC2Cc3sc4ncnc(N)c4c3CC1C2 | 0.891 | 0.7571 | 4.8053 | 260.37 | 1.739 | True | passed_all_filters |
| COC(=O)c1ccccc1CC1CCCOCCOC1 | 0.884 | 0.7967 | 3.0717 | 278.35 | 2.459 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | 0.6711 | 3.1753 | 200.28 | -0.047 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CN1C(=O)N1C(=O)NCC(CCN)C1CCC1 | 0.9224 | Strong candidate | 0.6958 | 3.6095 | 240.31 | 0.743 |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | Strong candidate | 0.6725 | 2.4779 | 199.3 | 0.065 |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | Strong candidate | 0.9346 | 1.4569 | 277.34 | 2.804 |
| CCC(CO)C(=O)C1=CC=C(C)C(=O)OCC(Cl)=C1Cl | 0.9183 | Strong candidate | 0.8094 | 4.4006 | 319.18 | 2.693 |
| NC(=O)c1cc2c(-c3ccc(F)cc3)cnc-2ns1 | 0.9142 | Strong candidate | 0.7797 | 2.5072 | 273.29 | 2.548 |
| CC(=O)NC(=O)CNCc1ccccc1 | 0.9127 | Strong candidate | 0.7511 | 1.7457 | 206.25 | 0.439 |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | Strong candidate | 0.7609 | 4.8104 | 272.37 | 1.521 |
| NCCCCC(N)C(=O)N1CCCC1 | 0.9111 | Strong candidate | 0.6152 | 2.464 | 199.3 | 0.065 |
| CNCC1=CC=C(C(C)C(=O)O)C(=O)CC1 | 0.91 | Strong candidate | 0.7498 | 3.6536 | 223.27 | 1.142 |
| CCOc1cc2ccc1C(=O)C(OCC(C)=O)C1CCC21 | 0.9045 | Strong candidate | 0.8357 | 4.3497 | 288.34 | 2.749 |
| CC(C)OC(=O)C1CCCOCCNO1 | 0.9038 | Strong candidate | 0.6878 | 3.9229 | 217.26 | 0.638 |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | Strong candidate | 0.8082 | 2.1281 | 267.28 | 2.81 |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | Strong candidate | 0.5366 | 1.6474 | 179.17 | 0.711 |
| C=CNC1(C2CCO2)C(=O)NC(=O)NC(=O)C(C)C1C | 0.8988 | Strong candidate | 0.6703 | 4.7161 | 281.31 | -0.115 |
| CC(C)C(=O)NOC(=O)C1CC1C | 0.8984 | Strong candidate | 0.6494 | 3.4804 | 185.22 | 0.873 |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | Strong candidate | 0.6373 | 2.0615 | 266.3 | 2.686 |
| CC1NC2Cc3sc4ncnc(N)c4c3CC1C2 | 0.891 | Strong candidate | 0.7571 | 4.8053 | 260.37 | 1.739 |
| COC(=O)c1ccccc1CC1CCCOCCOC1 | 0.884 | Strong candidate | 0.7967 | 3.0717 | 278.35 | 2.459 |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | Strong candidate | 0.6711 | 3.1753 | 200.28 | -0.047 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 542, 'long_repetitive_fragment': 138, 'ring_closure_mismatch': 126, 'unbalanced_parentheses': 60, 'unbalanced_brackets': 48}`
- Invalid reason percentages: `{'rdkit_parse_failure': 59.3, 'long_repetitive_fragment': 15.1, 'ring_closure_mismatch': 13.79, 'unbalanced_parentheses': 6.56, 'unbalanced_brackets': 5.25}`
- Avg invalid length: `81.9508`
- Common invalid endings: `{'ccc1': 13, 'CCC1': 12, ')cc1': 8, 'Ccc1': 7, 'C)C1': 6, 'O)C1': 6, 'O)c1': 6, 'CCCC': 5, '1C#N': 5, '2CC1': 5}`
- Top decoded tokens: `{'C': 17950, 'c': 13270, '1': 6776, 'O': 6365, '(': 5905, ')': 5828, '2': 2902, '=': 2603, 'H': 2212, 'N': 2157}`
