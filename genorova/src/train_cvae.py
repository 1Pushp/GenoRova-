"""
genorova/src/train_cvae.py

Production training loop for the Genorova Conditional VAE.

Features
--------
  - MoleculeDataset  : BPE tokenisation + QED/LogP/MW/SA property labels
  - AdamW + LambdaLR warmup/flat schedule
  - Automatic Mixed Precision (enabled automatically when CUDA is present)
  - Gradient clipping, slow KL beta warmup
  - Step logging (every 100 steps): loss components, perplexity, validity %
  - Epoch validation: validity %, uniqueness %, novelty %
  - Checkpoints: best-by-val-loss + every-N-epoch snapshots + resume
  - Optional Weights & Biases logging (--wandb flag)

Usage
-----
  python genorova/src/train_cvae.py                        # defaults
  python genorova/src/train_cvae.py --epochs 5             # quick smoke test
  python genorova/src/train_cvae.py --include-moses        # add MOSES data
  python genorova/src/train_cvae.py --resume               # resume last run
  python genorova/src/train_cvae.py --wandb                # W&B logging

Data priority (first match wins)
  1. genorova/data/processed/cleaned_molecules_v3.csv  (500K, run expand_data_v3.py)
  2. genorova/data/processed/cleaned_molecules_v2.csv  (10K fallback, pre-computed props)
  3. genorova/data/processed/cleaned_molecules.csv      (v1 fallback)
  3. genorova/data/moses/train.csv (if --include-moses, up to --max-moses rows)
"""

import argparse
import csv
import math
import os
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, random_split
from tqdm import tqdm

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths — train_cvae.py lives at genorova/src/
# ---------------------------------------------------------------------------
_SRC   = Path(__file__).resolve().parent          # genorova/src/
_ROOT  = _SRC.parent                              # genorova/
sys.path.insert(0, str(_ROOT))                    # allow: from models.cvae import ...

from models.cvae import (                         # noqa: E402
    CVAE, print_model_summary,
    PAD_ID, BOS_ID, EOS_ID, MAX_SEQ_LEN, NUM_PROPS,
)

DATA_DIR       = _ROOT / "data" / "processed"
MOSES_TRAIN    = _ROOT / "data" / "moses" / "train.csv"
TOKENIZER_PATH = _ROOT / "tokenizer" / "genorova_bpe.json"

# ---------------------------------------------------------------------------
# SA_score — rdkit contrib, fallback to fixed mean (4.0) if unavailable
# ---------------------------------------------------------------------------
try:
    from rdkit.Chem import RDConfig
    sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
    from sascorer import calculateScore as _calc_sa   # type: ignore
    _SA_AVAILABLE = True
except Exception:
    _SA_AVAILABLE = False
    warnings.warn("[SA_score] Not available — using mean value 4.0 for all molecules.")

try:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, QED as QEDCalc
    from rdkit.Chem.rdMolDescriptors import CalcTPSA
    RDLogger.DisableLog("rdApp.*")   # silence SMILES parse noise in logs
    _RDKIT_OK = True
except ImportError:
    _RDKIT_OK = False
    sys.exit("[ERROR] RDKit is required. Install with: conda install rdkit")

try:
    from tokenizers import Tokenizer as HFTokenizer
    _TOKENIZER_OK = True
except ImportError:
    _TOKENIZER_OK = False
    sys.exit("[ERROR] tokenizers library required. Run: pip install tokenizers")

PROP_NAMES = ["QED", "LogP", "MW", "SA"]


# ===========================================================================
# Config
# ===========================================================================

@dataclass
class TrainConfig:
    """All training hyperparameters in one place."""
    # Data
    max_seq_len:    int   = MAX_SEQ_LEN
    val_fraction:   float = 0.10
    max_moses_rows: int   = 50_000
    max_rows:       int   = 0       # 0 = use all rows; >0 caps dataset for smoke tests
    data_path: Optional[str] = None

    # Model
    vocab_size:  int   = 1000
    latent_dim:  int   = 512
    d_model:     int   = 256
    num_heads:   int   = 4
    num_layers:  int   = 3
    dropout:     float = 0.15

    # Training
    epochs:         int   = 50
    batch_size:     int   = 256
    micro_batch_size: int = 128
    lr:             float = 1e-3
    weight_decay:   float = 1e-4
    label_smoothing: float = 0.1
    grad_clip:      float = 1.0
    warmup_epochs:  int   = 5     # LR warmup; beta uses step-based slow warmup
    kl_free_bits:   float = 0.5
    kl_cycle_len:   int   = 10
    lambda_prop:    float = 0.5

    # Checkpointing
    save_every: int  = 5
    resume:       bool = False
    resume_from: Optional[str] = None
    checkpoint_dir: Optional[str] = None

    # Logging
    log_every_n_steps: int  = 100
    val_gen_n:         int  = 50    # molecules to generate during validation
    wandb_enabled:     bool = False
    wandb_project:     str  = "genorova-cvae"

    # Hardware
    num_workers: int  = 0      # 0 = main process only (safest on Windows)
    include_moses: bool = False


# ===========================================================================
# Tokenizer wrapper
# ===========================================================================

class CVAETokenizer:
    """
    Thin wrapper around the HuggingFace BPE tokenizer that adds
    BOS/EOS framing and pads to a fixed max_len.
    """

    def __init__(self, path: Path, max_len: int = MAX_SEQ_LEN):
        if not path.exists():
            sys.exit(f"[ERROR] Tokenizer not found at {path}\n"
                     "Run: python genorova/src/bpe_tokenizer.py first.")
        self.hf     = HFTokenizer.from_file(str(path))
        self.max_len = max_len

    def encode(self, smiles: str) -> list[int]:
        """Encode a SMILES string to a padded, BOS/EOS-framed token-id list."""
        ids = self.hf.encode(smiles).ids
        ids = [BOS_ID] + ids[: self.max_len - 2] + [EOS_ID]
        ids += [PAD_ID] * (self.max_len - len(ids))
        return ids

    def encode_batch(self, smiles_list: list[str]) -> np.ndarray:
        """Encode a list of SMILES; returns int32 array [N, max_len]."""
        return np.array([self.encode(s) for s in smiles_list], dtype=np.int32)

    def ids_to_smiles(self, token_ids) -> str:
        """Convert a token-id sequence back to a SMILES string."""
        skip = {PAD_ID, BOS_ID, EOS_ID}
        pieces = [self.hf.id_to_token(int(i))
                  for i in token_ids if int(i) not in skip]
        return "".join(p for p in pieces if p is not None)

    @property
    def pad_id(self) -> int:
        return PAD_ID

    @property
    def vocab_size(self) -> int:
        return self.hf.get_vocab_size()


# ===========================================================================
# Property computation
# ===========================================================================

def _mol_props(smi: str) -> Optional[tuple[float, float, float, float]]:
    """
    Compute (QED, LogP, MW, SA_score) for a SMILES string.
    Returns None if the molecule is invalid.
    """
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return None
    try:
        qed  = QEDCalc.qed(mol)
        logp = Descriptors.MolLogP(mol)
        mw   = Descriptors.ExactMolWt(mol)
        sa   = _calc_sa(mol) if _SA_AVAILABLE else 4.0
        return qed, logp, mw, sa
    except Exception:
        return None


def _compute_props(smi: str) -> Optional[dict[str, float]]:
    """Compute training properties for a SMILES string when CSV columns are absent."""
    try:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return None
        CalcTPSA(mol)
        return {
            "qed":        round(QEDCalc.qed(mol), 4),
            "logp":       round(Descriptors.MolLogP(mol), 4),
            "mol_weight": round(Descriptors.MolWt(mol), 4),
            "sa_score":   2.0,
        }
    except Exception:
        return None


def compute_props_batch(smiles_list: list[str],
                        desc: str = "properties") -> tuple[list[str], np.ndarray]:
    """
    Compute properties for a list of SMILES.
    Returns (valid_smiles, props_array [N, 4]).
    """
    valid_smi: list[str]         = []
    props:     list[tuple]       = []
    for smi in tqdm(smiles_list, desc=f"  Computing {desc}", unit="mol", leave=False):
        result = _mol_props(smi)
        if result is not None:
            valid_smi.append(smi)
            props.append(result)
    return valid_smi, np.array(props, dtype=np.float32)


# ===========================================================================
# Dataset
# ===========================================================================

class MoleculeDataset(Dataset):
    """
    PyTorch Dataset for SMILES + property vectors.

    Each item: {tokens [max_len], props [4], smiles str}
    Properties: [QED, LogP, MW, SA_score]  (z-score normalised)
    """

    def __init__(self,
                 smiles:    list[str],
                 props_raw: np.ndarray,          # [N, 4] un-normalised
                 tokenizer: CVAETokenizer,
                 prop_mean: Optional[np.ndarray] = None,
                 prop_std:  Optional[np.ndarray] = None):
        self.smiles    = smiles
        self.tokenizer = tokenizer

        # Fit or apply property normalisation
        if prop_mean is None:
            self.prop_mean = props_raw.mean(axis=0)
            self.prop_std  = props_raw.std(axis=0).clip(min=1e-6)
        else:
            self.prop_mean = prop_mean
            self.prop_std  = prop_std

        props_norm = (props_raw - self.prop_mean) / self.prop_std
        self.props  = torch.from_numpy(props_norm).float()

        # Pre-tokenise all SMILES (done once at init, stored in RAM)
        print(f"  Tokenising {len(smiles):,} SMILES...")
        token_arr   = tokenizer.encode_batch(smiles)   # [N, max_len]
        self.tokens = torch.from_numpy(token_arr).long()

    def __len__(self) -> int:
        return len(self.smiles)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        return {"tokens": self.tokens[idx],
                "props":  self.props[idx],
                "smiles": self.smiles[idx]}


# ===========================================================================
# Data loading
# ===========================================================================

def _load_v2_csv(path: Path) -> tuple[list[str], np.ndarray]:
    """
    Load cleaned_molecules_v2.csv which has pre-computed sa_score column.
    Order of property columns must match NUM_PROPS=4: [qed, logp, mol_weight, sa_score].
    Skips slow on-the-fly property computation since v2 stores them already.
    """
    df = pd.read_csv(path)
    df = df.dropna(subset=["smiles"]).copy()
    df["smiles"] = df["smiles"].str.strip()
    smiles = df["smiles"].tolist()

    required_props = ("qed", "logp", "mol_weight")
    if any(col not in df.columns for col in required_props):
        print(f"[DATA] Computing properties for {len(smiles)} molecules — this takes ~2 min")
        valid_smiles: list[str] = []
        computed_props: list[dict[str, float]] = []
        for smi in tqdm(smiles, desc="  Computing CSV properties", unit="mol", leave=False):
            props = _compute_props(smi)
            if props is None:
                continue
            valid_smiles.append(smi)
            computed_props.append(props)
        if not computed_props:
            sys.exit(f"[ERROR] No valid molecules found while computing properties for {path}")
        props = pd.DataFrame(computed_props)[["qed", "logp", "mol_weight", "sa_score"]]
        return valid_smiles, props.values.astype(np.float32)

    if "sa_score" not in df.columns:
        df["sa_score"] = 2.0

    props = df[["qed", "logp", "mol_weight", "sa_score"]].copy()
    props["sa_score"] = props["sa_score"].fillna(2.0)
    props = props.dropna(subset=list(required_props))
    smiles = df.loc[props.index, "smiles"].tolist()
    props = props.values.astype(np.float32)
    return smiles, props


def _load_cleaned_csv(path: Path) -> tuple[list[str], np.ndarray]:
    """Load cleaned_molecules.csv (v1 format) and compute SA_score on-the-fly."""
    df = pd.read_csv(path)
    smiles = df["smiles"].dropna().str.strip().tolist()
    # v1 CSV does not have sa_score; compute all four properties now
    valid_smi, props = compute_props_batch(smiles, desc="cleaned CSV (v1)")
    return valid_smi, props


def _load_moses_csv(path: Path, max_rows: int) -> tuple[list[str], np.ndarray]:
    """Load MOSES train CSV (SMILES only) and compute all four properties."""
    df     = pd.read_csv(path, nrows=max_rows)
    col    = "SMILES" if "SMILES" in df.columns else df.columns[0]
    smiles = df[col].dropna().str.strip().tolist()
    valid_smi, props = compute_props_batch(smiles, desc="MOSES train")
    return valid_smi, props


def build_dataloaders(cfg: TrainConfig,
                      tokenizer: CVAETokenizer
                      ) -> tuple[DataLoader, DataLoader, set[str]]:
    """
    Build train and validation DataLoaders from configured data sources.

    Data priority:
      1. cleaned_molecules_v3.csv (preferred — 500K molecules from expand_data_v3.py)
      2. cleaned_molecules_v2.csv (fallback — 10K with pre-computed properties)
      3. cleaned_molecules.csv    (v1 fallback — computes SA_score on-the-fly)
      4. MOSES train.csv          (if --include-moses flag is set)

    Returns (train_loader, val_loader, training_smiles_set).
    The training_smiles_set is used for novelty checking in validation.
    """
    all_smi:   list[str]  = []
    all_props: list[np.ndarray] = []
    dataset_name = "none"
    dataset_rows = 0

    print("[DATA] Loading datasets...")

    # Priority: v3 (500K, expand_data_v3.py) → v2 (10K) → v1 (950)
    cleaned_v3 = DATA_DIR / "cleaned_molecules_v3.csv"
    cleaned_v2 = DATA_DIR / "cleaned_molecules_v2.csv"
    cleaned_v1 = DATA_DIR / "cleaned_molecules.csv"

    override_data_path = Path(cfg.data_path).resolve() if cfg.data_path else None

    if override_data_path is not None:
        if not override_data_path.exists():
            sys.exit(f"[ERROR] Data path not found: {override_data_path}")
        smi, props = _load_v2_csv(override_data_path)
        all_smi.extend(smi); all_props.append(props)
        dataset_name = override_data_path.name
        dataset_rows = len(smi)
        print(f"  data_path override: {len(smi):,} from {override_data_path}")
    elif cleaned_v3.exists():
        smi, props = _load_v2_csv(cleaned_v3)   # v3 has same columns as v2
        all_smi.extend(smi); all_props.append(props)
        dataset_name = cleaned_v3.name
        dataset_rows = len(smi)
        print(f"  cleaned_molecules_v3: {len(smi):,} (500K dataset)")
    elif cleaned_v2.exists():
        smi, props = _load_v2_csv(cleaned_v2)
        all_smi.extend(smi); all_props.append(props)
        dataset_name = cleaned_v2.name
        dataset_rows = len(smi)
        print(f"  cleaned_molecules_v2: {len(smi):,} (pre-computed props)")
    elif cleaned_v1.exists():
        smi, props = _load_cleaned_csv(cleaned_v1)
        all_smi.extend(smi); all_props.append(props)
        dataset_name = cleaned_v1.name
        dataset_rows = len(smi)
        print(f"  cleaned_molecules (v1): {len(smi):,} valid")

    if cfg.include_moses and MOSES_TRAIN.exists():
        smi, props = _load_moses_csv(MOSES_TRAIN, cfg.max_moses_rows)
        all_smi.extend(smi); all_props.append(props)
        print(f"  MOSES train:          {len(smi):,} valid")

    if not all_smi:
        sys.exit("[ERROR] No data found. Run: python genorova/src/data_expansion.py")

    props_all = np.concatenate(all_props, axis=0)

    if cfg.max_rows > 0 and len(all_smi) > cfg.max_rows:
        all_smi   = all_smi[:cfg.max_rows]
        props_all = props_all[:cfg.max_rows]
        print(f"  [max-rows] Capped to {cfg.max_rows:,} rows for smoke test")

    print(f"[DATASET] Primary dataset: {dataset_name} rows={dataset_rows:,}")
    print(f"  Total:             {len(all_smi):,} molecules\n")

    # Train / val split
    n_val   = max(1, int(len(all_smi) * cfg.val_fraction))
    n_train = len(all_smi) - n_val
    idx     = np.random.permutation(len(all_smi))
    tr_idx, val_idx = idx[:n_train], idx[n_train:]

    tr_smi   = [all_smi[i] for i in tr_idx]
    val_smi  = [all_smi[i] for i in val_idx]
    tr_props  = props_all[tr_idx]
    val_props = props_all[val_idx]

    # Fit normalisation on training set only
    train_ds = MoleculeDataset(tr_smi, tr_props, tokenizer)
    val_ds   = MoleculeDataset(val_smi, val_props, tokenizer,
                                prop_mean=train_ds.prop_mean,
                                prop_std=train_ds.prop_std)

    nw = cfg.num_workers
    tr_loader  = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True,
                            num_workers=nw, pin_memory=False, drop_last=True)
    val_loader = DataLoader(val_ds,   batch_size=cfg.batch_size, shuffle=False,
                            num_workers=nw, pin_memory=False)

    print(f"  Train batches: {len(tr_loader):,}   Val batches: {len(val_loader):,}")
    return tr_loader, val_loader, set(tr_smi)


# ===========================================================================
# Metrics helpers
# ===========================================================================

def decode_generated(seqs: list[list[int]], tokenizer: CVAETokenizer) -> list[str]:
    """Convert lists of token ids to SMILES strings."""
    return [tokenizer.ids_to_smiles(s) for s in seqs]


def check_validity(smiles_list: list[str]) -> tuple[list[str], float]:
    """Return (valid_smiles, validity_rate) for a list of SMILES strings."""
    valid = [s for s in smiles_list if s and Chem.MolFromSmiles(s) is not None]
    rate  = len(valid) / max(len(smiles_list), 1)
    return valid, rate


def compute_gen_metrics(generated_smiles: list[str],
                        training_set: set[str]) -> dict[str, float]:
    """
    Compute validity, uniqueness, and novelty for a list of generated SMILES.
    Standard MOSES-style metrics.
    """
    valid, validity = check_validity(generated_smiles)
    if not valid:
        return {"validity": 0.0, "uniqueness": 0.0, "novelty": 0.0}

    unique    = list(set(valid))
    novel     = [s for s in unique if s not in training_set]

    return {
        "validity":   validity,
        "uniqueness": len(unique) / len(valid),
        "novelty":    len(novel)  / max(len(unique), 1),
    }


def batch_generate(model: CVAE, n: int, prop_mean: np.ndarray,
                   prop_std: np.ndarray, tokenizer: CVAETokenizer,
                   device: torch.device, cfg: TrainConfig) -> list[str]:
    """
    Generate n SMILES by sampling random z and random property targets.
    Properties are sampled from N(0,1) in normalised space then clipped.
    Returns decoded SMILES strings (may include invalid ones).
    """
    model.eval()
    results: list[list[int]] = []
    batch = 32
    with torch.no_grad():
        for start in range(0, n, batch):
            k    = min(batch, n - start)
            # Sample normalised properties from a mild normal — clip to avoid extremes
            props_norm = torch.clamp(torch.randn(k, NUM_PROPS) * 0.5, -2, 2).to(device)
            seqs = model.generate(
                props_norm, max_len=cfg.max_seq_len, beam_k=1, temperature=1.1
            )
            results.extend(seqs)
    return decode_generated(results, tokenizer)


# ===========================================================================
# Checkpointing
# ===========================================================================

def save_checkpoint(path: Path, model: CVAE, optimizer, scheduler,
                    scaler, epoch: int, val_loss: float,
                    prop_mean: np.ndarray, prop_std: np.ndarray,
                    cfg: TrainConfig, global_step: int = 0) -> None:
    """Save full training state to disk."""
    save_path = str(Path(path).resolve())
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save({
        "epoch":           epoch,
        "global_step":     global_step,
        "model_state":     model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "scheduler_state": scheduler.state_dict(),
        "scaler_state":    scaler.state_dict(),
        "val_loss":        val_loss,
        "prop_mean":       prop_mean,
        "prop_std":        prop_std,
        "config":          asdict(cfg),
    }, save_path)


def load_checkpoint(path: Path, model: CVAE, optimizer,
                    scheduler, scaler, device) -> tuple[int, float, int]:
    """
    Load training state from a checkpoint file.
    Returns (start_epoch, best_val_loss, global_step).
    """
    if not path.exists():
        return 0, float("inf"), 0
    ckpt = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    optimizer.load_state_dict(ckpt["optimizer_state"])
    scheduler.load_state_dict(ckpt["scheduler_state"])
    scaler.load_state_dict(ckpt["scaler_state"])
    global_step = ckpt.get("global_step", 0)
    print(f"[CKPT] Resumed from epoch {ckpt['epoch']}  val_loss={ckpt['val_loss']:.4f}  global_step={global_step}")
    return ckpt["epoch"] + 1, ckpt["val_loss"], global_step


# ===========================================================================
# Step logger (CSV + optional W&B)
# ===========================================================================

class StepLogger:
    """Writes per-step metrics to a CSV file and optionally to W&B."""

    def __init__(self, log_path: Path, wandb_enabled: bool,
                 wandb_project: str, cfg: TrainConfig, resume: bool = False):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Append when resuming so previous rows survive restarts; truncate otherwise.
        append = resume and log_path.exists()
        self._f      = open(log_path, "a" if append else "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._f, fieldnames=[
            "step", "epoch", "loss", "recon_loss", "kl_loss",
            "prop_loss", "perplexity", "validity", "beta", "lr",
        ])
        if not append:
            self._writer.writeheader()
        self._f.flush()

        self._wandb = None
        if wandb_enabled:
            try:
                import wandb
                wandb.init(project=wandb_project, config=asdict(cfg))
                self._wandb = wandb
            except ImportError:
                print("[WARN] wandb not installed — skipping W&B logging.")

    def log_step(self, row: dict) -> None:
        """Write one row of metrics to CSV and optionally to W&B."""
        self._writer.writerow(row)
        self._f.flush()
        if self._wandb:
            self._wandb.log(row, step=row["step"])

    def close(self) -> None:
        self._f.close()
        if self._wandb:
            self._wandb.finish()


# ===========================================================================
# KL annealing
# ===========================================================================

def get_beta(global_step: int, cfg: TrainConfig, steps_per_epoch: int) -> float:
    """Slow step-based KL beta warmup capped at 0.1."""
    # Slow linear beta warmup from step 0 over first 50% of training steps.
    beta_max = 0.1
    total_steps = cfg.epochs * steps_per_epoch
    warmup_steps = total_steps * 0.5
    beta = min(beta_max, (global_step / max(warmup_steps, 1)) * beta_max)
    return beta


# ===========================================================================
# Loss
# ===========================================================================

def compute_cvae_loss(
    recon_logits: torch.Tensor,
    target_tokens: torch.Tensor,
    mu: torch.Tensor,
    log_var: torch.Tensor,
    pred_props: torch.Tensor,
    true_props: torch.Tensor,
    beta: float,
    lambda_prop: float,
    criterion: nn.CrossEntropyLoss,
    kl_free_bits: float,
) -> dict[str, torch.Tensor]:
    """CVAE loss with label-smoothed reconstruction and KL free bits."""
    tgt = target_tokens[:, 1:]
    batch_size, seq_len, vocab_size = recon_logits.shape

    recon_loss = criterion(
        recon_logits.reshape(batch_size * seq_len, vocab_size),
        tgt.reshape(batch_size * seq_len),
    )

    kl_loss = (-0.5 * (1.0 + log_var - mu.pow(2) - log_var.exp())).mean()
    raw_kl_loss = kl_loss
    prop_loss = nn.functional.mse_loss(pred_props, true_props)
    kl_loss = torch.clamp(kl_loss, max=50.0)
    total_loss = recon_loss + beta * kl_loss + lambda_prop * prop_loss

    return {
        "loss": total_loss,
        "recon_loss": recon_loss.detach(),
        "kl_loss": kl_loss.detach(),
        "raw_kl_loss": raw_kl_loss.detach(),
        "prop_loss": prop_loss.detach(),
    }


def build_warmup_flat_scheduler(optimizer, cfg: TrainConfig,
                                steps_per_epoch: int):
    """Step-level LambdaLR: linear warmup, then flat LR."""
    warmup_epochs = cfg.warmup_epochs

    def lr_lambda(current_step: int) -> float:
        warmup_steps = warmup_epochs * steps_per_epoch
        if current_step < warmup_steps:
            return float(current_step) / float(max(1, warmup_steps))
        return 1.0

    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lr_lambda)


def _effective_micro_batch_size(cfg: TrainConfig, device: torch.device) -> int:
    """Limit CPU micro-batches to avoid native PyTorch exits at batch 256."""
    if device.type == "cpu":
        return min(cfg.batch_size, cfg.micro_batch_size)
    return cfg.batch_size


# ===========================================================================
# Training epoch
# ===========================================================================

def train_one_epoch(model: CVAE, loader: DataLoader,
                    optimizer, scheduler, scaler,
                    criterion: nn.CrossEntropyLoss,
                    cfg: TrainConfig, epoch: int,
                    tokenizer: CVAETokenizer,
                    logger: StepLogger,
                    device: torch.device,
                    training_set: set[str],
                    global_step: int,
                    use_amp: bool,
                    steps_per_epoch: int) -> tuple[float, int]:
    """
    One full training epoch.

    Returns (mean_train_loss, updated_global_step).
    Logs every cfg.log_every_n_steps steps.
    """
    model.train()
    total_loss_sum = 0.0
    n_batches      = 0
    consecutive_nan = 0

    pbar = tqdm(loader, desc=f"Epoch {epoch:03d} train", unit="batch", leave=False)
    for batch in pbar:
        beta = get_beta(global_step, cfg, steps_per_epoch)
        tokens = batch["tokens"].to(device)   # [B, L]
        props  = batch["props"].to(device)    # [B, 4]
        full_batch = tokens.size(0)
        micro_batch = _effective_micro_batch_size(cfg, device)

        optimizer.zero_grad(set_to_none=True)

        metric_sums = {
            "loss": 0.0,
            "recon_loss": 0.0,
            "kl_loss": 0.0,
            "raw_kl_loss": 0.0,
            "prop_loss": 0.0,
        }
        skip_batch = False
        stop_epoch_early = False
        for start in range(0, full_batch, micro_batch):
            end = min(start + micro_batch, full_batch)
            weight = (end - start) / full_batch
            mb_tokens = tokens[start:end]
            mb_props = props[start:end]

            with torch.amp.autocast("cuda", enabled=use_amp):
                out  = model(mb_tokens, mb_props)
                loss_dict = compute_cvae_loss(
                    out["recon_logits"], mb_tokens,
                    out["mu"], out["log_var"],
                    out["pred_props"], mb_props,
                    beta=beta, lambda_prop=cfg.lambda_prop,
                    criterion=criterion, kl_free_bits=cfg.kl_free_bits,
                )
                loss = loss_dict["loss"]
                scaled_loss = loss * weight

            if torch.isnan(loss) or torch.isinf(loss):
                consecutive_nan += 1
                print(f"[NaN GUARD] Skipping batch at step {global_step} "
                      f"({consecutive_nan} consecutive)")
                optimizer.zero_grad()
                if consecutive_nan >= 10:
                    print("[NaN GUARD] 10 consecutive NaN batches — stopping epoch early")
                    stop_epoch_early = True
                    break
                skip_batch = True
                break
            scaler.scale(scaled_loss).backward()
            for key in metric_sums:
                metric_sums[key] += float(loss_dict[key].detach()) * weight

        if stop_epoch_early:
            break

        if skip_batch:
            continue

        consecutive_nan = 0  # reset on healthy batch
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=0.5)
        scaler.step(optimizer)
        scaler.update()
        scheduler.step()

        loss_dict = {
            key: torch.tensor(value, device=device)
            for key, value in metric_sums.items()
        }

        total_loss_sum += metric_sums["loss"]
        n_batches      += 1
        global_step    += 1

        pbar.set_postfix({
            "loss":  f"{loss_dict['loss'].item():.3f}",
            "recon": f"{loss_dict['recon_loss'].item():.3f}",
            "kl":    f"{loss_dict['kl_loss'].item():.2f}",
            "beta":  f"{beta:.2f}",
        })

        if global_step % cfg.log_every_n_steps == 0:
            _log_step(model, loss_dict, beta, optimizer, tokenizer,
                      device, cfg, epoch, global_step, training_set, logger)

    return total_loss_sum / max(n_batches, 1), global_step


def _log_step(model: CVAE, loss_dict: dict, beta: float, optimizer,
              tokenizer: CVAETokenizer, device: torch.device,
              cfg: TrainConfig, epoch: int, step: int,
              training_set: set[str], logger: StepLogger) -> None:
    """Generate 32 molecules and log step-level metrics (validity, perplexity)."""
    model.eval()
    with torch.no_grad():
        props_rand = torch.randn(32, NUM_PROPS, device=device) * 0.5
        seqs = model.generate(
            props_rand, max_len=min(cfg.max_seq_len, 64), beam_k=1, temperature=1.1
        )
    decoded  = decode_generated(seqs, tokenizer)
    _, vrate = check_validity(decoded)

    recon = loss_dict["recon_loss"].item()
    raw_kl = loss_dict.get("raw_kl_loss", loss_dict["kl_loss"]).item()
    perp  = math.exp(min(recon, 20))   # cap to avoid overflow display

    lr_now = optimizer.param_groups[0]["lr"]
    row = {
        "step":       step,
        "epoch":      epoch,
        "loss":       round(loss_dict["loss"].item(), 4),
        "recon_loss": round(recon, 4),
        "kl_loss":    round(loss_dict["kl_loss"].item(), 4),
        "prop_loss":  round(loss_dict["prop_loss"].item(), 4),
        "perplexity": round(perp, 2),
        "validity":   round(vrate, 4),
        "beta":       round(beta, 3),
        "lr":         f"{lr_now:.2e}",
    }
    logger.log_step(row)
    if raw_kl > 20:
        global_step = step
        print(f"[KL WARN] kl={raw_kl:.1f} at step {global_step} — clamped to 50")
    print(f"  [step {step:6d}] loss={row['loss']}  recon={row['recon_loss']}"
          f"  kl={row['kl_loss']}  ppl={row['perplexity']:.1f}"
          f"  valid={row['validity']:.1%}  beta={row['beta']}")
    model.train()


# ===========================================================================
# Validation epoch
# ===========================================================================

def validate_epoch(model: CVAE, val_loader: DataLoader,
                   cfg: TrainConfig, epoch: int,
                   tokenizer: CVAETokenizer,
                   criterion: nn.CrossEntropyLoss,
                   device: torch.device,
                   training_set: set[str],
                   prop_mean: np.ndarray,
                   prop_std: np.ndarray,
                   global_step: int,
                   steps_per_epoch: int) -> dict[str, float]:
    """
    Compute validation reconstruction loss, then generate cfg.val_gen_n
    molecules and report validity / uniqueness / novelty.
    Returns a metrics dict.
    """
    model.eval()
    beta     = get_beta(global_step, cfg, steps_per_epoch)
    val_loss = 0.0
    n_batches = 0

    with torch.no_grad():
        for batch in tqdm(val_loader, desc=f"Epoch {epoch:03d}  val",
                          unit="batch", leave=False):
            tokens = batch["tokens"].to(device)
            props  = batch["props"].to(device)
            full_batch = tokens.size(0)
            micro_batch = _effective_micro_batch_size(cfg, device)
            batch_loss = 0.0

            for start in range(0, full_batch, micro_batch):
                end = min(start + micro_batch, full_batch)
                weight = (end - start) / full_batch
                mb_tokens = tokens[start:end]
                mb_props = props[start:end]
                out = model(mb_tokens, mb_props)
                ld = compute_cvae_loss(
                    out["recon_logits"], mb_tokens, out["mu"], out["log_var"],
                    out["pred_props"], mb_props, beta=beta, lambda_prop=cfg.lambda_prop,
                    criterion=criterion, kl_free_bits=cfg.kl_free_bits,
                )
                batch_loss += ld["loss"].item() * weight

            val_loss  += batch_loss
            n_batches += 1

    val_loss /= max(n_batches, 1)

    # Generate cfg.val_gen_n molecules from prior
    print(f"  Generating {cfg.val_gen_n} molecules for validation metrics...")
    gen_smi = batch_generate(model, cfg.val_gen_n, prop_mean, prop_std,
                              tokenizer, device, cfg)
    metrics = compute_gen_metrics(gen_smi, training_set)
    metrics["val_loss"] = val_loss

    return metrics


# ===========================================================================
# Main training loop
# ===========================================================================

def train(cfg: TrainConfig) -> None:
    """Full training run: setup -> loop -> checkpoint -> log."""
    CKPT_DIR = Path(cfg.checkpoint_dir).resolve() if cfg.checkpoint_dir else (_ROOT / "outputs" / "checkpoints").resolve()
    LOG_DIR  = Path(os.environ.get('GENOROVA_LOG_DIR',  'outputs/logs'))
    os.makedirs(CKPT_DIR, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = torch.cuda.is_available()
    print(f"[DEVICE] {device}  |  AMP: {'on' if use_amp else 'off (CPU)'}")

    # Tokenizer
    tokenizer = CVAETokenizer(TOKENIZER_PATH, max_len=cfg.max_seq_len)
    cfg.vocab_size = tokenizer.vocab_size
    print(f"[TOKEN] BPE vocab size: {cfg.vocab_size}")
    criterion = nn.CrossEntropyLoss(
        ignore_index=tokenizer.pad_id,
        label_smoothing=cfg.label_smoothing,
    )
    print(
        f"[LOSS] label_smoothing={cfg.label_smoothing}  "
        f"kl_free_bits={cfg.kl_free_bits}"
    )
    micro_batch = _effective_micro_batch_size(cfg, device)
    if micro_batch < cfg.batch_size:
        print(
            f"[BATCH] effective_batch={cfg.batch_size}  "
            f"micro_batch={micro_batch}  accumulation_steps="
            f"{math.ceil(cfg.batch_size / micro_batch)}"
        )

    # Data
    tr_loader, val_loader, training_set = build_dataloaders(cfg, tokenizer)
    steps_per_epoch = len(tr_loader)
    train_ds = tr_loader.dataset
    prop_mean: np.ndarray = train_ds.prop_mean   # type: ignore[union-attr]
    prop_std:  np.ndarray = train_ds.prop_std    # type: ignore[union-attr]

    # Model
    model = CVAE(vocab_size=cfg.vocab_size, d_model=cfg.d_model,
                 latent_dim=cfg.latent_dim, num_heads=cfg.num_heads,
                 num_layers=cfg.num_layers, dropout=cfg.dropout,
                 max_len=cfg.max_seq_len).to(device)
    if cfg.resume_from and os.path.exists(cfg.resume_from):
        ckpt = torch.load(cfg.resume_from,
                          weights_only=False, map_location='cpu')
        model.load_state_dict(ckpt['model_state'])
        print(f"[RESUME] Loaded weights from {cfg.resume_from}")
        print(f"[RESUME] Previous epoch={ckpt.get('epoch')} "
              f"val_loss={ckpt.get('val_loss'):.4f}")
    print(f"[MODEL] dropout={cfg.dropout}")
    print_model_summary(model)

    # Optimiser + scheduler
    optimizer = torch.optim.AdamW(model.parameters(),
                                  lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = build_warmup_flat_scheduler(optimizer, cfg, steps_per_epoch)
    print(f"[LR] LambdaLR warmup_epochs={cfg.warmup_epochs} flat_after_warmup=True")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)   # enabled=False is no-op on CPU

    # Resume
    start_epoch  = 0
    best_val_loss = float("inf")
    global_step   = 0
    best_ckpt_path = CKPT_DIR / "best.pt"
    if cfg.resume and best_ckpt_path.exists():
        start_epoch, best_val_loss, global_step = load_checkpoint(
            best_ckpt_path, model, optimizer, scheduler, scaler, device)
        print(f"Resuming from epoch {start_epoch}")
    elif cfg.resume:
        print(f"[RESUME] No checkpoint found at {best_ckpt_path} — starting from epoch 0")

    # Logger — append to existing CSV on resume so history survives restarts
    log_path = LOG_DIR / "train_cvae.csv"
    logger   = StepLogger(log_path, cfg.wandb_enabled, cfg.wandb_project, cfg,
                          resume=cfg.resume)
    print(f"[LOG] Step log -> {log_path}")
    print(f"\n[TRAIN] Starting from epoch {start_epoch}, "
          f"running to epoch {cfg.epochs - 1}\n")

    for epoch in range(start_epoch, cfg.epochs):
        t0 = time.time()

        # ── Training ──────────────────────────────────────────────────────
        train_loss, global_step = train_one_epoch(
            model, tr_loader, optimizer, scheduler, scaler, criterion,
            cfg, epoch, tokenizer, logger, device,
            training_set, global_step, use_amp, steps_per_epoch,
        )

        # ── Validation ────────────────────────────────────────────────────
        val_metrics = validate_epoch(
            model, val_loader, cfg, epoch, tokenizer, criterion, device,
            training_set, prop_mean, prop_std, global_step, steps_per_epoch,
        )
        val_loss = val_metrics["val_loss"]
        elapsed  = time.time() - t0

        print(f"\nEpoch {epoch:03d}/{cfg.epochs-1}  "
              f"train={train_loss:.4f}  val={val_loss:.4f}  "
              f"[{elapsed:.0f}s]  "
              f"valid={val_metrics['validity']:.1%}  "
              f"unique={val_metrics['uniqueness']:.1%}  "
              f"novel={val_metrics['novelty']:.1%}\n")

        if cfg.wandb_enabled and logger._wandb:
            logger._wandb.log({"epoch": epoch, **val_metrics}, step=global_step)

        # ── Checkpointing ─────────────────────────────────────────────────
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            save_checkpoint(best_ckpt_path, model, optimizer, scheduler,
                            scaler, epoch, val_loss, prop_mean, prop_std, cfg,
                            global_step=global_step)
            print(f"  [CKPT] New best -> {best_ckpt_path}  (val={val_loss:.4f})")

        if (epoch + 1) % cfg.save_every == 0:
            snap = CKPT_DIR / f"epoch_{epoch + 1:03d}.pt"
            save_checkpoint(snap, model, optimizer, scheduler,
                            scaler, epoch, val_loss, prop_mean, prop_std, cfg,
                            global_step=global_step)
            print(f"  [CKPT] Snapshot -> {snap}")

    logger.close()
    print(f"\n[DONE] Training complete.  Best val loss: {best_val_loss:.4f}")
    print(f"       Best checkpoint: {best_ckpt_path}")


# ===========================================================================
# Entry point
# ===========================================================================

def parse_args() -> TrainConfig:
    """Parse CLI arguments and return a populated TrainConfig."""
    parser = argparse.ArgumentParser(description="Genorova CVAE Training Loop")

    parser.add_argument("--epochs",        type=int,   default=50)
    parser.add_argument("--batch-size",    type=int,   default=256)
    parser.add_argument("--lr",            type=float, default=1e-3)
    parser.add_argument("--latent-dim",    type=int,   default=512)
    parser.add_argument("--d-model",       type=int,   default=256)
    parser.add_argument("--num-workers",   type=int,   default=0)
    parser.add_argument("--label-smoothing", type=float, default=0.1)
    parser.add_argument("--dropout",       type=float, default=0.15)
    parser.add_argument("--grad-clip",     type=float, default=1.0)
    parser.add_argument("--kl-free-bits",  type=float, default=0.5)
    parser.add_argument("--save-every",    type=int,   default=5)
    parser.add_argument("--val-gen-n",     type=int,   default=50)
    parser.add_argument("--max-moses",     type=int,   default=50_000)
    parser.add_argument("--warmup-epochs", type=int,   default=5)
    parser.add_argument("--log-every-n-steps", type=int, default=100,
                        dest="log_every_n_steps")
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Path to training CSV file. If provided, overrides the default data location.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default=None,
        help="Directory to save checkpoints. If provided, overrides the default checkpoint path.",
    )
    parser.add_argument(
        "--resume-from",
        type=str,
        default=None,
        help="Path to checkpoint to resume weights from.",
    )
    parser.add_argument(
        "--include-moses",
        type=lambda x: x.lower() in ("1", "true", "yes"),
        default=False,
        help="Include MOSES dataset in training. Pass True or False.",
    )
    parser.add_argument("--resume",        action="store_true",
                        help="Resume from checkpoints/best.pt")
    parser.add_argument("--wandb",         action="store_true",
                        help="Enable Weights & Biases logging")
    parser.add_argument("--max-rows",      type=int, default=0,
                        help="Cap dataset size (0=all); useful for quick smoke tests")

    a = parser.parse_args()
    data_path = Path(a.data_path).resolve() if a.data_path is not None else None
    if a.checkpoint_dir is not None:
        ckpt_dir = Path(a.checkpoint_dir).resolve()
        os.makedirs(ckpt_dir, exist_ok=True)
    else:
        ckpt_dir = None

    return TrainConfig(
        epochs=a.epochs,
        batch_size=a.batch_size,
        lr=a.lr,
        latent_dim=a.latent_dim,
        d_model=a.d_model,
        num_workers=a.num_workers,
        label_smoothing=a.label_smoothing,
        dropout=a.dropout,
        grad_clip=a.grad_clip,
        kl_free_bits=a.kl_free_bits,
        save_every=a.save_every,
        val_gen_n=a.val_gen_n,
        max_moses_rows=a.max_moses,
        data_path=str(data_path) if data_path is not None else None,
        warmup_epochs=a.warmup_epochs,
        log_every_n_steps=a.log_every_n_steps,
        include_moses=a.include_moses,
        resume=a.resume,
        resume_from=a.resume_from,
        checkpoint_dir=str(ckpt_dir) if ckpt_dir is not None else None,
        wandb_enabled=a.wandb,
        max_rows=a.max_rows,
    )


def main() -> None:
    cfg = parse_args()
    train(cfg)


if __name__ == "__main__":
    main()
