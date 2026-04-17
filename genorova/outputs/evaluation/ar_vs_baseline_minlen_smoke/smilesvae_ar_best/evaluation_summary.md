# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\ar\smilesvae_ar_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocab_ar.json`
- Strategy: `guided`
- Temperature: `0.25`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- AR minimum generation length: `20`
- Requested samples: `200`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `None`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 144 / 200 |
| Validity | 72.0% |
| Unique valid molecules | 143 / 144 |
| Uniqueness among valid | 99.31% |
| Novel valid molecules | 144 / 144 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 143 / 143 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.8437 |
| Best clinical score (unique valid) | 0.9568 |
| Mean generated length | 37.595 |
| Mean valid length | 36.4306 |
| Mean filtered-candidate length | 36.2296 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 143 |
| Filtered computational candidates | 135 |
| Filter pass rate | 94.41% |
| Mean valid MW | 304.2104 |
| Mean valid QED | 0.7998 |
| Rejection reasons | `{'lipinski_fail': 8, 'logp_out_of_range': 8, 'qed_below_threshold': 1}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COC(=O)C1CCN(C(=O)c2ccc(C(N)=O)cc2)CC1 | 0.9568 | 0.8341 | 1.7779 | 290.32 | 0.811 | True | passed_all_filters |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCO3)cc1 | 0.9511 | 0.9364 | 1.7886 | 319.34 | 2.071 | True | passed_all_filters |
| O=C(c1ccc2c(c1)OCCO2)N1CCCC(CO)C1=O | 0.9393 | 0.8168 | 2.7861 | 291.3 | 0.829 | True | passed_all_filters |
| N#CC(NC(=O)C1CCCCC1)N1CCOCC1 | 0.9381 | 0.8078 | 3.089 | 251.33 | 0.865 | True | passed_all_filters |
| Nc1nn(Cc2ccc3c(c2)CCCC3)c(=O)[nH]c1=O | 0.9361 | 0.8292 | 2.4746 | 272.31 | 0.441 | True | passed_all_filters |
| CC1(C)C(=O)CC1C(=O)N1CCCC1C(=O)Nc1ccc(F)cc1 | 0.9344 | 0.924 | 3.0301 | 332.37 | 2.37 | True | passed_all_filters |
| NC(=O)C1CCCN(C(=O)Cn2c(=O)[nH]c3cc(Cl)ccc3c2=O)C1 | 0.9321 | 0.8004 | 2.7167 | 364.79 | 0.067 | True | passed_all_filters |
| CC(=O)N(C)C(=O)N1CCC(C(=O)Nc2ccc(F)c(F)c2)CC1 | 0.9307 | 0.8981 | 2.2576 | 339.34 | 2.214 | True | passed_all_filters |
| NC(=O)C1(NC(=O)C2CCCN(c3ccccc3)CC2)CCCC1 | 0.9295 | 0.8891 | 2.6151 | 329.44 | 2.207 | True | passed_all_filters |
| N#CC(NC(=O)C1CCN(C(=O)c2ccc(Cl)cc2)CC1)N1CCCC1 | 0.9277 | 0.8765 | 2.864 | 374.87 | 2.254 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| COC(=O)C1CCN(C(=O)c2ccc(C(N)=O)cc2)CC1 | 0.9568 | Strong candidate | 0.8341 | 1.7779 | 290.32 | 0.811 |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCO3)cc1 | 0.9511 | Strong candidate | 0.9364 | 1.7886 | 319.34 | 2.071 |
| O=C(c1ccc2c(c1)OCCO2)N1CCCC(CO)C1=O | 0.9393 | Strong candidate | 0.8168 | 2.7861 | 291.3 | 0.829 |
| N#CC(NC(=O)C1CCCCC1)N1CCOCC1 | 0.9381 | Strong candidate | 0.8078 | 3.089 | 251.33 | 0.865 |
| Nc1nn(Cc2ccc3c(c2)CCCC3)c(=O)[nH]c1=O | 0.9361 | Strong candidate | 0.8292 | 2.4746 | 272.31 | 0.441 |
| CC1(C)C(=O)CC1C(=O)N1CCCC1C(=O)Nc1ccc(F)cc1 | 0.9344 | Strong candidate | 0.924 | 3.0301 | 332.37 | 2.37 |
| NC(=O)C1CCCN(C(=O)Cn2c(=O)[nH]c3cc(Cl)ccc3c2=O)C1 | 0.9321 | Strong candidate | 0.8004 | 2.7167 | 364.79 | 0.067 |
| CC(=O)N(C)C(=O)N1CCC(C(=O)Nc2ccc(F)c(F)c2)CC1 | 0.9307 | Strong candidate | 0.8981 | 2.2576 | 339.34 | 2.214 |
| NC(=O)C1(NC(=O)C2CCCN(c3ccccc3)CC2)CCCC1 | 0.9295 | Strong candidate | 0.8891 | 2.6151 | 329.44 | 2.207 |
| O=C(COC(=O)c1ccc2c(c1)OCO2)Nc1ccccc1 | 0.9277 | Strong candidate | 0.8762 | 1.7043 | 299.28 | 2.211 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'ring_closure_mismatch': 19, 'unbalanced_parentheses': 17, 'long_repetitive_fragment': 10, 'rdkit_parse_failure': 10}`
- Invalid reason percentages: `{'ring_closure_mismatch': 33.93, 'unbalanced_parentheses': 30.36, 'long_repetitive_fragment': 17.86, 'rdkit_parse_failure': 17.86}`
- Avg invalid length: `40.5893`
- Common invalid endings: `{')cc1': 6, 'cc21': 5, ')CC1': 5, 'ccc1': 5, '(C)C': 3, '2)c1': 3, 'c2c1': 3, 'nH]1': 2, 'C1=O': 2, 'CCC2': 2}`
- Top decoded tokens: `{'c': 1948, 'C': 1546, '(': 706, ')': 701, '1': 555, '2': 393, 'O': 364, 'N': 332, '=': 288, 'n': 218}`
