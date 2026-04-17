# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes\genorova_diabetes_finetune_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.3`
- Requested samples: `1000`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `finetune`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 63 / 1000 |
| Validity | 6.3% |
| Unique valid molecules | 50 / 63 |
| Uniqueness among valid | 79.37% |
| Novel valid molecules | 44 / 63 |
| Novelty among valid | 69.84% |
| Novel unique molecules | 37 / 50 |
| Novelty among unique valid | 74.0% |
| Average clinical score (unique valid) | 0.8411 |
| Best clinical score (unique valid) | 0.9333 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 50 |
| Filtered computational candidates | 41 |
| Filter pass rate | 82.0% |
| Rejection reasons | `{'mw_out_of_range': 6, 'qed_below_threshold': 4, 'logp_out_of_range': 2, 'lipinski_fail': 1}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CCC(C)C(N)C(=O)N1CSCC1C#N | 0.9333 | 0.7734 | 3.8631 | 227.33 | 0.785 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCCC1C#N | 0.9299 | 0.7495 | 3.3801 | 209.29 | 0.874 | True | passed_all_filters |
| NC(=O)c1cc2c(-c3ccc(F)cc3)cnc-2ns1 | 0.9142 | 0.7797 | 2.5072 | 273.29 | 2.548 | True | passed_all_filters |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | 0.8082 | 2.1281 | 267.28 | 2.81 | True | passed_all_filters |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | 0.5366 | 1.6474 | 179.17 | 0.711 | True | passed_all_filters |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | 0.6373 | 2.0615 | 266.3 | 2.686 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | 0.6711 | 3.1753 | 200.28 | -0.047 | True | passed_all_filters |
| CCC1(CO)C(=O)NC(=O)N(C)C1=O | 0.884 | 0.5644 | 3.3517 | 200.19 | -0.917 | True | passed_all_filters |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True | passed_all_filters |
| CC(=O)Oc1ccccc1C(=O)O | 0.882 | 0.5501 | 1.58 | 180.16 | 1.31 | True | passed_all_filters |
| NCCC(N)C(=O)N1CCCCC1 | 0.8785 | 0.6324 | 2.5359 | 185.27 | -0.325 | True | passed_all_filters |
| CC(=O)NC(=O)NCCc1ccccc1 | 0.8763 | 0.7769 | 1.6266 | 206.25 | 1.075 | True | passed_all_filters |
| O=C1NC2=CC=CSC2=Nc2ccccc21 | 0.8763 | 0.7412 | 3.2588 | 228.28 | 2.604 | True | passed_all_filters |
| CC(C(=O)N1CSCC1C#N)C1CCCC1 | 0.8762 | 0.7408 | 3.6794 | 238.36 | 2.238 | True | passed_all_filters |
| CNCNc1ncnc2sc3c(c12)CCCC3 | 0.8669 | 0.8173 | 2.6872 | 248.35 | 2.159 | True | passed_all_filters |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1C | 0.8643 | 0.9413 | 1.6185 | 291.37 | 3.113 | True | passed_all_filters |
| NC(C(=O)N1CCCC1)c1ccccc1 | 0.863 | 0.7891 | 2.1891 | 204.27 | 1.309 | True | passed_all_filters |
| CNC(=O)Cc1cccc2ccccc12 | 0.8629 | 0.7883 | 1.5982 | 199.25 | 2.128 | True | passed_all_filters |
| CCC(C)C(N)C(=O)N1CCCCC1C | 0.8609 | 0.7746 | 3.047 | 212.34 | 1.761 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| CCC(C)C(N)C(=O)N1CSCC1C#N | 0.9333 | Strong candidate | 0.7734 | 3.8631 | 227.33 | 0.785 |
| CCC(C)C(N)C(=O)N1CCCC1C#N | 0.9299 | Strong candidate | 0.7495 | 3.3801 | 209.29 | 0.874 |
| NC(=O)c1cc2c(-c3ccc(F)cc3)cnc-2ns1 | 0.9142 | Strong candidate | 0.7797 | 2.5072 | 273.29 | 2.548 |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | Strong candidate | 0.7609 | 4.8104 | 272.37 | 1.521 |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | Strong candidate | 0.8082 | 2.1281 | 267.28 | 2.81 |
| CC(=O)Oc1ccccc1C(N)=O | 0.9001 | Strong candidate | 0.5366 | 1.6474 | 179.17 | 0.711 |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | Strong candidate | 0.6373 | 2.0615 | 266.3 | 2.686 |
| CCC(C)C(N)C(=O)N1CCC(O)C1 | 0.884 | Strong candidate | 0.6711 | 3.1753 | 200.28 | -0.047 |
| CCC1(CO)C(=O)NC(=O)N(C)C1=O | 0.884 | Strong candidate | 0.5644 | 3.3517 | 200.19 | -0.917 |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | Strong candidate | 0.7707 | 1.9713 | 276.34 | 2.852 |
| CC(=O)Oc1ccccc1C(=O)O | 0.882 | Strong candidate | 0.5501 | 1.58 | 180.16 | 1.31 |
| NCCC(N)C(=O)N1CCCCC1 | 0.8785 | Strong candidate | 0.6324 | 2.5359 | 185.27 | -0.325 |
| CC(=O)NC(=O)NCCc1ccccc1 | 0.8763 | Strong candidate | 0.7769 | 1.6266 | 206.25 | 1.075 |
| O=C1NC2=CC=CSC2=Nc2ccccc21 | 0.8763 | Strong candidate | 0.7412 | 3.2588 | 228.28 | 2.604 |
| CC(C(=O)N1CSCC1C#N)C1CCCC1 | 0.8762 | Strong candidate | 0.7408 | 3.6794 | 238.36 | 2.238 |
| CNCNc1ncnc2sc3c(c12)CCCC3 | 0.8669 | Strong candidate | 0.8173 | 2.6872 | 248.35 | 2.159 |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1C | 0.8643 | Strong candidate | 0.9413 | 1.6185 | 291.37 | 3.113 |
| NC(C(=O)N1CCCC1)c1ccccc1 | 0.863 | Strong candidate | 0.7891 | 2.1891 | 204.27 | 1.309 |
| CNC(=O)Cc1cccc2ccccc12 | 0.8629 | Strong candidate | 0.7883 | 1.5982 | 199.25 | 2.128 |
| CCC(C)C(N)C(=O)N1CCCCC1C | 0.8609 | Strong candidate | 0.7746 | 3.047 | 212.34 | 1.761 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'unbalanced_parentheses': 649, 'ring_closure_mismatch': 162, 'unbalanced_brackets': 73, 'rdkit_parse_failure': 35, 'long_repetitive_fragment': 18}`
- Top decoded tokens: `{'c': 9356, 'C': 8513, ')': 4082, '(': 3898, '1': 2581, 'O': 2386, '=': 1549, '<unk>': 1469, '2': 1386, 'N': 1322}`
