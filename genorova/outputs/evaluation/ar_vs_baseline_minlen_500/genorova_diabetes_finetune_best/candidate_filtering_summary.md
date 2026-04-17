# Candidate Filtering Summary

These are filtered computational candidates for research support only, not experimentally validated drug leads.

## Thresholds

- QED minimum: `0.5`
- SA maximum: `6.0`
- Molecular weight range: `150.0 - 500.0` Da
- LogP range: `-1.0 - 5.0`
- Require Lipinski pass: `True`

## Summary

- Unique valid generated molecules: `50`
- Filtered computational candidates: `43`
- Filter pass rate: `86.0%`
- Rejection reason counts: `{'qed_below_threshold': 4, 'mw_out_of_range': 3, 'lipinski_fail': 1, 'logp_out_of_range': 1}`

## Top Filtered Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski |
| --- | --- | --- | --- | --- | --- | --- |
| NCCCC(N)C(=O)N1CCCCC1 | 0.9191 | 0.6725 | 2.4779 | 199.3 | 0.065 | True |
| COc1ccc(NS(=O)(=O)c2ccc(C)cc2)cc1 | 0.9183 | 0.9346 | 1.4569 | 277.34 | 2.804 | True |
| O=C(O)CC=CC1CCCCC1C1CS(=O)C1O | 0.9115 | 0.7609 | 4.8104 | 272.37 | 1.521 | True |
| Cc1cccc(C)c1N1C(=O)c2cccc(O)c2C1=O | 0.9006 | 0.8082 | 2.1281 | 267.28 | 2.81 | True |
| C=CNC1(C2CCO2)C(=O)NC(=O)NC(=O)C(C)C1C | 0.8988 | 0.6703 | 4.7161 | 281.31 | -0.115 | True |
| Cc1cccc(C)c1N1C(=O)c2ccc(N)cc2C1=O | 0.8942 | 0.6373 | 2.0615 | 266.3 | 2.686 | True |
| CC(C)OC(=O)C1CCCOCCNC1 | 0.8901 | 0.6968 | 3.2524 | 215.29 | 0.954 | True |
| COC1=NC(C)=C(N)C1c1ccc(Cl)cc1 | 0.8866 | 0.8151 | 3.1973 | 236.7 | 2.672 | True |
| Nc1ncnc2sc3c(c12)CC1CC(C3)N1 | 0.8849 | 0.7137 | 4.4714 | 232.31 | 1.103 | True |
| NCc1c(N)nc(-c2ccccc2)nc1-c1ccccc1 | 0.8829 | 0.7707 | 1.9713 | 276.34 | 2.852 | True |
