import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GENOROVA_SRC_DIR = ROOT_DIR / "genorova" / "src"

if str(GENOROVA_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(GENOROVA_SRC_DIR))

from api import GenerateRequest, ScoreRequest, best_molecules, generate, health, report, score

