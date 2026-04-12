#!/usr/bin/env python3
"""
Genorova AI - AutoDock Vina Installation Guide
Provides step-by-step instructions for Windows installation
"""

import sys
import os
import subprocess
import platform
from pathlib import Path

print("="*70)
print("GENOROVA AI - AUTODOCK VINA SETUP FOR WINDOWS")
print("="*70)
print()

# Check current OS
print(f"[1] System Information")
print(f"    OS: {platform.system()} {platform.release()}")
print(f"    Architecture: {platform.machine()}")
print(f"    Python: {sys.executable}")
print()

# Check if Vina already installed
print(f"[2] AutoDock Vina Status Check")
try:
    result = subprocess.run(['vina', '--help'], capture_output=True, timeout=5, text=True)
    print(f"    ✓ AutoDock Vina is INSTALLED")
    print(f"    ✓ Version: {result.stdout.split(chr(10))[0]}")
    print()
    print("No action needed - Vina is ready!")
except FileNotFoundError:
    print(f"    ! AutoDock Vina NOT found in PATH")
    print(f"    ! Pipeline will use mock docking (still works for ranking)")
    print()
    
    print("[3] MANUAL INSTALLATION OPTIONS")
    print()
    
    print("Option A: Via pip (Linux/macOS - Limited Windows support)")
    print("  pip install vina")
    print()
    
    print("Option B: Via Conda (RECOMMENDED for Windows)")
    print("  1. Install Conda from: https://www.anaconda.com/download")
    print("  2. Open Anaconda Prompt and run:")
    print("     conda install -c conda-forge autodock-vina")
    print()
    
    print("Option C: Manual Download (BEST for Windows)")
    print("  1. Download from: https://autodock.scripps.edu/download/autodock_suite/")
    print("  2. Run the Windows installer")
    print("  3. Add to PATH or use fully qualified path")
    print()
    
    print("Option D: Pre-compiled Binary (FASTEST)")
    print("  1. Download: https://autodock.scripps.edu/")
    print("  2. Extract to: C:\\Program Files\\AutodockVina\\")
    print("  3. Add to PATH environment variable")
    print("     • Windows Settings > Edit environment variables")
    print("     • Add: C:\\Program Files\\AutodockVina\\bin")
    print()

print("="*70)
print("MOCK DOCKING (DEFAULT)")
print("="*70)
print()
print("If you skip AutoDock Vina installation:")
print()
print("✓ Pipeline WORKS with mock docking")
print("✓ Uses deterministic scoring (reproducible)")
print("✓ Perfect for testing and development")
print("✗ Less accurate than real Vina predictions")
print()
print("To upgrade later to real docking:")
print("  1. Install AutoDock Vina (any method above)")
print("  2. Run pipeline again:")
print("     python src/run_docking_pipeline.py")
print()
print("Pipeline will automatically use Vina if available!")
print()

print("="*70)
print("TESTING DOCKING")
print("="*70)
print()
print("To test your docking setup:")
print()
print("  1. Quick test with 10 molecules:")
print("     python src/run_docking_pipeline.py --max-molecules 10")
print()
print("  2. Check results:")
print("     ls outputs/docking/")
print()
print("  3. View top candidates:")
print("     cat outputs/docking/diabetes_final_ranked_candidates.csv | head -20")
print()

print("="*70)
print("INFERENCE MODE (NO DOWNLOADS)")
print("="*70)
print()
print("To run with pre-downloaded proteins:")
print()
print("  1. First, ensure PDB files exist:")
print("     ls outputs/docking/proteins/")
print()
print("  2. Run pipeline:")
print("     python src/run_docking_pipeline.py")
print()
print("Pipeline supports offline mode!")
print()
