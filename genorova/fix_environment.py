#!/usr/bin/env python3
"""
Genorova AI - Environment Fix Script
Ensures all dependencies are installed and properly configured
Run this if you get any import errors
"""

import subprocess
import sys
import platform

print("="*70)
print("GENOROVA AI - ENVIRONMENT FIX SCRIPT")
print("="*70)
print()

# Step 1: Upgrade pip
print("[1] Upgrading pip...")
subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'], check=False)
print()

# Step 2: Core dependencies
print("[2] Installing core dependencies...")
core_deps = [
    'numpy>=2.0',
    'scipy>=1.10',
    'pandas>=2.0',
    'matplotlib>=3.7',
    'tqdm>=4.60',
    'Pillow>=10.0',
    'torch>=2.0',
    'torchvision>=0.15',
]

for dep in core_deps:
    print(f"    Installing {dep}...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', dep], 
                   capture_output=True, check=False)

print()

# Step 3: RDKit (special handling)
print("[3] Installing RDKit...")
print("    Attempting pip install...")
result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'rdkit'],
                       capture_output=True, text=True)
if result.returncode == 0:
    print("    ✓ RDKit installed via pip")
else:
    print("    Note: RDKit not available via pip, checking alternatives...")
    print(f"    OS: {platform.system()}")
    if platform.system() == 'Windows':
        print("    Tip: Use conda for better RDKit support on Windows")
        print("    Command: conda install -c conda-forge rdkit")

print()

# Step 4: Docking dependencies
print("[4] Installing docking dependencies...")
docking_deps = [
    'vina',
    'meeko',
    'pdbfixer',
    'biopython',
    'requests',
]

for dep in docking_deps:
    print(f"    Installing {dep}...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', dep],
                   capture_output=True, check=False)

print()

# Step 5: Verify installations
print("[5] Verifying installations...")
test_imports = {
    'numpy': 'numpy',
    'scipy': 'scipy',
    'pandas': 'pandas',
    'matplotlib': 'matplotlib',
    'tqdm': 'tqdm',
    'PIL': 'PIL',
    'torch': 'torch',
    'rdkit': 'rdkit',
    'biopython': 'Bio',
}

failed = []
for name, module in test_imports.items():
    try:
        __import__(module)
        print(f"    ✓ {name}")
    except:
        print(f"    ✗ {name} - FAILED")
        failed.append(name)

print()
if failed:
    print(f"⚠️  Failed to install: {', '.join(failed)}")
    print("\nIf you're on Windows and RDKit failed:")
    print("  1. Install Conda from: https://www.anaconda.com/")
    print("  2. Run: conda install -c conda-forge rdkit")
else:
    print("✅ All dependencies installed successfully!")
    print()
    print("Next steps:")
    print("  1. Open VS Code")
    print("  2. Ctrl+Shift+P > Python: Select Interpreter")
    print(f"  3. Choose: {sys.executable}")
    print("  4. Reload VS Code window (Ctrl+Shift+P > Developer: Reload Window)")
    print()
    print("Then run: python test_environment.py")

print("="*70)
