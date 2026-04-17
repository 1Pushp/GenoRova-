# Candidate Filtering Summary

These are filtered computational candidates for research support only, not experimentally validated drug leads.

## Thresholds

- QED minimum: `0.5`
- SA maximum: `6.0`
- Molecular weight range: `150.0 - 500.0` Da
- LogP range: `-1.0 - 5.0`
- Require Lipinski pass: `True`

## Summary

- Unique valid generated molecules: `367`
- Filtered computational candidates: `349`
- Filter pass rate: `95.1%`
- Rejection reason counts: `{'lipinski_fail': 16, 'logp_out_of_range': 16, 'qed_below_threshold': 3}`

## Top Filtered Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski |
| --- | --- | --- | --- | --- | --- | --- |
| CN(C)S(=O)(=O)c1ccc(C(=O)N2CCC(C(N)=O)CC2)cc1 | 0.9591 | 0.8508 | 1.9181 | 339.42 | 0.274 | True |
| NC(=O)C1CCCN1C(=O)C1CCCC1C(=O)N1CCCC1 | 0.9553 | 0.8239 | 3.1574 | 307.39 | 0.501 | True |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCO3)cc1 | 0.9511 | 0.9364 | 1.7886 | 319.34 | 2.071 | True |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCCO3)cc1 | 0.9502 | 0.9302 | 1.8353 | 333.37 | 2.114 | True |
| CNC(=O)CN(C)C(=O)C1CCN(Cc2ccccc2)C(=O)C1 | 0.9462 | 0.8658 | 2.5606 | 317.39 | 0.63 | True |
| CNS(=O)(=O)c1cccc(NC(=O)N2CCCC2CO)c1 | 0.946 | 0.7571 | 2.5472 | 313.38 | 0.583 | True |
| COC(=O)c1c(C(=O)N2CCCC(C(=O)N(C)C)CC2)cnn1C | 0.9453 | 0.7522 | 2.7955 | 336.39 | 0.537 | True |
| CC1=C(C)N=C(C2CCCN(C(=O)c3ccc(C(N)=O)cc3)N2)CC1 | 0.944 | 0.8856 | 3.445 | 340.43 | 2.423 | True |
| NS(=O)(=O)c1ccc(NCC2CCCO2)cc1Cl | 0.9435 | 0.8819 | 2.644 | 290.77 | 1.578 | True |
| O=C(Nc1ccc(C(=O)N2CCCC2)cc1)NC1CC(=O)N(C2CC2)C1 | 0.9408 | 0.8632 | 2.5579 | 356.43 | 1.807 | True |
