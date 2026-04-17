# Generation Evaluation Summary

## Run Metadata

- Checkpoint: `genorova\outputs\models\diabetes_guarded_retrain\genorova_diabetes_guarded_retrain_pretrain_best.pt`
- Vocabulary: `C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova\outputs\vocabulary_diabetes_pretrain.json`
- Strategy: `guided`
- Temperature: `0.25`
- Top-k: `5`
- Repetition penalty: `0.75`
- Structural guard strength: `1.0`
- Requested samples: `1000`
- Reference source for novelty: `csv:genorova\data\raw\diabetes_molecules.csv`
- Checkpoint stage: `pretrain`
- Candidate filter thresholds: `{"logp_max": 5.0, "logp_min": -1.0, "mw_max": 500.0, "mw_min": 150.0, "qed_min": 0.5, "require_lipinski": true, "sa_max": 6.0}`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Valid RDKit SMILES | 30 / 1000 |
| Validity | 3.0% |
| Unique valid molecules | 30 / 30 |
| Uniqueness among valid | 100.0% |
| Novel valid molecules | 30 / 30 |
| Novelty among valid | 100.0% |
| Novel unique molecules | 30 / 30 |
| Novelty among unique valid | 100.0% |
| Average clinical score (unique valid) | 0.7835 |
| Best clinical score (unique valid) | 0.9353 |

## Filtering Summary

| Metric | Value |
| --- | ---: |
| Unique valid candidate pool | 30 |
| Filtered computational candidates | 20 |
| Filter pass rate | 66.67% |
| Rejection reasons | `{'lipinski_fail': 6, 'logp_out_of_range': 6, 'qed_below_threshold': 5}` |

## Top Filtered Computational Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski | filter_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COc1ccc(NS(=O)(=O)c2ccc(C)nc2)cc1 | 0.9353 | 0.9306 | 1.7483 | 278.33 | 2.199 | True | passed_all_filters |
| CCOC(=O)NC(=O)N1CCC(C)CC(COC)C1CC | 0.9263 | 0.8663 | 3.7358 | 300.4 | 2.626 | True | passed_all_filters |
| CC1=CN=C(NS(=O)(=O)c2ccc(F)cc2)C1 | 0.9099 | 0.8746 | 2.6939 | 254.29 | 1.81 | True | passed_all_filters |
| CCCNN(C)C(=O)NC(=O)NOCC(C)C | 0.8874 | 0.6064 | 3.1783 | 246.31 | 0.84 | True | passed_all_filters |
| COc1ccccc1CCC1COCN2CC(COC(=O)CO)C=C12 | 0.8733 | 0.7556 | 3.937 | 347.41 | 1.583 | True | passed_all_filters |
| COC(=O)C1=CC=CC=C2CC2=CCC(C)OCC=N1 | 0.8691 | 0.6901 | 4.6864 | 273.33 | 2.736 | True | passed_all_filters |
| C=C1CNC(=O)N(CCC(C)CC)C(CN)C1 | 0.868 | 0.7177 | 3.996 | 239.36 | 1.721 | True | passed_all_filters |
| C=C(CNC(=O)c1ccc(C)cc1C)OC | 0.8629 | 0.7882 | 2.2268 | 219.28 | 2.193 | True | passed_all_filters |
| CCC1=CC=CC(OC)CCCc2c(F)cccc2C(=O)NCCN1 | 0.8534 | 0.8634 | 3.9694 | 346.45 | 3.347 | True | passed_all_filters |
| CN(Sc1ccccc1)C(=O)NC1C#CCC1 | 0.8444 | 0.6562 | 4.2316 | 246.33 | 2.501 | True | passed_all_filters |
| CC1=CC=C2C=CCC2C(=O)N(C)CC(=O)C1C | 0.8442 | 0.6552 | 4.7258 | 245.32 | 2.112 | True | passed_all_filters |
| C=C(NCCC)N1CCCCCCCCCCCCOCC1 | 0.8316 | 0.815 | 2.7618 | 310.53 | 4.69 | True | passed_all_filters |
| CC1=CC2=CC3=CC=C4C=C4NC(=C12)C3 | 0.8223 | 0.6234 | 4.8947 | 193.25 | 2.884 | True | passed_all_filters |
| CCCCSC1NC(=O)N(C)CCC(C)C1CC | 0.8062 | 0.7762 | 4.0497 | 272.46 | 3.553 | True | passed_all_filters |
| CCCC=C(C)C(=O)NC1=NC=CC(C)C1C | 0.8024 | 0.7492 | 4.2486 | 234.34 | 3.047 | True | passed_all_filters |
| CCCCCN(C)C(=O)N1CCC2CC2C1CC | 0.7939 | 0.6883 | 3.5154 | 252.4 | 3.349 | True | passed_all_filters |
| C=C1CC2CNC(CC)C(C)C2C(C)C2CSC(C)CC12 | 0.7796 | 0.7111 | 5.3786 | 307.55 | 4.591 | True | passed_all_filters |
| Cc1ccc(S(=O)(=O)Nc2ccccc2)cc1 | 0.7794 | 0.9061 | 1.3737 | 247.32 | 2.796 | True | passed_all_filters |
| C#CCCCNC1=CCC(C)Cc2ccccc21 | 0.7675 | 0.6249 | 3.274 | 239.36 | 3.613 | True | passed_all_filters |
| CCCNCC1C(C)=C(C2CCCCC2)CC1C | 0.758 | 0.557 | 3.5297 | 249.44 | 4.539 | True | passed_all_filters |

## Top Scored Valid Molecules

| canonical_smiles | clinical_score | scorer_recommendation | qed_score | sa_score | molecular_weight | logp |
| --- | --- | --- | --- | --- | --- | --- |
| COc1ccc(NS(=O)(=O)c2ccc(C)nc2)cc1 | 0.9353 | Strong candidate | 0.9306 | 1.7483 | 278.33 | 2.199 |
| CCOC(=O)NC(=O)N1CCC(C)CC(COC)C1CC | 0.9263 | Strong candidate | 0.8663 | 3.7358 | 300.4 | 2.626 |
| CC1=CN=C(NS(=O)(=O)c2ccc(F)cc2)C1 | 0.9099 | Strong candidate | 0.8746 | 2.6939 | 254.29 | 1.81 |
| CCCNN(C)C(=O)NC(=O)NOCC(C)C | 0.8874 | Strong candidate | 0.6064 | 3.1783 | 246.31 | 0.84 |
| COc1ccccc1CCC1COCN2CC(COC(=O)CO)C=C12 | 0.8733 | Strong candidate | 0.7556 | 3.937 | 347.41 | 1.583 |
| COC(=O)C1=CC=CC=C2CC2=CCC(C)OCC=N1 | 0.8691 | Strong candidate | 0.6901 | 4.6864 | 273.33 | 2.736 |
| C=C1CNC(=O)N(CCC(C)CC)C(CN)C1 | 0.868 | Strong candidate | 0.7177 | 3.996 | 239.36 | 1.721 |
| C=C(CNC(=O)c1ccc(C)cc1C)OC | 0.8629 | Strong candidate | 0.7882 | 2.2268 | 219.28 | 2.193 |
| CCC1=CC=CC(OC)CCCc2c(F)cccc2C(=O)NCCN1 | 0.8534 | Strong candidate | 0.8634 | 3.9694 | 346.45 | 3.347 |
| CN(Sc1ccccc1)C(=O)NC1C#CCC1 | 0.8444 | Strong candidate | 0.6562 | 4.2316 | 246.33 | 2.501 |
| CC1=CC=C2C=CCC2C(=O)N(C)CC(=O)C1C | 0.8442 | Strong candidate | 0.6552 | 4.7258 | 245.32 | 2.112 |
| C=C(NCCC)N1CCCCCCCCCCCCOCC1 | 0.8316 | Strong candidate | 0.815 | 2.7618 | 310.53 | 4.69 |
| CC1=C(C(CO)C(C)C(C=O)CC2C(C)C(=O)C(=O)C2C)CC1 | 0.8297 | Strong candidate | 0.4445 | 4.9806 | 320.43 | 2.587 |
| COCOCCNCC1=CC2C(=O)CCC(=O)NCCCC(CO)CC2C1 | 0.8286 | Strong candidate | 0.3294 | 4.5068 | 382.5 | 1.017 |
| CC1=CC2=CC3=CC=C4C=C4NC(=C12)C3 | 0.8223 | Strong candidate | 0.6234 | 4.8947 | 193.25 | 2.884 |
| CCCCSC1NC(=O)N(C)CCC(C)C1CC | 0.8062 | Strong candidate | 0.7762 | 4.0497 | 272.46 | 3.553 |
| CCCC=C(C)C(=O)NC1=NC=CC(C)C1C | 0.8024 | Strong candidate | 0.7492 | 4.2486 | 234.34 | 3.047 |
| CCCCCN(C)C(=O)N1CCC2CC2C1CC | 0.7939 | Strong candidate | 0.6883 | 3.5154 | 252.4 | 3.349 |
| C=CCNC(NC(=O)NCc1ccccc1)C(CO)C1CCOCC1 | 0.7891 | Strong candidate | 0.4041 | 3.538 | 347.46 | 1.623 |
| C=C1CC2CNC(CC)C(C)C2C(C)C2CSC(C)CC12 | 0.7796 | Strong candidate | 0.7111 | 5.3786 | 307.55 | 4.591 |

## Caveats

- These are computationally generated candidates, not experimentally validated molecules.
- Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.
- Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.

## Debug Snapshot

- Empty decoded strings: `0`
- Top invalid reasons: `{'long_repetitive_fragment': 359, 'rdkit_parse_failure': 310, 'unbalanced_parentheses': 162, 'ring_closure_mismatch': 90, 'unbalanced_brackets': 49}`
- Invalid reason percentages: `{'long_repetitive_fragment': 37.01, 'rdkit_parse_failure': 31.96, 'unbalanced_parentheses': 16.7, 'ring_closure_mismatch': 9.28, 'unbalanced_brackets': 5.05}`
- Avg invalid length: `75.1175`
- Common invalid endings: `{'11C2': 19, 'ccc1': 14, '1CC2': 13, 'C121': 9, '1Cl2': 9, 'CCC1': 9, ')cc1': 7, 'C1C1': 7, 'COC1': 7, 'cnc1': 6}`
- Top decoded tokens: `{'c': 12623, 'C': 11247, '1': 6044, '(': 4643, ')': 4375, 'O': 4053, '2': 3231, 'n': 3083, '=': 2781, 'N': 2734}`
