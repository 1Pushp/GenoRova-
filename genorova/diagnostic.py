#!/usr/bin/env python3
"""
Genorova AI - Complete Environment Diagnostic
Identifies environment issues and guides fixes
"""

import sys
import os
import subprocess

print("="*70)
print("GENOROVA AI - COMPLETE DIAGNOSTIC REPORT")
print("="*70)
print()

# 1. Python interpreter
print("[1] PYTHON INTERPRETER")
print(f"    ✓ Path: {sys.executable}")
print(f"    ✓ Version: {sys.version}")
print()

# 2. Virtual environment
print("[2] VIRTUAL ENVIRONMENT STATUS")
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    print(f"    ✓ VENV Active: {sys.prefix}")
    print(f"    ✓ Type: venv (detected)")
else:
    print(f"    ! System Python (not in venv)")
    print(f"    ✓ Prefix: {sys.prefix}")
print()

# 3. Site packages
print("[3] SITE-PACKAGES LOCATION")
import site
sp = site.getsitepackages()[0]
print(f"    ✓ {sp}")
print()

# 4. Import tests
print("[4] CRITICAL IMPORTS TEST")
imports_to_test = {
    'rdkit': 'rdkit',
    'rdkit.Chem': 'rdkit.Chem',
    'numpy': 'numpy',
    'PIL': 'PIL',
    'tqdm': 'tqdm',
    'pandas': 'pandas',
    'torch': 'torch',
    'scipy': 'scipy',
    'matplotlib': 'matplotlib',
    'RDKit.Chem': 'rdkit.Chem',
}

failed_imports = []
for name, module_path in imports_to_test.items():
    try:
        mod = __import__(module_path)
        version = getattr(mod, '__version__', 'installed')
        print(f"    ✓ {name:20s} {version}")
    except ImportError as e:
        print(f"    ✗ {name:20s} NOT FOUND")
        failed_imports.append(name)
    except Exception as e:
        print(f"    ✗ {name:20s} ERROR: {str(e)[:40]}")
        failed_imports.append(name)

print()

# 5. Pip list
print("[5] INSTALLED PACKAGES (pip list)")
try:
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                          capture_output=True, text=True, timeout=10)
    packages = result.stdout.split('\n')
    critical_packages = ['rdkit', 'numpy', 'pillow', 'torch', 'scipy', 'pandas', 'matplotlib', 'tqdm']
    
    for line in packages:
        if any(pkg in line.lower() for pkg in critical_packages):
            print(f"    {line}")
except Exception as e:
    print(f"    Error: {e}")

print()

# 6. VS Code Configuration check
print("[6] VS CODE CONFIGURATION")
vscode_settings = os.path.expanduser('~/.vscode/settings.json')
if os.path.exists(vscode_settings):
    print(f"    ✓ Found: {vscode_settings}")
    try:
        import json
        with open(vscode_settings, 'r') as f:
            settings = json.load(f)
            python_path = settings.get('python.defaultInterpreterPath', 'Not set')
            print(f"    ✓ Python path setting: {python_path}")
    except:
        print("    ! Could not read settings")
else:
    print(f"    ! VS Code settings not found at: {vscode_settings}")

print()

# 7. AutoDock Vina check
print("[7] AUTODOCK VINA CHECK")
try:
    result = subprocess.run(['vina', '--help'], capture_output=True, timeout=5, text=True)
    if result.returncode == 0:
        print(f"    ✓ AutoDock Vina: INSTALLED")
    else:
        print(f"    ! AutoDock Vina: Not in PATH")
except FileNotFoundError:
    print(f"    ! AutoDock Vina: NOT FOUND - will use mock docking")
except Exception as e:
    print(f"    ! AutoDock Vina: Error: {e}")

print()
print("="*70)

if failed_imports:
    print(f"\nFAILED IMPORTS: {', '.join(failed_imports)}")
    print("\nRun: python fix_environment.py")
else:
    print("\n✅ ALL IMPORTS WORKING - Environment is OK!")
    print("\nTo use in VS Code:")
    print(f"  1. Open Command Palette (Ctrl+Shift+P)")
    print(f"  2. Search: 'Python: Select Interpreter'")
    print(f"  3. Choose: {sys.executable}")
