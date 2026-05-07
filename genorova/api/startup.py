import os, sys
from pathlib import Path

CHECKPOINT_URL  = "https://drive.google.com/uc?id=1QDJxsK0p7wI1pxDtV-mz36YTbPm65jXE"
CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "checkpoints" / "best.pt"
TOKENIZER_PATH  = Path(__file__).resolve().parent.parent / "tokenizer" / "genorova_bpe.json"

def download_checkpoint_if_missing():
    if CHECKPOINT_PATH.exists():
        size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
        print(f"[STARTUP] Checkpoint found ({size_mb:.1f}MB): {CHECKPOINT_PATH}")
        return True

    print("[STARTUP] best.pt not found — downloading from Google Drive...")
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        import gdown
        gdown.download(CHECKPOINT_URL, str(CHECKPOINT_PATH), quiet=False, fuzzy=True)
        size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
        print(f"[STARTUP] Downloaded successfully: {size_mb:.1f}MB")
        return True
    except Exception as e:
        print(f"[STARTUP] ERROR downloading checkpoint: {e}")
        print("[STARTUP] Generation endpoints will be unavailable.")
        return False

def check_required_files():
    missing = []
    if not TOKENIZER_PATH.exists():
        missing.append(str(TOKENIZER_PATH))
    if missing:
        print(f"[STARTUP] WARNING — missing files: {missing}")
    return len(missing) == 0
