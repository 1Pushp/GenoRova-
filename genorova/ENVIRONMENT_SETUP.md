# Genorova AI - Complete Environment Setup Guide
## Fix All Import Errors - April 2026

---

## ✅ STATUS: YOUR ENVIRONMENT IS ALREADY WORKING!

Great news! Diagnostic testing shows:
- ✓ All critical packages installed (rdkit, numpy, PIL, tqdm, pandas, torch, scipy, matplotlib)
- ✓ All imports work correctly from Python
- ✗ VS Code just needs to know where to find them

---

## 🚀 QUICK FIX (5 Minutes)

### Step 1: Run Setup Script
```bash
cd "c:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova"
python setup_vscode.py
```

This automatically:
- Detects your Python interpreter
- Configures VS Code settings (.vscode/settings.json)
- Sets up debug configurations
- Recommends VS Code extensions

### Step 2: Reload VS Code
- Press `Ctrl+Shift+P`
- Type: `Developer: Reload Window`
- Press Enter

### Step 3: Verify
- Press `Ctrl+Shift+P`
- Type: `Python: Select Interpreter`
- Confirm it shows your Python path (C:\Program Files\Python314\python.exe)

### Step 4: Test
```bash
python test_environment.py
```

Expected output: ✅ ALL TESTS PASSED!

---

## 📋 DETAILED ENVIRONMENT REPORT

Run the diagnostic to see your complete setup:
```bash
python diagnostic.py
```

This shows:
- [x] Python interpreter location
- [x] Virtual environment status
- [x] Site-packages location
- [x] All critical import tests
- [x] VS Code settings
- [x] AutoDock Vina availability

---

## 🔧 IF SOMETHING IS MISSING

### Missing Package? Re-install
```bash
# For most packages:
pip install -r requirements.txt

# For RDKit specifically (if having issues):
pip install rdkit

# Or via conda (RECOMMENDED):
conda install -c conda-forge rdkit
```

### Still Getting Import Errors?

Run the fix script:
```bash
python fix_environment.py
```

This:
1. Upgrades pip
2. Installs all core dependencies
3. Installs docking dependencies
4. Verifies each installation
5. Guides next steps

---

## 🎯 COMPLETE FLOW (From Scratch)

If you want to rebuild environment from zero:

### Step 1: Activate Virtual Environment
```bash
cd "c:\Users\pushp\OneDrive\Desktop\organic chemistry"
.\genorova_env\Scripts\Activate.ps1
```

### Step 2: Upgrade Pip
```bash
python -m pip install --upgrade pip
```

### Step 3: Install All Dependencies
```bash
cd genorova
pip install -r requirements.txt
```

### Step 4: Fix VS Code
```bash
python setup_vscode.py
```

### Step 5: Test Everything
```bash
python test_environment.py
```

Expected output:
```
✅ ALL TESTS PASSED!

Environment is ready for:
  • Running molecular docking pipeline
  • Training generative models
  • Processing drug candidates
```

---

## 📦 WHAT GETS INSTALLED

### Science & Math (Required)
- numpy 2.4.3 - Array computing
- scipy 1.17.1 - Scientific algorithms
- pandas 3.0.2 - Data analysis
- matplotlib 3.10.8 - Plotting

### Chemistry (Required)
- rdkit 2026.3.1 - Molecular structures
- biopython 1.81 - Protein analysis
- biotite 0.40.1 - Bioinformatics

### Deep Learning (Required)
- torch 2.11.0 - Neural networks
- torchvision 0.26.0 - Computer vision

### Docking (Optional)
- vina 1.2.5 - Molecular docking (install separately)
- meeko 0.5.0 - Ligand prep (optional)
- pdbfixer 1.10 - PDB cleaning (optional)

### Utilities
- pillow 12.1.1 - Image processing
- tqdm 4.67.3 - Progress bars
- requests 2.31.0 - HTTP client

---

## 🎓 UNDERSTANDING ERRORS

### Error: "Import rdkit could not be resolved"
**Cause**: VS Code using different Python interpreter

**Solution**:
```bash
# Check which Python VS Code sees:
Ctrl+Shift+P > Python: Select Interpreter

# Should match:
python diagnostic.py
```

### Error: "ModuleNotFoundError: No module named 'numpy'"
**Cause**: Package not installed in selected environment

**Solution**:
```bash
pip install numpy
python test_environment.py
```

### Error: "Windows Defender blocked import"
**Cause**: Antivirus scanning RDKit DLL

**Solution**: Add Windows Defender exclusion
```powershell
Add-MpPreference -ExclusionPath "C:\Users\pushp\OneDrive\Desktop\organic chemistry\genorova_env\Lib\site-packages\rdkit"
```

---

## 🚀 QUICK COMMANDS REFERENCE

| Task | Command |
|------|---------|
| Diagnose environment | `python diagnostic.py` |
| Run tests | `python test_environment.py` |
| Fix missing packages | `python fix_environment.py` |
| Configure VS Code | `python setup_vscode.py` |
| Install Vina guide | `python install_vina.py` |
| Run docking (test) | `python src/run_docking_pipeline.py --max-molecules 10` |
| Run docking (full) | `python src/run_docking_pipeline.py` |

---

## 🔍 VS CODE SETUP DETAILS

After running `setup_vscode.py`, these files are created:

### .vscode/settings.json
```json
{
  "python.defaultInterpreterPath": "C:\\Program Files\\Python314\\python.exe",
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black"
}
```

### .vscode/launch.json
Debug configurations for:
- Main docking pipeline
- Environment testing
- Individual file execution

### .vscode/extensions.json
Recommended VS Code extensions:
- Python (official)
- Pylance (advanced IntelliSense)
- Black Formatter
- Flake8 Linter

---

## 💻 VS CODE MANUAL CONFIGURATION

If script doesn't work, manually configure:

1. **Select Interpreter**:
   - `Ctrl+Shift+P` → `Python: Select Interpreter`
   - Choose: `C:\Program Files\Python314\python.exe`

2. **Check Settings**:
   - `File` → `Preferences` → `Settings`
   - Search: `python.defaultInterpreterPath`
   - Set to your Python path

3. **Reload**:
   - `Ctrl+Shift+P` → `Developer: Reload Window`

4. **Verify**:
   - Open any Python file
   - Check bottom-right status bar (should show Python version)
   - No red squiggles = working!

---

## 🎯 VALIDATION CHECKLIST

After fixing, verify all items:

- [ ] `python diagnostic.py` runs without errors
- [ ] `python test_environment.py` shows ✅ ALL TESTS PASSED
- [ ] VS Code shows no red squiggles in .py files
- [ ] `Ctrl+Shift+P` → `Python: Select Interpreter` shows correct path
- [ ] `python -c "import rdkit; print('OK')"` works
- [ ] `python src/quick_test.py` passes all tests
- [ ] Bottom-right of VS Code shows Python 3.14.4 (or similar)

---

## 📞 TROUBLESHOOTING

### "Python interpreter not found"
```bash
# Find it:
where python

# If not found, install from:
https://www.python.org/downloads/
```

### "pip command not found"
```bash
python -m pip --version
```

### "Still getting import errors after setup"
```bash
# Nuclear option - reinstall everything:
pip install --upgrade --force-reinstall -r requirements.txt
```

### "RDKit import hangs or crashes"
```bash
# Windows Defender blocking:
Add-MpPreference -ExclusionPath "C:\...\genorova_env\Lib\site-packages\rdkit"

# Or use conda instead:
conda install -c conda-forge rdkit
```

---

## ✨ ADVANCED: Custom Python Environment

If you want to use the venv instead of system Python:

```bash
# Activate venv:
.\genorova_env\Scripts\Activate.ps1

# Install into venv:
pip install -r requirements.txt

# Update VS Code:
python setup_vscode.py

# VS Code will now use venv Python
```

---

## 📚 NEXT STEPS

Once environment is fixed:

1. **Run quick test**:
   ```bash
   cd genorova/src
   python run_docking_pipeline.py --max-molecules 10
   ```

2. **Review outputs**:
   ```bash
   cat ../outputs/docking/diabetes_final_ranked_candidates.csv
   ```

3. **Full production run**:
   ```bash
   python run_docking_pipeline.py
   ```

---

## 📝 FILES FOR THIS SETUP

| File | Purpose |
|------|---------|
| `diagnostic.py` | Complete environment scan |
| `test_environment.py` | Import validation tests |
| `fix_environment.py` | Auto-install missing packages |
| `setup_vscode.py` | VS Code configuration |
| `install_vina.py` | AutoDock Vina guide |
| `requirements.txt` | All Python dependencies |

---

## 🎉 SUCCESS!

When everything is working, you should see:

```
[TEST 1] Python Version
    ✓ PASS: Python 3.9+ required

[TEST 2] Core Imports
    ✓ numpy (2.4.3)
    ✓ scipy (1.17.1)
    ✓ pandas (3.0.2)

[TEST 3] Chemistry & ML
    ✓ rdkit (2026.3.1)
    ✓ torch (2.11.0+cpu)

[TEST 4] Genorova Modules
    ✓ data_loader
    ✓ preprocessor
    ✓ model

[TEST 5] Docking Modules
    ✓ protein_prep
    ✓ ligand_prep
    ✓ docking_engine

✅ ALL TESTS PASSED!
```

---

## 📞 SUPPORT

If something doesn't work:

1. Run: `python diagnostic.py` → Share output
2. Run: `python test_environment.py` → Share failures
3. Check: `requirements.txt` for all dependencies
4. Reinstall: `pip install -r requirements.txt`

---

**Generated**: April 12, 2026  
**Status**: Production Ready ✅  
**Last Updated**: After diagnostic validation
