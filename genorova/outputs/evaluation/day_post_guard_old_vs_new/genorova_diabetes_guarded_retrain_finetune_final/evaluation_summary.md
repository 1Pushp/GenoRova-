# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes_guarded_retrain\genorova_diabetes_guarded_retrain_finetune_final.pt`
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
| Valid RDKit SMILES | 90 / 1000 |
| Validity | 9.0% |
| Unique valid molecules | 73 / 90 |
| Uniqueness among valid | 81.11% |
| Novel valid molecules | 67 / 90 |
| Novelty among valid | 74.44% |
| Novel unique molecules | 61 / 73 |
| Novelty among unique valid | 83.56% |
| Average clinical score (unique valid) | 0.8178 |
| Best clinical score (unique valid) | 0.9296 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 73 |
| Filtered computational candidates | 54 |
| Filter pass rate | 73.97% |
| Rejection reasons | `{'mw_out_of_range': 13, 'qed_below_threshold': 12, 'logp_out_of_range': 3, 'lipinski_fail': 2}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COC1=CC=C2C=CC3=c4cc(Cc5cnc(N)nc5)c(n43)=C1OC2 | 0.9296 | 0.8901 | 5.0604 | 332.36 | 0.586 | True | passed_all_filters |
| COC1=C(O)CC(O)CC(Cc2cnc(C)nc2N)=C1 | 0.928 | 0.7718 | 3.8322 | 277.32 | 1.407 | True | passed_all_filters |
| CCC1CCOCC(=O)NC(=O)N1CCC1COCC1C | 0.9242 | 0.8516 | 4.5012 | 298.38 | 1.396 | True | passed_all_filters |
| CN(c1cccccc(=O)c2ccccc2cc1)C(O)CO | 0.9242 | 0.8515 | 3.1623 | 297.35 | 2.071 | True | passed_all_filters |
| CCCCC(N)C(=O)N(C)C(C)=O | 0.9224 | 0.6954 | 2.9181 | 186.25 | 0.509 | True | passed_all_filters |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | 0.6725 | 2.4779 | 199.3 | 0.065 | True | passed_all_filters |
| CC(N)NC(=O)N1CCCCCOCC1C | 0.9169 | 0.6562 | 3.6706 | 229.32 | 0.892 | True | passed_all_filters |
| Cc1ncc(NS(=O)(=O)c2ccc(N)cc2)s1 | 0.9165 | 0.8325 | 2.3866 | 269.35 | 1.835 | True | passed_all_filters |
| NCCCCC(N)C(=O)N1CCCC1 | 0.9111 | 0.6152 | 2.464 | 199.3 | 0.065 | True | passed_all_filters |
| CCn1cc(C(=O)O)c(=O)c2cc(F)c(N3CCNCC3)cc21 | 0.9097 | 0.891 | 2.4121 | 319.34 | 1.268 | True | passed_all_filters |
| C=C1CC2COCC(NC(C)=O)CCC2N1 | 0.9044 | 0.6922 | 4.1593 | 224.3 | 0.793 | True | passed_all_filters |
| COc1ccccc1OCC(O)C1CCCNC1 | 0.9038 | 0.8311 | 2.9129 | 251.33 | 1.434 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | 0.8082 | 2.1281 | 267.28 | 2.81 | True | passed_all_filters |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | 0.5366 | 1.6474 | 179.17 | 0.711 | True | passed_all_filters |
| OCCNc1ncnc2sc3c(c12)C1C=CC3C1 | 0.8837 | 0.8299 | 4.6711 | 259.33 | 2.236 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |
| NC(=O)n1c2cccc-2cc(=O)c2ccccc21 | 0.8761 | 0.6509 | 2.2731 | 238.25 | 2.033 | True | passed_all_filters |
| CC(Cc1ccccc1)C(=O)NC1CCC1 | 0.868 | 0.8247 | 2.1276 | 217.31 | 2.534 | True | passed_all_filters |
| CC(N)CC(=O)N1CCCCC1 | 0.8655 | 0.664 | 2.383 | 170.26 | 0.736 | True | passed_all_filters |
| CC(CN)C(=O)N1CCCCC1 | 0.8648 | 0.6591 | 2.4563 | 170.26 | 0.594 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| COC1=CC=C2C=CC3=c4cc(Cc5cnc(N)nc5)c(n43)=C1OC2 | 0.9296 | Strong candidate | 0.8901 | 5.0604 | 332.36 | 0.586 |
| COC1=C(O)CC(O)CC(Cc2cnc(C)nc2N)=C1 | 0.928 | Strong candidate | 0.7718 | 3.8322 | 277.32 | 1.407 |
| CN(c1cccccc(=O)c2ccccc2cc1)C(O)CO | 0.9242 | Strong candidate | 0.8515 | 3.1623 | 297.35 | 2.071 |
| CCC1CCOCC(=O)NC(=O)N1CCC1COCC1C | 0.9242 | Strong candidate | 0.8516 | 4.5012 | 298.38 | 1.396 |
| CCCCC(N)C(=O)N(C)C(C)=O | 0.9224 | Strong candidate | 0.6954 | 2.9181 | 186.25 | 0.509 |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | Strong candidate | 0.6725 | 2.4779 | 199.3 | 0.065 |
| CC(N)NC(=O)N1CCCCCOCC1C | 0.9169 | Strong candidate | 0.6562 | 3.6706 | 229.32 | 0.892 |
| Cc1ncc(NS(=O)(=O)c2ccc(N)cc2)s1 | 0.9165 | Strong candidate | 0.8325 | 2.3866 | 269.35 | 1.835 |
| NCCCCC(N)C(=O)N1CCCC1 | 0.9111 | Strong candidate | 0.6152 | 2.464 | 199.3 | 0.065 |
| CCn1cc(C(=O)O)c(=O)c2cc(F)c(N3CCNCC3)cc21 | 0.9097 | Strong candidate | 0.891 | 2.4121 | 319.34 | 1.268 |
| C=C1CC2COCC(NC(C)=O)CCC2N1 | 0.9044 | Strong candidate | 0.6922 | 4.1593 | 224.3 | 0.793 |
| COc1ccccc1OCC(O)C1CCCNC1 | 0.9038 | Strong candidate | 0.8311 | 2.9129 | 251.33 | 1.434 |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | Strong candidate | 0.8082 | 2.1281 | 267.28 | 2.81 |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | Strong candidate | 0.5366 | 1.6474 | 179.17 | 0.711 |
| OCCNc1ncnc2sc3c(c12)C1C=CC3C1 | 0.8837 | Strong candidate | 0.8299 | 4.6711 | 259.33 | 2.236 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |
| NC(=O)n1c2cccc-2cc(=O)c2ccccc21 | 0.8761 | Strong candidate | 0.6509 | 2.2731 | 238.25 | 2.033 |
| CC(Cc1ccccc1)C(=O)NC1CCC1 | 0.868 | Strong candidate | 0.8247 | 2.1276 | 217.31 | 2.534 |
| CC(N)CC(=O)N1CCCCC1 | 0.8655 | Strong candidate | 0.664 | 2.383 | 170.26 | 0.736 |
| CC(CN)C(=O)N1CCCCC1 | 0.8648 | Strong candidate | 0.6591 | 2.4563 | 170.26 | 0.594 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 497, 'long_repetitive_fragment': 174, 'ring_closure_mismatch': 137, 'unbalanced_parentheses': 61, 'unbalanced_brackets': 41}`
- Invalid reason percentages: `{'rdkit_parse_failure': 54.62, 'long_repetitive_fragment': 19.12, 'ring_closure_mismatch': 15.05, 'unbalanced_parentheses': 6.7, 'unbalanced_brackets': 4.51}`
- Avg invalid length: `80.2462`
- Common invalid endings: `{'ccc1': 13, 'C)C1': 10, 'CCC1': 10, 'c1c2': 9, ')cc1': 8, '2cc1': 7, 'c1c1': 6, '2)O1': 5, 'c2c1': 5, 'O)c1': 5}`
- Top decoded tokens: `{'C': 16409, 'c': 13577, '1': 6970, 'O': 6217, '(': 5506, ')': 5429, '2': 2984, '=': 2714, 'H': 2118, 'N': 2117}`
