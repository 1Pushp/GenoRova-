import os, sys
from pathlib import Path

CHECKPOINT_URL  = "https://drive.google.com/uc?id=1QDJxsK0p7wI1pxDtV-mz36YTbPm65jXE"
CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "checkpoints" / "best.pt"
TOKENIZER_PATH  = Path(__file__).resolve().parent.parent / "tokenizer" / "genorova_bpe.json"

def download_checkpoint_if_missing():
    if CHECKPOINT_PATH.exists():
        size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
        print(f"[STARTUP] Checkpoint found ({size_mb:.1f}MB)")
        return True

    print("[STARTUP] Downloading best.pt from Google Drive...")
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)

    FILE_ID = "1QDJxsK0p7wI1pxDtV-mz36YTbPm65jXE"

    try:
        # Method 1: gdown
        import gdown
        url = f"https://drive.google.com/uc?id={FILE_ID}&export=download"
        gdown.download(url, str(CHECKPOINT_PATH), quiet=False)

        if CHECKPOINT_PATH.exists() and CHECKPOINT_PATH.stat().st_size > 1_000_000:
            size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
            print(f"[STARTUP] Downloaded: {size_mb:.1f}MB")
            return True
        else:
            print("[STARTUP] gdown failed or file too small, trying requests...")
            raise Exception("File too small")

    except Exception as e1:
        print(f"[STARTUP] gdown error: {e1}")
        try:
            # Method 2: requests with session (handles Drive redirect)
            import requests
            session = requests.Session()

            # First request to get confirmation token
            url = f"https://drive.google.com/uc?id={FILE_ID}&export=download"
            response = session.get(url, stream=True)

            # Check for virus scan warning page
            token = None
            for key, value in response.cookies.items():
                if key.startswith('download_warning'):
                    token = value
                    break

            if token:
                url = f"https://drive.google.com/uc?id={FILE_ID}&export=download&confirm={token}"
                response = session.get(url, stream=True)

            # Write file
            with open(str(CHECKPOINT_PATH), 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded % (10 * 1024**2) == 0:
                            print(f"[STARTUP] Downloaded {downloaded/1024**2:.0f}MB...")

            size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
            if size_mb > 50:
                print(f"[STARTUP] Downloaded via requests: {size_mb:.1f}MB")
                return True
            else:
                CHECKPOINT_PATH.unlink(missing_ok=True)
                print(f"[STARTUP] File too small ({size_mb:.1f}MB) - likely HTML error page")
                return False

        except Exception as e2:
            print(f"[STARTUP] requests error: {e2}")
            return False

def check_required_files():
    missing = []
    if not TOKENIZER_PATH.exists():
        missing.append(str(TOKENIZER_PATH))
    if missing:
        print(f"[STARTUP] WARNING — missing files: {missing}")
    return len(missing) == 0
