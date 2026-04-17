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
- Requested samples: `500`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `None`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 371 / 500 |
| Validity | 74.2% |
| Unique valid molecules | 367 / 371 |
| Uniqueness among valid | 98.92% |
| Novel valid molecules | 371 / 371 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 367 / 367 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.8456 |
| Best clinical score (unique valid) | 0.9591 |
| Mean generated length | 37.312 |
| Mean valid length | 36.5849 |
| Mean filtered-candidate length | 36.3639 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 367 |
| Filtered computational candidates | 349 |
| Filter pass rate | 95.1% |
| Mean valid MW | 305.6385 |
| Mean valid QED | 0.8016 |
| Rejection reasons | `{'lipinski_fail': 16, 'logp_out_of_range': 16, 'qed_below_threshold': 3}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CN(C)S(=O)(=O)c1ccc(C(=O)N2CCC(C(N)=O)CC2)cc1 | 0.9591 | 0.8508 | 1.9181 | 339.42 | 0.274 | True | passed_all_filters |
| NC(=O)C1CCCN1C(=O)C1CCCC1C(=O)N1CCCC1 | 0.9553 | 0.8239 | 3.1574 | 307.39 | 0.501 | True | passed_all_filters |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCO3)cc1 | 0.9511 | 0.9364 | 1.7886 | 319.34 | 2.071 | True | passed_all_filters |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCCO3)cc1 | 0.9502 | 0.9302 | 1.8353 | 333.37 | 2.114 | True | passed_all_filters |
| CNC(=O)CN(C)C(=O)C1CCN(Cc2ccccc2)C(=O)C1 | 0.9462 | 0.8658 | 2.5606 | 317.39 | 0.63 | True | passed_all_filters |
| CNS(=O)(=O)c1cccc(NC(=O)N2CCCC2CO)c1 | 0.946 | 0.7571 | 2.5472 | 313.38 | 0.583 | True | passed_all_filters |
| COC(=O)c1c(C(=O)N2CCCC(C(=O)N(C)C)CC2)cnn1C | 0.9453 | 0.7522 | 2.7955 | 336.39 | 0.537 | True | passed_all_filters |
| CC1=C(C)N=C(C2CCCN(C(=O)c3ccc(C(N)=O)cc3)N2)CC1 | 0.944 | 0.8856 | 3.445 | 340.43 | 2.423 | True | passed_all_filters |
| NS(=O)(=O)c1ccc(NCC2CCCO2)cc1Cl | 0.9435 | 0.8819 | 2.644 | 290.77 | 1.578 | True | passed_all_filters |
| O=C(Nc1ccc(C(=O)N2CCCC2)cc1)NC1CC(=O)N(C2CC2)C1 | 0.9408 | 0.8632 | 2.5579 | 356.43 | 1.807 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CN(C)S(=O)(=O)c1ccc(C(=O)N2CCC(C(N)=O)CC2)cc1 | 0.9591 | Strong candidate | 0.8508 | 1.9181 | 339.42 | 0.274 |
| NC(=O)C1CCCN1C(=O)C1CCCC1C(=O)N1CCCC1 | 0.9553 | Strong candidate | 0.8239 | 3.1574 | 307.39 | 0.501 |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCO3)cc1 | 0.9511 | Strong candidate | 0.9364 | 1.7886 | 319.34 | 2.071 |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCCO3)cc1 | 0.9502 | Strong candidate | 0.9302 | 1.8353 | 333.37 | 2.114 |
| CNC(=O)CN(C)C(=O)C1CCN(Cc2ccccc2)C(=O)C1 | 0.9462 | Strong candidate | 0.8658 | 2.5606 | 317.39 | 0.63 |
| CNS(=O)(=O)c1cccc(NC(=O)N2CCCC2CO)c1 | 0.946 | Strong candidate | 0.7571 | 2.5472 | 313.38 | 0.583 |
| COC(=O)c1c(C(=O)N2CCCC(C(=O)N(C)C)CC2)cnn1C | 0.9453 | Strong candidate | 0.7522 | 2.7955 | 336.39 | 0.537 |
| CC1=C(C)N=C(C2CCCN(C(=O)c3ccc(C(N)=O)cc3)N2)CC1 | 0.944 | Strong candidate | 0.8856 | 3.445 | 340.43 | 2.423 |
| NS(=O)(=O)c1ccc(NCC2CCCO2)cc1Cl | 0.9435 | Strong candidate | 0.8819 | 2.644 | 290.77 | 1.578 |
| O=C(Nc1ccc(C(=O)N2CCCC2)cc1)NC1CC(=O)N(C2CC2)C1 | 0.9408 | Strong candidate | 0.8632 | 2.5579 | 356.43 | 1.807 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'ring_closure_mismatch': 47, 'long_repetitive_fragment': 34, 'unbalanced_parentheses': 28, 'rdkit_parse_failure': 20}`
- Invalid reason percentages: `{'ring_closure_mismatch': 36.43, 'long_repetitive_fragment': 26.36, 'unbalanced_parentheses': 21.71, 'rdkit_parse_failure': 15.5}`
- Avg invalid length: `39.4031`
- Common invalid endings: `{')cc1': 19, ')CC1': 10, 'ccc1': 9, '2)c1': 8, 'cc21': 6, '(C)C': 5, 'C1=O': 5, 'c2c1': 5, 'c1OC': 4, 'nH]1': 4}`
- Top decoded tokens: `{'c': 4778, 'C': 3877, '(': 1795, ')': 1783, '1': 1394, '2': 963, 'O': 930, 'N': 820, '=': 729, 'n': 497}`
