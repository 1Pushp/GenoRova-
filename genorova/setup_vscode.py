#!/usr/bin/env python3
"""
Genorova AI - VS Code Configuration Fixer
Automatically configures VS Code to use the correct Python interpreter
"""

import sys
import json
import os
from pathlib import Path

print("="*70)
print("GENOROVA AI - VS CODE CONFIGURATION FIXER")
print("="*70)
print()

# Current Python executable
current_python = sys.executable
print(f"[1] Current Python Interpreter")
print(f"    {current_python}")
print()

# VS Code settings location
vscode_settings = Path.home() / '.vscode' / 'settings.json'
workspace_settings = Path.cwd() / '.vscode' / 'settings.json'

print(f"[2] VS Code Settings Locations")
print(f"    User Settings: {vscode_settings}")
print(f"    Workspace Settings: {workspace_settings}")
print()

# Create .vscode directory if needed
vscode_dir = workspace_settings.parent
vscode_dir.mkdir(exist_ok=True)

# Read or create workspace settings
print(f"[3] Creating Workspace Configuration")
if workspace_settings.exists():
    with open(workspace_settings, 'r') as f:
        settings = json.load(f)
    print(f"    ✓ Existing settings found")
else:
    settings = {}
    print(f"    ✓ Creating new settings file")

# Update Python interpreter settings
settings['python.defaultInterpreterPath'] = current_python
settings['python.linting.enabled'] = True
settings['python.linting.pylintEnabled'] = False
settings['python.linting.flake8Enabled'] = True
settings['python.formatting.provider'] = 'black'
settings['[python]'] = {
    'editor.formatOnSave': True,
    'editor.defaultFormatter': 'ms-python.python'
}

# Pylance settings for better IntelliSense
settings['python.analysis.typeCheckingMode'] = 'off'  # or 'basic' for checking
settings['python.analysis.diagnosticsMode'] = 'pull'

# Write settings
with open(workspace_settings, 'w') as f:
    json.dump(settings, f, indent=2)

print(f"    ✓ Settings written to: {workspace_settings}")
print()

# Create .vscode/extensions.json to recommend extensions
extensions_file = vscode_dir / 'extensions.json'
extensions_config = {
    "recommendations": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-python.debugpy",
        "ms-python.black-formatter",
        "ms-python.flake8",
        "ms-python.pylint",
        "formulahendry.code-runner"
    ]
}

with open(extensions_file, 'w') as f:
    json.dump(extensions_config, f, indent=2)

print(f"[4] VS Code Extensions Configuration")
print(f"    ✓ Created: {extensions_file}")
print(f"    Recommended extensions:")
for ext in extensions_config['recommendations']:
    print(f"      • {ext}")
print()

# Create launch.json for debugging
launch_file = vscode_dir / 'launch.json'
launch_config = {
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Main Pipeline",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/src/run_docking_pipeline.py",
            "console": "integratedTerminal",
            "justMyCode": True,
            "args": ["--max-molecules", "10"],
            "preLaunchTask": "python.linting"
        },
        {
            "name": "Python: Test Environment",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/test_environment.py",
            "console": "integratedTerminal",
            "justMyCode": True
        },
        {
            "name": "Python: Current File",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "justMyCode": True
        }
    ]
}

with open(launch_file, 'w') as f:
    json.dump(launch_config, f, indent=2)

print(f"[5] VS Code Debug Configuration")
print(f"    ✓ Created: {launch_file}")
print(f"    Debug configurations created for:")
print(f"      • Main docking pipeline")
print(f"      • Environment testing")
print(f"      • Current file execution")
print()

print("="*70)
print("✅ VS CODE CONFIGURATION COMPLETE!")
print("="*70)
print()
print("NEXT STEPS:")
print("1. Reload VS Code:")
print("   • Ctrl+Shift+P > Developer: Reload Window")
print()
print("2. Verify interpreter in Status Bar:")
print("   • Bottom-right of VS Code shows Python version")
print("   • Should show: Python 3.14.4 (or similar)")
print()
print("3. Open any .py file and check for import errors:")
print("   • If red squiggles remain, run:")
print("     python test_environment.py")
print()
print("4. To debug with launch configs:")
print("   • F5 to start debugging")
print("   • Or Click 'Run > Run Without Debugging'")
print()
print("Configuration saved to:")
print(f"  {workspace_settings}")
print(f"  {extensions_file}")
print(f"  {launch_file}")
