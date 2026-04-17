# Candidate Filtering Summary

These are filtered computational candidates for research support only, not experimentally validated drug leads.

## Thresholds

- QED minimum: `0.5`
- SA maximum: `6.0`
- Molecular weight range: `150.0 - 500.0` Da
- LogP range: `-1.0 - 5.0`
- Require Lipinski pass: `True`

## Summary

- Unique valid generated molecules: `143`
- Filtered computational candidates: `135`
- Filter pass rate: `94.41%`
- Rejection reason counts: `{'lipinski_fail': 8, 'logp_out_of_range': 8, 'qed_below_threshold': 1}`

## Top Filtered Candidates

| canonical_smiles | clinical_score | qed_score | sa_score | molecular_weight | logp | passes_lipinski |
| --- | --- | --- | --- | --- | --- | --- |
| COC(=O)C1CCN(C(=O)c2ccc(C(N)=O)cc2)CC1 | 0.9568 | 0.8341 | 1.7779 | 290.32 | 0.811 | True |
| CS(=O)(=O)c1ccc(NC(=O)c2ccc3c(c2)OCO3)cc1 | 0.9511 | 0.9364 | 1.7886 | 319.34 | 2.071 | True |
| O=C(c1ccc2c(c1)OCCO2)N1CCCC(CO)C1=O | 0.9393 | 0.8168 | 2.7861 | 291.3 | 0.829 | True |
| N#CC(NC(=O)C1CCCCC1)N1CCOCC1 | 0.9381 | 0.8078 | 3.089 | 251.33 | 0.865 | True |
| Nc1nn(Cc2ccc3c(c2)CCCC3)c(=O)[nH]c1=O | 0.9361 | 0.8292 | 2.4746 | 272.31 | 0.441 | True |
| CC1(C)C(=O)CC1C(=O)N1CCCC1C(=O)Nc1ccc(F)cc1 | 0.9344 | 0.924 | 3.0301 | 332.37 | 2.37 | True |
| NC(=O)C1CCCN(C(=O)Cn2c(=O)[nH]c3cc(Cl)ccc3c2=O)C1 | 0.9321 | 0.8004 | 2.7167 | 364.79 | 0.067 | True |
| CC(=O)N(C)C(=O)N1CCC(C(=O)Nc2ccc(F)c(F)c2)CC1 | 0.9307 | 0.8981 | 2.2576 | 339.34 | 2.214 | True |
| NC(=O)C1(NC(=O)C2CCCN(c3ccccc3)CC2)CCCC1 | 0.9295 | 0.8891 | 2.6151 | 329.44 | 2.207 | True |
| N#CC(NC(=O)C1CCN(C(=O)c2ccc(Cl)cc2)CC1)N1CCCC1 | 0.9277 | 0.8765 | 2.864 | 374.87 | 2.254 | True |
