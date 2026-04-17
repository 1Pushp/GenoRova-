# Candidate Filtering Summary

These are filtered computational candidates for research support only, not experimentally validated drug leads.

## Thresholds

- QED minimum: `0.5`
- SA maximum: `6.0`
- Molecular weight range: `150.0 - 500.0` Da
- LogP range: `-1.0 - 5.0`
- Require Lipinski pass: `True`

## Summary

- Unique valid generated molecules: `24`
- Filtered computational candidates: `20`
- Filter pass rate: `83.33%`
- Rejection reason counts: `{'mw_out_of_range': 2, 'qed_below_threshold': 2, 'lipinski_fail': 1, 'logp_out_of_range': 1}`

## Top Filtered Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski |
| --- | --- | --- | --- | --- | --- | --- |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | 0.6725 | 2.4779 | 199.3 | 0.065 | True |
| COc1ccc(NS(=O)(=O)c2ccc(F)cc2)cc1 | 0.9187 | 0.9369 | 1.4821 | 281.31 | 2.635 | True |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True |
| NC(CO)C(=O)C1CCCC1 | 0.9102 | 0.6088 | 2.7666 | 157.21 | 0.065 | True |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | 0.6968 | 3.2524 | 215.29 | 0.954 | True |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | 0.8151 | 3.1973 | 236.7 | 2.672 | True |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True |
| CCC(C)C(N)C(=O)N1CCCCC1 | 0.8567 | 0.7442 | 2.6619 | 198.31 | 1.372 | True |
| CCCCC(N)C(=O)N1CCCCC1 | 0.8567 | 0.7441 | 2.3049 | 198.31 | 1.516 | True |
| CC1=CC=C(C(=O)C2C(C)CC3OCC32)C1C | 0.8549 | 0.7315 | 4.8299 | 232.32 | 2.749 | True |
