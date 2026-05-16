from __future__ import annotations

import subprocess
import sys


subprocess.check_call(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "rdkit",
        "huggingface_hub",
        "--quiet",
    ]
)

DATA_CSV = "/kaggle/working/cleaned_molecules_v3.csv"
CKPT_DIR = "/kaggle/working/checkpoints"
TRAIN_SCRIPT = "/kaggle/working/genorova/src/train_cvae.py"

cmd = [
    sys.executable,
    TRAIN_SCRIPT,
    "--data-path",
    DATA_CSV,
    "--checkpoint-dir",
    CKPT_DIR,
    "--epochs",
    "25",
    "--batch-size",
    "64",
    "--lr",
    "0.00005",
    "--include-moses",
    "False",
    "--max-rows",
    "500000",
]

subprocess.run(cmd, check=True)

import torch

ckpt = torch.load(f"{CKPT_DIR}/best.pt", weights_only=False, map_location="cpu")
print(f"[RESULT] epoch={ckpt.get('epoch')} val_loss={ckpt.get('val_loss'):.4f}")
print(f"[RESULT] config: {ckpt.get('config')}")

print("=" * 60)
print("NEXT STEP: Upload checkpoint to HuggingFace")
print("Run this after downloading best.pt from Kaggle output:")
print()
print("  from huggingface_hub import HfApi")
print("  api = HfApi()")
print("  api.upload_file(")
print("      path_or_fileobj='best.pt',")
print("      path_in_repo='best.pt',")
print("      repo_id='pushp1/genorova-cvae',")
print("      token='YOUR_HF_TOKEN'")
print("  )")
print()
print("Then redeploy Render to pull the new checkpoint.")
print("=" * 60)
