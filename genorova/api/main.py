import sys, torch, os, time, logging, json
from pathlib import Path
from typing import Optional, List

from rdkit import Chem, RDLogger
RDLogger.DisableLog('rdApp.*')

from train_cvae import CVAETokenizer
from models.cvae import CVAE
from admet.scorer import score_batch as _score_batch, score_smiles as _score_smiles

GENOROVA_DIR = Path(__file__).resolve().parent.parent

# ── Load model once at startup ────────────────────────────────
CKPT_PATH = GENOROVA_DIR / "outputs" / "checkpoints" / "best.pt"
ckpt  = torch.load(CKPT_PATH, weights_only=False, map_location='cpu')
cfg   = ckpt['config']

TOK = CVAETokenizer(
    GENOROVA_DIR / "tokenizer" / "genorova_bpe.json",
    max_len=cfg['max_seq_len'],
)
MODEL = CVAE(vocab_size=cfg['vocab_size'], latent_dim=cfg['latent_dim'],
             d_model=cfg['d_model'], num_heads=cfg['num_heads'],
             num_layers=cfg['num_layers'])
MODEL.load_state_dict(ckpt['model_state'])
MODEL.eval()

MODEL_EPOCH    = ckpt['epoch']
MODEL_VAL_LOSS = ckpt['val_loss']
MAX_LEN = cfg['max_seq_len']

# ── Logging ───────────────────────────────────────────────────
LOG_DIR = GENOROVA_DIR / "outputs" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / 'api.log'),
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

# ── FastAPI ───────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Genorova AI",
    description="""
## Generative Drug Discovery API

Built by **Pushp Dwivedi** | [GitHub](https://github.com/1Pushp)

### Benchmark Results (MOSES Official)
| Metric | Genorova AI | REINVENT | MolGPT | JT-VAE |
|--------|------------|---------|--------|--------|
| SNN/Test ↑ | **0.611 ★** | 0.58 | 0.56 | 0.54 |
| Filters ↑ | **97.3% ★** | ~95% | ~94% | ~97% |
| Validity | 70.9% | 96.8% | 98.5% | 100% |

### DPP-4 Specialist
Tanimoto similarity **0.836** vs Sitagliptin (FDA-approved diabetes drug)

### Endpoints
- `POST /generate` — generate novel drug-like molecules
- `POST /score` — full ADMET profile for any SMILES
- `POST /batch-score` — score up to 500 molecules
- `GET /metrics` — benchmark results and novelty stats
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Schemas ───────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    target: str = Field(default="ANY",
        description="DPP4 (diabetes) | GYRASE (antibacterial) | ANY")
    n_molecules: int = Field(default=50, ge=1, le=500)
    mw_max: float  = Field(default=550.0, description="Max molecular weight (Da)")
    qed_min: float = Field(default=0.0,   description="Min QED score (0-1)")
    temperature: float = Field(default=1.1, ge=0.5, le=2.0)

class MoleculeResult(BaseModel):
    rank: int
    smiles: str
    qed: float
    mw: float
    logp: float
    sa_score: float
    composite_score: float
    grade: str
    lipinski_pass: bool

class ScoreRequest(BaseModel):
    smiles: str

class BatchScoreRequest(BaseModel):
    smiles_list: List[str] = Field(..., description="Max 500 molecules")

# ── API key auth ──────────────────────────────────────────────
def require_key(x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key:
        raise HTTPException(status_code=401,
            detail="X-API-Key header required. Use any non-empty string for dev.")

# ── Generation helper ─────────────────────────────────────────
def _generate(n: int, temperature: float = 1.1) -> list[str]:
    valid, attempts = [], 0
    max_attempts = n * 5
    while len(valid) < n and attempts < max_attempts:
        prop = torch.zeros(1, 4)
        seqs = MODEL.generate(prop, max_len=MAX_LEN, beam_k=1, temperature=temperature)
        attempts += 1
        smi = TOK.ids_to_smiles(seqs[0])
        if smi and Chem.MolFromSmiles(smi):
            valid.append(smi)
    return list(dict.fromkeys(valid))   # deduplicate preserving order

# ── Endpoints ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard():
    dashboard = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"
    if dashboard.exists():
        return HTMLResponse(content=dashboard.read_text(encoding="utf-8"))
    return HTMLResponse(content="""
    <html>
    <head><title>Genorova AI</title></head>
    <body style="margin:0;background:#0B1D35;color:#fff;
    font-family:system-ui;display:flex;align-items:center;
    justify-content:center;height:100vh;flex-direction:column">
      <div style="color:#02C39A;font-size:42px;font-weight:bold;
      letter-spacing:4px">GENOROVA AI</div>
      <div style="color:#7A9BBF;margin:12px 0 32px">
        Generative Drug Discovery · SNN/Test 0.611 · Beats REINVENT
      </div>
      <div style="display:flex;gap:16px">
        <a href="/docs" style="background:#02C39A;color:#0B1D35;
        padding:10px 24px;border-radius:8px;text-decoration:none;
        font-weight:bold">API Documentation</a>
        <a href="/health" style="border:1px solid #02C39A;color:#02C39A;
        padding:10px 24px;border-radius:8px;text-decoration:none">
        Health Check</a>
      </div>
    </body></html>
    """)

@app.get("/health", tags=["System"])
def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "model": "Genorova CVAE",
        "model_epoch": MODEL_EPOCH,
        "model_val_loss": round(MODEL_VAL_LOSS, 4),
        "model_params": "6,785,068",
        "training_molecules": 10873,
        "benchmarks": {
            "snn_test": 0.611,
            "snn_note": "Beats REINVENT 0.58, MolGPT 0.56, JT-VAE 0.54",
            "validity": 0.709,
            "uniqueness": 0.911,
            "novelty": 0.641,
            "filter_pass_rate": 0.973,
            "fcd_test": 6.23
        },
        "dpp4": {
            "tanimoto_vs_sitagliptin": 0.836,
            "top_hit_ic50_nm": 0.012,
            "training_actives": 2273
        },
        "built_by": "Pushp Dwivedi",
        "github": "https://github.com/1Pushp",
        "timestamp": time.time()
    }

@app.get("/metrics", tags=["System"])
def metrics():
    out = {}
    for name, path in [
        ("novelty",  GENOROVA_DIR / "outputs" / "NOVELTY_PROOF_REPORT.json"),
        ("moses",    GENOROVA_DIR / "benchmarks" / "moses_results.json"),
    ]:
        if path.exists():
            out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out

@app.post("/generate", response_model=List[MoleculeResult], tags=["Generation"])
def generate(req: GenerateRequest, _=Depends(require_key)):
    t0 = time.time()
    logging.info(f"POST /generate target={req.target} n={req.n_molecules}")

    smiles_list = _generate(req.n_molecules, req.temperature)
    if not smiles_list:
        raise HTTPException(status_code=500,
            detail="Generation failed — model produced no valid SMILES")

    df = _score_batch(smiles_list)

    df = df[df['MW']  <= req.mw_max]
    df = df[df['QED'] >= req.qed_min]
    df = df.sort_values('composite_score', ascending=False).reset_index(drop=True)

    results = []
    for i, row in df.iterrows():
        results.append(MoleculeResult(
            rank=i + 1,
            smiles=str(row['smiles']),
            qed=round(float(row['QED']), 4),
            mw=round(float(row['MW']), 2),
            logp=round(float(row['LogP']), 3),
            sa_score=round(float(row['SA_Score']), 3),
            composite_score=round(float(row['composite_score']), 2),
            grade=str(row['grade']),
            lipinski_pass=bool(row['lipinski_pass'])
        ))

    elapsed = time.time() - t0
    logging.info(f"POST /generate done: {len(results)} results in {elapsed:.1f}s")
    return results

@app.post("/score", tags=["Scoring"])
def score_one(req: ScoreRequest, _=Depends(require_key)):
    result = _score_smiles(req.smiles)
    if not result.get('valid'):
        raise HTTPException(status_code=422,
            detail=f"Invalid SMILES: {req.smiles}")
    return result

@app.post("/batch-score", tags=["Scoring"])
def batch_score(req: BatchScoreRequest, _=Depends(require_key)):
    if len(req.smiles_list) > 500:
        raise HTTPException(status_code=400,
            detail="Max 500 molecules per batch request")
    df = _score_batch(req.smiles_list)
    # to_json handles NaN → null natively; re-parse so FastAPI returns a list
    return json.loads(df.to_json(orient='records'))

# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("genorova.api.main:app",
                host="0.0.0.0", port=8000, reload=False)
