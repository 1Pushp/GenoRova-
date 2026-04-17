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
- Requested samples: `200`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `finetune`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 24 / 200 |
| Validity | 12.0% |
| Unique valid molecules | 24 / 24 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 19 / 24 |
| Novelty among valid | 79.17% |
| Novel unique molecules | 19 / 24 |
| Novelty among unique valid | 79.17% |
| Average clinical score (unique valid) | 0.8342 |
| Best clinical score (unique valid) | 0.9191 |
| Mean generated length | 74.8 |
| Mean valid length | 27.6667 |
| Mean filtered-candidate length | 27.8 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 24 |
| Filtered computational candidates | 20 |
| Filter pass rate | 83.33% |
| Mean valid MW | 249.5992 |
| Mean valid QED | 0.7087 |
| Rejection reasons | `{'mw_out_of_range': 2, 'qed_below_threshold': 2, 'lipinski_fail': 1, 'logp_out_of_range': 1}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | 0.6725 | 2.4779 | 199.3 | 0.065 | True | passed_all_filters |
| COc1ccc(NS(=O)(=O)c2ccc(F)cc2)cc1 | 0.9187 | 0.9369 | 1.4821 | 281.31 | 2.635 | True | passed_all_filters |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True | passed_all_filters |
| NC(CO)C(=O)C1CCCC1 | 0.9102 | 0.6088 | 2.7666 | 157.21 | 0.065 | True | passed_all_filters |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | 0.6968 | 3.2524 | 215.29 | 0.954 | True | passed_all_filters |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | 0.8151 | 3.1973 | 236.7 | 2.672 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCCCC1 | 0.8567 | 0.7442 | 2.6619 | 198.31 | 1.372 | True | passed_all_filters |
| CCCCC(N)C(=O)N1CCCCC1 | 0.8567 | 0.7441 | 2.3049 | 198.31 | 1.516 | True | passed_all_filters |
| CC1=CC=C(C(=O)C2C(C)CC3OCC32)C1C | 0.8549 | 0.7315 | 4.8299 | 232.32 | 2.749 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | Strong candidate | 0.6725 | 2.4779 | 199.3 | 0.065 |
| COc1ccc(NS(=O)(=O)c2ccc(F)cc2)cc1 | 0.9187 | Strong candidate | 0.9369 | 1.4821 | 281.31 | 2.635 |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | Strong candidate | 0.7609 | 4.8104 | 272.37 | 1.521 |
| NC(CO)C(=O)C1CCCC1 | 0.9102 | Strong candidate | 0.6088 | 2.7666 | 157.21 | 0.065 |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | Strong candidate | 0.6968 | 3.2524 | 215.29 | 0.954 |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | Strong candidate | 0.8151 | 3.1973 | 236.7 | 2.672 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |
| CC(C)(O)C1(CCSCN)CCCCCCOC1=O | 0.8696 | Strong candidate | 0.4614 | 4.3278 | 289.44 | 2.291 |
| CCC(C)C(N)C(=O)N1CCCCC1 | 0.8567 | Strong candidate | 0.7442 | 2.6619 | 198.31 | 1.372 |
| CCCCC(N)C(=O)N1CCCCC1 | 0.8567 | Strong candidate | 0.7441 | 2.3049 | 198.31 | 1.516 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'rdkit_parse_failure': 116, 'long_repetitive_fragment': 31, 'unbalanced_parentheses': 13, 'ring_closure_mismatch': 12, 'unbalanced_brackets': 4}`
- Invalid reason percentages: `{'rdkit_parse_failure': 65.91, 'long_repetitive_fragment': 17.61, 'unbalanced_parentheses': 7.39, 'ring_closure_mismatch': 6.82, 'unbalanced_brackets': 2.27}`
- Avg invalid length: `81.2273`
- Common invalid endings: `{'ccc1': 3, 'CC)C': 2, '2)O1': 2, 'CC11': 2, 'nH]1': 2, '1CC1': 2, '21C1': 2, '1C2C': 1, '2CH]': 1, '1O1c': 1}`
- Top decoded tokens: `{'C': 3495, 'c': 2652, '1': 1268, 'O': 1168, '(': 1146, ')': 1132, '2': 554, '=': 521, 'H': 440, 'N': 425}`
