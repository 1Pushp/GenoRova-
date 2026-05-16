import sys
from pathlib import Path

# Path setup (works on Render Linux + local Windows)
ROOT = Path(__file__).resolve().parent
GENOROVA = ROOT / "genorova"
SRC = GENOROVA / "src"

for p in [str(ROOT), str(GENOROVA), str(SRC)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Download checkpoint if missing (Render cold start)
try:
    from genorova.api.startup import download_checkpoint_if_missing

    download_checkpoint_if_missing()
except Exception as e:
    print(f"[STARTUP] Warning: {e}")

# Import and expose the full backend app used by Render.
from app.backend import main as backend_main  # noqa: E402

app = backend_main.app


def __getattr__(name):
    return getattr(backend_main, name)

__all__ = ["app"]
