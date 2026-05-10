import os, sys
from pathlib import Path

CHECKPOINT_URL  = "https://drive.google.com/uc?id=1QDJxsK0p7wI1pxDtV-mz36YTbPm65jXE"
CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "checkpoints" / "best.pt"
TOKENIZER_PATH  = Path(__file__).resolve().parent.parent / "tokenizer" / "genorova_bpe.json"
HF_REPO_ID      = os.getenv("GENOROVA_HF_REPO_ID", "pushp1/genorova-cvae")

def download_checkpoint_if_missing():
    if CHECKPOINT_PATH.exists():
        size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
        print(f"[STARTUP] Checkpoint found ({size_mb:.1f}MB)")
        return True

    print(f"[STARTUP] Downloading best.pt from HuggingFace: {HF_REPO_ID}")
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download

        local_path = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename="best.pt",
            local_dir=str(CHECKPOINT_PATH.parent),
        )
        print(f"[STARTUP] Downloaded from HuggingFace: {local_path}")

        if CHECKPOINT_PATH.exists() and CHECKPOINT_PATH.stat().st_size > 50 * 1024**2:
            size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
            print(f"[STARTUP] Checkpoint ready: {size_mb:.1f}MB")
            return True

        CHECKPOINT_PATH.unlink(missing_ok=True)
        raise RuntimeError("HuggingFace download produced a missing or too-small file")

    except Exception as hf_error:
        print(f"[STARTUP] HuggingFace download error: {hf_error}")
        print("[STARTUP] Falling back to Google Drive...")

        FILE_ID = "1QDJxsK0p7wI1pxDtV-mz36YTbPm65jXE"
        try:
            # Method 2: gdown
            import gdown
            url = f"https://drive.google.com/uc?id={FILE_ID}&export=download"
            gdown.download(url, str(CHECKPOINT_PATH), quiet=False)

            if CHECKPOINT_PATH.exists() and CHECKPOINT_PATH.stat().st_size > 1_000_000:
                size_mb = CHECKPOINT_PATH.stat().st_size / 1024**2
                print(f"[STARTUP] Downloaded via gdown: {size_mb:.1f}MB")
                return True

            print("[STARTUP] gdown failed or file too small, trying requests...")
            raise RuntimeError("File too small")

        except Exception as gdown_error:
            print(f"[STARTUP] gdown error: {gdown_error}")
            try:
                # Method 3: requests with session (handles Drive redirect)
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

                CHECKPOINT_PATH.unlink(missing_ok=True)
                print(f"[STARTUP] File too small ({size_mb:.1f}MB) - likely HTML error page")
                return False

            except Exception as requests_error:
                print(f"[STARTUP] requests error: {requests_error}")
                return False

def check_required_files():
    missing = []
    if not TOKENIZER_PATH.exists():
        missing.append(str(TOKENIZER_PATH))
    if missing:
        print(f"[STARTUP] WARNING — missing files: {missing}")
    return len(missing) == 0
