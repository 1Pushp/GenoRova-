# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes_guarded_retrain\genorova_diabetes_guarded_retrain_finetune_best.pt`
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
| Valid RDKit SMILES | 88 / 1000 |
| Validity | 8.8% |
| Unique valid molecules | 79 / 88 |
| Uniqueness among valid | 89.77% |
| Novel valid molecules | 67 / 88 |
| Novelty among valid | 76.14% |
| Novel unique molecules | 66 / 79 |
| Novelty among unique valid | 83.54% |
| Average clinical score (unique valid) | 0.8331 |
| Best clinical score (unique valid) | 0.9216 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 79 |
| Filtered computational candidates | 59 |
| Filter pass rate | 74.68% |
| Rejection reasons | `{'mw_out_of_range': 13, 'qed_below_threshold': 11, 'logp_out_of_range': 3}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CNC(=O)c1ncccc1OC(C)=O | 0.9216 | 0.6903 | 2.1146 | 194.19 | 0.366 | True | passed_all_filters |
| O=C(O)C(=O)C1COC1C1CCCC1 | 0.9206 | 0.6825 | 3.5741 | 198.22 | 0.845 | True | passed_all_filters |
| Cc1nnc(NS(=O)(=O)c2ccc(N)cc2)s1 | 0.9144 | 0.8173 | 2.1065 | 270.34 | 1.23 | True | passed_all_filters |
| CN1CCCCCC(=O)C(c2ccccn2)CC1=O | 0.8963 | 0.7771 | 3.2948 | 260.34 | 2.157 | True | passed_all_filters |
| NC1CCC(CO)CCC(=O)CC1Cl | 0.8958 | 0.6487 | 4.2429 | 219.71 | 1.063 | True | passed_all_filters |
| NC(=O)N1c2ccccc2CC(=O)c2ccccc21 | 0.8946 | 0.783 | 2.1583 | 252.27 | 2.642 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2cccc(N)c2C1=O | 0.8942 | 0.6373 | 2.1326 | 266.3 | 2.686 | True | passed_all_filters |
| NC1=CN=C(N)C=Nc2ccccc21 | 0.8938 | 0.6341 | 3.2614 | 186.22 | 1.017 | True | passed_all_filters |
| C=C(C)C(N)C(=O)N1CCCCNC1 | 0.8937 | 0.6154 | 3.6591 | 197.28 | 0.059 | True | passed_all_filters |
| CCC(CCO)C(=O)NC(=O)N1CCC1CO | 0.8917 | 0.619 | 3.4225 | 244.29 | -0.302 | True | passed_all_filters |
| CNOC(=O)Nc1ccc(NCc2ccc(F)cc2)nc1 | 0.8883 | 0.7377 | 2.2795 | 290.3 | 2.516 | True | passed_all_filters |
| CN1CCCOCC2=C3C(O)=CC=C3C(=O)C21 | 0.8873 | 0.677 | 4.0633 | 233.27 | 0.968 | True | passed_all_filters |
| CC1=CC=C2NC(=O)CN(CCC=O)C2=CC=CC=C2CC=C12 | 0.8866 | 0.8152 | 4.3239 | 308.38 | 2.548 | True | passed_all_filters |
| O=C1CC=CC=CC=C2CN2C(=O)NCN1 | 0.8865 | 0.5822 | 4.2091 | 219.24 | 0.485 | True | passed_all_filters |
| CNC(=O)c1ccccc1OC(C)=O | 0.8862 | 0.5621 | 1.6674 | 193.2 | 0.972 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | 0.6711 | 3.1753 | 200.28 | -0.047 | True | passed_all_filters |
| CCNCCC1CC=CNC=C2N=CC(CO)=CC=CC2=CC1 | 0.8833 | 0.6842 | 4.7619 | 313.45 | 2.826 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |
| NC(=O)c1c[nH]c2nc3ccc=3ccc(F)cc3c1CN=c3[nH]2 | 0.8786 | 0.6326 | 5.1496 | 309.3 | 1.392 | True | passed_all_filters |
| CC1=NCNCCCOCCCNCCCCCCC1 | 0.8731 | 0.7184 | 3.3636 | 283.46 | 2.735 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CNC(=O)c1ncccc1OC(C)=O | 0.9216 | Strong candidate | 0.6903 | 2.1146 | 194.19 | 0.366 |
| O=C(O)C(=O)C1COC1C1CCCC1 | 0.9206 | Strong candidate | 0.6825 | 3.5741 | 198.22 | 0.845 |
| Cc1nnc(NS(=O)(=O)c2ccc(N)cc2)s1 | 0.9144 | Strong candidate | 0.8173 | 2.1065 | 270.34 | 1.23 |
| CN1CCCCCC(=O)C(c2ccccn2)CC1=O | 0.8963 | Strong candidate | 0.7771 | 3.2948 | 260.34 | 2.157 |
| NC1CCC(CO)CCC(=O)CC1Cl | 0.8958 | Strong candidate | 0.6487 | 4.2429 | 219.71 | 1.063 |
| NC(=O)N1c2ccccc2CC(=O)c2ccccc21 | 0.8946 | Strong candidate | 0.783 | 2.1583 | 252.27 | 2.642 |
| Cc1cccc(C)c1N1C(=O)c2cccc(N)c2C1=O | 0.8942 | Strong candidate | 0.6373 | 2.1326 | 266.3 | 2.686 |
| NC1=CN=C(N)C=Nc2ccccc21 | 0.8938 | Strong candidate | 0.6341 | 3.2614 | 186.22 | 1.017 |
| C=C(C)C(N)C(=O)N1CCCCNC1 | 0.8937 | Strong candidate | 0.6154 | 3.6591 | 197.28 | 0.059 |
| CCC(CCO)C(=O)NC(=O)N1CCC1CO | 0.8917 | Strong candidate | 0.619 | 3.4225 | 244.29 | -0.302 |
| CNOC(=O)Nc1ccc(NCc2ccc(F)cc2)nc1 | 0.8883 | Strong candidate | 0.7377 | 2.2795 | 290.3 | 2.516 |
| CN1CCCOCC2=C3C(O)=CC=C3C(=O)C21 | 0.8873 | Strong candidate | 0.677 | 4.0633 | 233.27 | 0.968 |
| CC1=CC=C2NC(=O)CN(CCC=O)C2=CC=CC=C2CC=C12 | 0.8866 | Strong candidate | 0.8152 | 4.3239 | 308.38 | 2.548 |
| O=C1CC=CC=CC=C2CN2C(=O)NCN1 | 0.8865 | Strong candidate | 0.5822 | 4.2091 | 219.24 | 0.485 |
| CNC(=O)c1ccccc1OC(C)=O | 0.8862 | Strong candidate | 0.5621 | 1.6674 | 193.2 | 0.972 |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | Strong candidate | 0.6711 | 3.1753 | 200.28 | -0.047 |
| CCNCCC1CC=CNC=C2N=CC(CO)=CC=CC2=CC1 | 0.8833 | Strong candidate | 0.6842 | 4.7619 | 313.45 | 2.826 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |
| NC(=O)c1c[nH]c2nc3ccc=3ccc(F)cc3c1CN=c3[nH]2 | 0.8786 | Strong candidate | 0.6326 | 5.1496 | 309.3 | 1.392 |
| CC1=NCNCCCOCCCNCCCCCCC1 | 0.8731 | Strong candidate | 0.7184 | 3.3636 | 283.46 | 2.735 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 520, 'long_repetitive_fragment': 157, 'ring_closure_mismatch': 132, 'unbalanced_parentheses': 58, 'unbalanced_brackets': 45}`
- Invalid reason percentages: `{'rdkit_parse_failure': 57.02, 'long_repetitive_fragment': 17.21, 'ring_closure_mismatch': 14.47, 'unbalanced_parentheses': 6.36, 'unbalanced_brackets': 4.93}`
- Avg invalid length: `83.5329`
- Common invalid endings: `{'CCC1': 12, 'ccc1': 11, 'O)C1': 7, 'c2c1': 6, '2CC1': 6, 'C)C1': 6, 'CcC1': 6, 'H1C2': 5, '2)O1': 5, 'C1C1': 5}`
- Top decoded tokens: `{'C': 17018, 'c': 13667, '1': 6978, 'O': 6756, '(': 6045, ')': 5974, '2': 3049, '=': 2866, 'N': 2140, 'H': 2112}`
