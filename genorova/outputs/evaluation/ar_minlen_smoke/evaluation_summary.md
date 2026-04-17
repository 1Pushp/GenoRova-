# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\ar\smilesvae_ar_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocab_ar.json`
- Strategy: `random`
- Temperature: `0.3`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- AR minimum generation length: `20`
- Requested samples: `100`
- Reference source for novelty: `dataset:moses`
- Checkpoint stage: `None`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 43 / 100 |
| Validity | 43.0% |
| Unique valid molecules | 43 / 43 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 43 / 43 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 43 / 43 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.8419 |
| Best clinical score (unique valid) | 0.9172 |
| Mean generated length | 27.21 |
| Mean valid length | 30.5349 |
| Mean filtered-candidate length | 30.4524 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 43 |
| Filtered computational candidates | 42 |
| Filter pass rate | 97.67% |
| Mean valid MW | 266.7247 |
| Mean valid QED | 0.843 |
| Rejection reasons | `{'lipinski_fail': 1, 'logp_out_of_range': 1}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CCc1csc(C(=O)Nc2ccc(C(=O)N(C)C)cc2)n1 | 0.9172 | 0.9442 | 2.0818 | 303.39 | 2.66 | True | passed_all_filters |
| Cc1cc(NCC(=O)N2CCc3ccc(Cl)cc3C2)no1 | 0.9001 | 0.9468 | 2.352 | 305.77 | 2.633 | True | passed_all_filters |
| COC(=O)c1ccc(C(=O)N2CCCC2c2ccccc2)nn1 | 0.8988 | 0.8129 | 2.5611 | 311.34 | 2.24 | True | passed_all_filters |
| O=C(Nc1ccncn1)N1CCCC(c2ccccc2)C1 | 0.8964 | 0.921 | 2.517 | 282.35 | 2.888 | True | passed_all_filters |
| CNC(=O)c1ccc(NC(=O)NC2CCCC2)cc1 | 0.8941 | 0.7796 | 1.6934 | 261.32 | 2.11 | True | passed_all_filters |
| CC(C#N)C(=O)Nc1ccc(C(F)(F)F)cc1 | 0.8888 | 0.8664 | 2.5008 | 242.2 | 2.804 | True | passed_all_filters |
| Cc1c(O)cccc1C(=O)N(C)Cc1ccccc1 | 0.8807 | 0.9156 | 1.7201 | 255.32 | 2.973 | True | passed_all_filters |
| O=CNc1ccc(NC(=O)c2ccccc2)cc1 | 0.8804 | 0.8066 | 1.5803 | 240.26 | 2.507 | True | passed_all_filters |
| CC1(CNC(=O)CCc2cccc(Cl)c2)CC1=O | 0.8769 | 0.8884 | 2.7003 | 265.74 | 2.368 | True | passed_all_filters |
| O=C1CCN(CCc2ccc(F)cc2Cl)N1 | 0.8752 | 0.8761 | 2.7424 | 242.68 | 1.758 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CCc1csc(C(=O)Nc2ccc(C(=O)N(C)C)cc2)n1 | 0.9172 | Strong candidate | 0.9442 | 2.0818 | 303.39 | 2.66 |
| Cc1cc(NCC(=O)N2CCc3ccc(Cl)cc3C2)no1 | 0.9001 | Strong candidate | 0.9468 | 2.352 | 305.77 | 2.633 |
| COC(=O)c1ccc(C(=O)N2CCCC2c2ccccc2)nn1 | 0.8988 | Strong candidate | 0.8129 | 2.5611 | 311.34 | 2.24 |
| O=C(Nc1ccncn1)N1CCCC(c2ccccc2)C1 | 0.8964 | Strong candidate | 0.921 | 2.517 | 282.35 | 2.888 |
| CNC(=O)c1ccc(NC(=O)NC2CCCC2)cc1 | 0.8941 | Strong candidate | 0.7796 | 1.6934 | 261.32 | 2.11 |
| CC(C#N)C(=O)Nc1ccc(C(F)(F)F)cc1 | 0.8888 | Strong candidate | 0.8664 | 2.5008 | 242.2 | 2.804 |
| Cc1c(O)cccc1C(=O)N(C)Cc1ccccc1 | 0.8807 | Strong candidate | 0.9156 | 1.7201 | 255.32 | 2.973 |
| O=CNc1ccc(NC(=O)c2ccccc2)cc1 | 0.8804 | Strong candidate | 0.8066 | 1.5803 | 240.26 | 2.507 |
| CC1(CNC(=O)CCc2cccc(Cl)c2)CC1=O | 0.8769 | Strong candidate | 0.8884 | 2.7003 | 265.74 | 2.368 |
| O=C1CCN(CCc2ccc(F)cc2Cl)N1 | 0.8752 | Strong candidate | 0.8761 | 2.7424 | 242.68 | 1.758 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 43, 'long_repetitive_fragment': 5, 'ring_closure_mismatch': 4, 'rdkit_parse_failure': 4, 'unbalanced_brackets': 1}`
- Invalid reason percentages: `{'unbalanced_parentheses': 75.44, 'long_repetitive_fragment': 8.77, 'ring_closure_mismatch': 7.02, 'rdkit_parse_failure': 7.02, 'unbalanced_brackets': 1.75}`
- Avg invalid length: `24.7018`
- Common invalid endings: `{')cc1': 7, '1CC1': 7, 'c1Cl': 7, 'ccc1': 7, 'CCC1': 3, 'cc21': 3, 'cc1C': 2, 'c2s1': 2, 'N)=O': 2, 'cc1F': 1}`
- Top decoded tokens: `{'c': 749, 'C': 519, '1': 300, ')': 259, '(': 210, '2': 133, 'O': 121, 'N': 94, '=': 78, 'n': 60}`
