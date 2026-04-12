#!/usr/bin/env python3
"""
Quick test to verify data availability and pipeline readiness
"""

import pandas as pd
from pathlib import Path
import sys

print('[DATA CHECK] Verifying existing candidate files')
print('='*70)

data_ready = True

for disease in ['diabetes', 'infection']:
    candidate_file = Path(f'../outputs/generated/{disease}_candidates_validated.csv')
    
    if candidate_file.exists():
        df = pd.read_csv(candidate_file)
        print(f'✓ {disease.upper()}: {candidate_file.name}')
        print(f'  Rows: {len(df)}')
        cols = list(df.columns)
        print(f'  Columns: {cols}')
        if 'smiles' in df.columns:
            first_smiles = df['smiles'].iloc[0][:40]
            print(f'  First SMILES: {first_smiles}...')
        if 'clinical_score' in df.columns:
            mean_score = df['clinical_score'].mean()
            print(f'  Mean clinical score: {mean_score:.4f}')
    else:
        print(f'✗ {disease.upper()}: MISSING {candidate_file.name}')
        data_ready = False
    print()

print('='*70)
if data_ready:
    print('✓ DATA READY: Candidate files verified!')
    print()
    print('Ready to run docking pipeline:')
    print('  python run_docking_pipeline.py --target diabetes')
    print('  python run_docking_pipeline.py --target infection')
else:
    print('✗ UPDATE NEEDED: Some candidate files missing')
    sys.exit(1)
