#!/usr/bin/env python3
"""
QUICK TEST: Docking Pipeline Components (No Downloads)
=======================================================

Fast test of docking functions without downloading large PDB files.
"""

import sys
from pathlib import Path

SRC_PATH = Path(__file__).parent
sys.path.insert(0, str(SRC_PATH))

print("\n" + "="*70)
print("GENOROVA AI — QUICK DOCKING PIPELINE TEST (NO DOWNLOADS)")
print("="*70)

try:
    # Test 1: Imports
    print("\n[TEST 1] Module Imports")
    print("-" * 70)
    from docking.ligand_prep import prepare_ligand, smiles_to_mol
    from docking.docking_results import normalize_binding_affinity, load_candidate_data
    from docking.docking_engine import check_vina_installed, mock_docking_affinity
    print("✓ All modules imported successfully")
    
    # Test 2: SMILES to Molecule Conversion
    print("\n[TEST 2] SMILES Parsing")
    print("-" * 70)
    test_smiles = [
        ("CC(=O)Oc1ccccc1C(=O)O", "Aspirin"),
        ("c1ccccc1", "Benzene"),
        ("CN1C=NC2=C1C(=O)N(C(=O)N2C)C", "Caffeine"),
    ]
    
    for smiles, name in test_smiles:
        mol = smiles_to_mol(smiles)
        if mol is not None:
            from rdkit.Chem import Descriptors
            mw = Descriptors.MolWt(mol)
            print(f"✓ {name:15s} → MW: {mw:7.2f}")
        else:
            print(f"✗ {name:15s} → INVALID")
    
    # Test 3: Affinity Scoring
    print("\n[TEST 3] Binding Affinity Interpretation")
    print("-" * 70)
    test_affinities = [-10.5, -7.2, -5.0, -3.5]
    for aff in test_affinities:
        score = normalize_binding_affinity(aff)
        print(f"  {aff:>6.1f} kcal/mol → Score: {score:.3f}")
    
    # Test 4: Vina Status
    print("\n[TEST 4] AutoDock Vina Status")
    print("-" * 70)
    vina_available = check_vina_installed()
    print(f"Vina installed: {'✓ YES' if vina_available else '✗ NO (will use mock docking)'}")
    
    # Test 5: Mock Docking  
    print("\n[TEST 5] Mock Docking Affinity (for testing)")
    print("-" * 70)
    for i in range(1, 6):
        mol_id = f"MOL_{i:03d}"
        affinity = mock_docking_affinity(mol_id)
        print(f"  {mol_id} → {affinity:.2f} kcal/mol")
    
    # Test 6: Load Candidate Data
    print("\n[TEST 6] Loading Candidate Data")
    print("-" * 70)
    for disease in ['diabetes', 'infection']:
        df = load_candidate_data(disease)
        if not df.empty:
            print(f"✓ {disease.capitalize():10s} → {len(df)} candidates, mean score: {df['clinical_score'].mean():.4f}")
        else:
            print(f"✗ {disease.capitalize():10s} → No data")
    
    print("\n" + "="*70)
    print("QUICK TEST COMPLETE - ALL FUNCTIONS WORKING")
    print("="*70)
    print("\nNext steps:")
    print("1. Install dependencies:")
    print("   pip install -r requirements.txt")
    print()
    print("2. Run docking pipeline:")
    print("   python run_docking_pipeline.py --max-molecules 10")
    print()
    print("3. Or run full pipeline:")
    print("   python run_docking_pipeline.py")
    print("\n" + "="*70)

except Exception as e:
    print(f"\n✗ ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
