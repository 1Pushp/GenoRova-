# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_finetune_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.25`
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
| Valid RDKit SMILES | 98 / 1000 |
| Validity | 9.8% |
| Unique valid molecules | 86 / 98 |
| Uniqueness among valid | 87.76% |
| Novel valid molecules | 73 / 98 |
| Novelty among valid | 74.49% |
| Novel unique molecules | 70 / 86 |
| Novelty among unique valid | 81.4% |
| Average clinical score (unique valid) | 0.834 |
| Best clinical score (unique valid) | 0.9275 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 86 |
| Filtered computational candidates | 72 |
| Filter pass rate | 83.72% |
| Rejection reasons | `{'qed_below_threshold': 9, 'mw_out_of_range': 6, 'lipinski_fail': 3, 'logp_out_of_range': 3}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CCC(CO)C(=O)C1=CC=C(N)C(=O)OCC(Cl)=C1Cl | 0.9275 | 0.7679 | 4.5565 | 320.17 | 1.589 | True | passed_all_filters |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | 0.6725 | 2.4779 | 199.3 | 0.065 | True | passed_all_filters |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | 0.9346 | 1.4569 | 277.34 | 2.804 | True | passed_all_filters |
| CCC1(CC)C(=O)NC(=O)N(C)C1=O | 0.917 | 0.6569 | 2.7668 | 198.22 | 0.501 | True | passed_all_filters |
| NC(=O)c1cc2c(-c3ccc(F)cc3)cnc-2ns1 | 0.9142 | 0.7797 | 2.5072 | 273.29 | 2.548 | True | passed_all_filters |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True | passed_all_filters |
| CNCC1=CC=C(C(C)C(=O)O)C(=O)CC1 | 0.91 | 0.7498 | 3.6536 | 223.27 | 1.142 | True | passed_all_filters |
| CCOc1cc2ccc1C(=O)C(OCC(C)=O)C1CCC21 | 0.9045 | 0.8357 | 4.3497 | 288.34 | 2.749 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | 0.8082 | 2.1281 | 267.28 | 2.81 | True | passed_all_filters |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | 0.5366 | 1.6474 | 179.17 | 0.711 | True | passed_all_filters |
| C=CNC1(C2CCO2)C(=O)NC(=O)NC(=O)C(C)C1C | 0.8988 | 0.6703 | 4.7161 | 281.31 | -0.115 | True | passed_all_filters |
| CC(C)C(=O)NOC(=O)C1CC1C | 0.8984 | 0.6494 | 3.4804 | 185.22 | 0.873 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | 0.6373 | 2.0615 | 266.3 | 2.686 | True | passed_all_filters |
| C=C1Nc2cc(N)ccc2NC(=O)CC2C=CC=C12 | 0.8922 | 0.6226 | 4.1201 | 253.3 | 2.649 | True | passed_all_filters |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | 0.6968 | 3.2524 | 215.29 | 0.954 | True | passed_all_filters |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | 0.8151 | 3.1973 | 236.7 | 2.672 | True | passed_all_filters |
| Nc1ncnc2sc3c(c12)CC1CC(C3)N1 | 0.8849 | 0.7137 | 4.4714 | 232.31 | 1.103 | True | passed_all_filters |
| COC(=O)c1ccccc1CC1CCCOCCOC1 | 0.884 | 0.7967 | 3.0717 | 278.35 | 2.459 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | 0.6711 | 3.1753 | 200.28 | -0.047 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CCC(CO)C(=O)C1=CC=C(N)C(=O)OCC(Cl)=C1Cl | 0.9275 | Strong candidate | 0.7679 | 4.5565 | 320.17 | 1.589 |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | Strong candidate | 0.6725 | 2.4779 | 199.3 | 0.065 |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | Strong candidate | 0.9346 | 1.4569 | 277.34 | 2.804 |
| CCC1(CC)C(=O)NC(=O)N(C)C1=O | 0.917 | Strong candidate | 0.6569 | 2.7668 | 198.22 | 0.501 |
| NC(=O)c1cc2c(-c3ccc(F)cc3)cnc-2ns1 | 0.9142 | Strong candidate | 0.7797 | 2.5072 | 273.29 | 2.548 |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | Strong candidate | 0.7609 | 4.8104 | 272.37 | 1.521 |
| CNCC1=CC=C(C(C)C(=O)O)C(=O)CC1 | 0.91 | Strong candidate | 0.7498 | 3.6536 | 223.27 | 1.142 |
| CCOc1cc2ccc1C(=O)C(OCC(C)=O)C1CCC21 | 0.9045 | Strong candidate | 0.8357 | 4.3497 | 288.34 | 2.749 |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | Strong candidate | 0.8082 | 2.1281 | 267.28 | 2.81 |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | Strong candidate | 0.5366 | 1.6474 | 179.17 | 0.711 |
| C=CNC1(C2CCO2)C(=O)NC(=O)NC(=O)C(C)C1C | 0.8988 | Strong candidate | 0.6703 | 4.7161 | 281.31 | -0.115 |
| CC(C)C(=O)NOC(=O)C1CC1C | 0.8984 | Strong candidate | 0.6494 | 3.4804 | 185.22 | 0.873 |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | Strong candidate | 0.6373 | 2.0615 | 266.3 | 2.686 |
| C=C1Nc2cc(N)ccc2NC(=O)CC2C=CC=C12 | 0.8922 | Strong candidate | 0.6226 | 4.1201 | 253.3 | 2.649 |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | Strong candidate | 0.6968 | 3.2524 | 215.29 | 0.954 |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | Strong candidate | 0.8151 | 3.1973 | 236.7 | 2.672 |
| Nc1ncnc2sc3c(c12)CC1CC(C3)N1 | 0.8849 | Strong candidate | 0.7137 | 4.4714 | 232.31 | 1.103 |
| COC(=O)c1ccccc1CC1CCCOCCOC1 | 0.884 | Strong candidate | 0.7967 | 3.0717 | 278.35 | 2.459 |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | Strong candidate | 0.6711 | 3.1753 | 200.28 | -0.047 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 576, 'long_repetitive_fragment': 146, 'ring_closure_mismatch': 88, 'unbalanced_parentheses': 58, 'unbalanced_brackets': 34}`
- Invalid reason percentages: `{'rdkit_parse_failure': 63.86, 'long_repetitive_fragment': 16.19, 'ring_closure_mismatch': 9.76, 'unbalanced_parentheses': 6.43, 'unbalanced_brackets': 3.77}`
- Avg invalid length: `81.4534`
- Common invalid endings: `{'ccc1': 13, 'CCC1': 12, '2)O1': 9, 'C)C1': 9, ')CC1': 8, 'c2c1': 6, 'c1c2': 5, '2CC1': 5, '1C#N': 5, '2cc1': 5}`
- Top decoded tokens: `{'C': 17938, 'c': 13314, '1': 6673, 'O': 6077, '(': 5814, ')': 5745, '2': 2837, '=': 2575, 'H': 2242, 'N': 2042}`
