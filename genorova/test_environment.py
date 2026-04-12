#!/usr/bin/env python3
"""
Genorova AI - Environment Test & Validation Script
Verify all imports work correctly before running the pipeline
Run this after fixing environment issues
"""

import sys
import subprocess
from pathlib import Path

print("="*70)
print("GENOROVA AI - ENVIRONMENT VALIDATION TEST")
print("="*70)
print()

# Test 1: Python version
print("[TEST 1] Python Version")
print(f"    Python: {sys.version}")
if sys.version_info >= (3, 9):
    print("    ✓ PASS: Python 3.9+ required")
else:
    print("    ✗ FAIL: Python 3.9+ required")
print()

# Test 2: Core imports
print("[TEST 2] Core Imports")
core_imports = {
    'numpy': 'Scientific computing',
    'scipy': 'Scientific algorithms',
    'pandas': 'Data manipulation',
    'matplotlib': 'Visualization',
}

core_pass = True
for module, desc in core_imports.items():
    try:
        ver = __import__(module).__version__
        print(f"    ✓ {module:15s} {ver:20s} {desc}")
    except Exception as e:
        print(f"    ✗ {module:15s} FAILED: {str(e)[:30]}")
        core_pass = False
print()

# Test 3: Chemistry imports
print("[TEST 3] Chemistry & ML Imports")
chem_imports = {
    'rdkit': 'RDKit (chemistry)',
    'rdkit.Chem': 'RDKit.Chem (molecular)',
    'torch': 'PyTorch (deep learning)',
}

chem_pass = True
for module, desc in chem_imports.items():
    try:
        ver = __import__(module).__version__ if '.' not in module else __import__(module.split('.')[0]).__version__
        print(f"    ✓ {module:15s} {ver:20s} {desc}")
    except Exception as e:
        print(f"    ✗ {module:15s} FAILED: {str(e)[:30]}")
        chem_pass = False
print()

# Test 4: Genorova specific imports
print("[TEST 4] Genorova Pipeline Imports")
genorova_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(genorova_path))

genorova_imports = {
    'data_loader': 'Data loading module',
    'preprocessor': 'Preprocessing module',
    'model': 'Model architecture',
    'scorer': 'Scoring module',
}

genorova_pass = True
for module, desc in genorova_imports.items():
    try:
        __import__(module)
        print(f"    ✓ {module:15s} {desc}")
    except Exception as e:
        print(f"    ✗ {module:15s} FAILED: {str(e)[:30]}")
        genorova_pass = False
print()

# Test 5: Docking imports
print("[TEST 5] Docking Module Imports")
docking_path = Path(__file__).parent / 'src' / 'docking'
sys.path.insert(0, str(docking_path))

docking_imports = {
    'protein_prep': 'Protein preparation',
    'ligand_prep': 'Ligand preparation',
    'docking_engine': 'Docking engine',
    'docking_results': 'Results processing',
    'batch_processor': 'Batch processing',
}

docking_pass = True
for module, desc in docking_imports.items():
    try:
        __import__(module)
        print(f"    ✓ {module:20s} {desc}")
    except Exception as e:
        print(f"    ✗ {module:20s} FAILED: {str(e)[:30]}")
        docking_pass = False
print()

# Test 6: Optional imports
print("[TEST 6] Optional Dependencies")
optional_imports = {
    'Bio': 'BioPython (protein analysis)',
    'PIL': 'Pillow (image processing)',
    'tqdm': 'tqdm (progress bars)',
}

for module, desc in optional_imports.items():
    try:
        ver = __import__(module).__version__ if hasattr(__import__(module), '__version__') else 'installed'
        print(f"    ✓ {module:15s} {ver:20s} {desc}")
    except Exception as e:
        print(f"    ! {module:15s} Not found: {desc}")
print()

# Test 7: AutoDock Vina
print("[TEST 7] AutoDock Vina (Optional)")
try:
    result = subprocess.run(['vina', '--help'], capture_output=True, timeout=5)
    if result.returncode == 0:
        print(f"    ✓ AutoDock Vina: INSTALLED (will use for real docking)")
    else:
        print(f"    ! AutoDock Vina: Found but with errors")
except FileNotFoundError:
    print(f"    ! AutoDock Vina: NOT INSTALLED")
    print(f"      Note: Pipeline will use mock docking instead")
print()

# Summary
print("="*70)
print("TEST RESULTS SUMMARY")
print("="*70)

all_pass = core_pass and chem_pass and genorova_pass and docking_pass

if all_pass:
    print("✅ ALL TESTS PASSED!")
    print()
    print("Environment is ready for:")
    print("  • Running molecular docking pipeline")
    print("  • Training generative models")
    print("  • Processing drug candidates")
    print()
    print("Quick start:")
    print("  cd genorova/src")
    print("  python run_docking_pipeline.py --max-molecules 10")
else:
    print("⚠️  Some tests failed. Running fix_environment.py...")
    print()
    print("Command:")
    print("  python fix_environment.py")

print()
