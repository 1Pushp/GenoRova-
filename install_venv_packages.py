#!/usr/bin/env python3
"""Install packages in venv"""
import subprocess
import sys

packages = [
    'numpy',
    'scipy',
    'pandas',
    'matplotlib',
    'pillow',
    'tqdm',
    'torch',
    'rdkit',
]

print(f"Installing {len(packages)} packages to: {sys.prefix}")
print()

for pkg in packages:
    print(f"Installing {pkg}...", end=" ", flush=True)
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', pkg], 
                      timeout=300, check=True)
        print("✓")
    except Exception as e:
        print(f"✗ ({e})")

print()
print("Installation complete!")
