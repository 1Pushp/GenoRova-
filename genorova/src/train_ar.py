"""
Genorova AI -- Autoregressive VAE Training  (train_ar.py)
==========================================================

HOW TO RUN
----------
    # From genorova/src/  (the usual working directory):
    python train_ar.py

    # With custom settings:
    python train_ar.py --dataset moses --epochs 100 --batch-size 256
    python train_ar.py --dataset moses --epochs 100 --checkpoint path/to/resume.pt

WHAT THIS DOES
--------------
Trains the SMILESVAE (autoregressive GRU decoder) defined in model_ar.py
on the MOSES benchmark dataset.  The training loop is intentionally close
to the one in train.py so you can compare runs.

Key differences from train.py (which trains model.VAE):
  1. Model:   SMILESVAE (model_ar.py) instead of VAE (model.py)
  2. Forward: model(x) returns (logits, mu, logvar) -- 3 values not 3
  3. Loss:    CrossEntropy on shifted sequence, not position-independent BCE
  4. Sanity:  autoregressive generation (via model.generate()) not decode()

Everything else is shared:
  - Same data pipeline (data_loader.load_smiles_dataset)
  - Same vocabulary / preprocessor utilities
  - Same checkpoint format (adds model_type="SMILESVAE_AR")
  - Same KL annealing schedule
  - Same early stopping and LR decay
  - Same generation sanity check every N epochs

COMPARING AGAINST OLD BASELINE
-------------------------------
After training, run evaluate_generation.py pointing at the new checkpoint:

    python evaluate_generation.py \\
        --checkpoint ../outputs/models/ar/smilesvae_ar_best.pt \\
        --n 1000 --output ../outputs/evaluation/ar_eval

Then compare against the old diabetes finetune checkpoint:

    python evaluate_generation.py \\
        --checkpoint ../outputs/models/diabetes/genorova_diabetes_finetune_best.pt \\
        --n 1000 --output ../outputs/evaluation/baseline_eval

Compare the evaluation_metrics.json files for validity, uniqueness, novelty.

AUTHOR  : Claude Code  (Genorova AI Sprint 2)
DATE    : April 2026
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Any

import numpy as np
import pandas as pd
import torch
import torch.optim as optim
from torch.utils.data import DataLoader, random_split

# ── project imports ──────────────────────────────────────────────────────────
from data_loader import load_smiles_dataset
from model_ar import (
    SMILESVAE,
    HIDDEN_DIM,
    NUM_GRU_LAYERS,
    EMBED_DIM,
    DEFAULT_MIN_GENERATION_LENGTH,
)
from preprocessor import (
    MAX_SMILES_LENGTH as DEFAULT_MAX_LENGTH,
    SmilesDataset,
    build_vocab,
    decode_token_ids,
    get_special_token_ids,
    preprocess_batch,
    save_vocab,
    select_token_ids_from_logits,
)

# ── paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR   = PROJECT_ROOT / "outputs"
DEFAULT_MODEL_DIR = OUTPUT_DIR / "models" / "ar"
DEFAULT_LOG_DIR   = OUTPUT_DIR / "logs"
DEFAULT_VOCAB_PATH = OUTPUT_DIR / "vocab_ar.json"

DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── training hyperparameters ─────────────────────────────────────────────────
EPOCHS          = 100
BATCH_SIZE      = 256
LEARNING_RATE   = 1e-3
LR_DECAY        = 0.95
LR_DECAY_EVERY  = 10
GRADIENT_CLIP   = 1.0
CHECKPOINT_EVERY = 10
EARLY_STOPPING_PATIENCE = 10
TRAIN_SPLIT     = 0.90
SEED            = 42

# KL annealing: linear warmup from 0 to KL_WEIGHT_TARGET over KL_WARMUP_EPOCHS
KL_WEIGHT_TARGET  = 0.5
KL_WARMUP_EPOCHS  = 50   # effectively stretched to max(50, epochs//2) at runtime

# Sanity check: generate a handful of SMILES every N epochs and log validity
SANITY_EVERY   = 5
SANITY_SAMPLES = 16
SANITY_TOP_K   = 5
SANITY_TEMPERATURE = 0.3

# DataLoader workers (0 = main process, safest on Windows)
NUM_WORKERS = 0


# ============================================================================
# REPRODUCIBILITY
# ============================================================================

def set_seed(seed: int = SEED) -> None:
    """Fix all random seeds for reproducible training runs."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ============================================================================
# LOGGING
# ============================================================================

def setup_logger(log_dir: Path = DEFAULT_LOG_DIR) -> Tuple[logging.Logger, Path]:
    """
    Create a logger that writes to both stdout and a timestamped log file.

    Returns:
        (logger, log_file_path)
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = log_dir / f"train_ar_{timestamp}.log"

    logger = logging.getLogger("genorova.train_ar")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh  = logging.FileHandler(log_file)
    sh  = logging.StreamHandler()
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False

    return logger, log_file


def _safe_run_name(run_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(run_name).strip())
    return cleaned.strip("._-") or "ar_run"


def _resolve_run_paths(run_name: str | None) -> tuple[Path, Path, Path, str]:
    normalized = (run_name or "").strip()
    if not normalized or normalized.lower() in {"ar", "default"}:
        model_dir = DEFAULT_MODEL_DIR
        log_dir = DEFAULT_LOG_DIR
        vocab_path = DEFAULT_VOCAB_PATH
        run_label = "ar"
    else:
        run_label = _safe_run_name(normalized)
        model_dir = OUTPUT_DIR / "models" / "ar" / run_label
        log_dir = OUTPUT_DIR / "logs" / "ar" / run_label
        vocab_path = model_dir / "vocab.json"

    model_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return model_dir, log_dir, vocab_path, run_label


# ============================================================================
# CHECKPOINT SAVE / LOAD
# ============================================================================

def save_checkpoint(
    model: SMILESVAE,
    optimizer: optim.Optimizer,
    epoch: int,
    val_loss: float,
    char2idx: dict,
    max_length: int,
    filename: str = "checkpoint.pt",
    model_dir: Path = DEFAULT_MODEL_DIR,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """
    Save a SMILESVAE checkpoint.

    The checkpoint dict includes model_type="SMILESVAE_AR" so that
    evaluate_generation.py can load it with the correct model class.
    """
    path = model_dir / filename
    payload = {
        "model_type":        SMILESVAE.MODEL_TYPE,
        "epoch":             epoch,
        "model_state":       model.state_dict(),
        "optimizer_state":   optimizer.state_dict(),
        "val_loss":          val_loss,
        "best_val_loss":     val_loss,
        "vocab_size":        len(char2idx),
        "max_length":        max_length,
        "latent_dim":        model.latent_dim,
        "hidden_dim":        model.decoder.hidden_dim,
        "num_gru_layers":    model.decoder.num_layers,
        "embed_dim":         model.decoder.embed_dim,
    }
    if metadata:
        payload.update(metadata)
    torch.save(payload, path)
    return path


def load_checkpoint(
    checkpoint_path: Path,
    model: SMILESVAE,
    optimizer: optim.Optimizer,
    device: torch.device,
) -> Tuple[int, float]:
    """
    Resume training from a SMILESVAE checkpoint.

    Returns:
        (start_epoch, best_val_loss)
    """
    ckpt = torch.load(checkpoint_path, map_location=device)
    if ckpt.get("model_type") != SMILESVAE.MODEL_TYPE:
        raise ValueError(
            f"Checkpoint model_type={ckpt.get('model_type')!r} does not match "
            f"SMILESVAE_AR. Cannot resume with a different model class."
        )
    model.load_state_dict(ckpt["model_state"])
    optimizer.load_state_dict(ckpt["optimizer_state"])
    return ckpt["epoch"] + 1, ckpt.get("best_val_loss", float("inf"))


# ============================================================================
# SINGLE EPOCH HELPERS
# ============================================================================

def train_epoch(
    model: SMILESVAE,
    loader: DataLoader,
    optimizer: optim.Optimizer,
    kl_weight: float,
    device: torch.device,
    logger: logging.Logger,
    epoch: int,
    log_interval: int = 50,
) -> Dict[str, float]:
    """
    Run one training epoch with teacher forcing.

    Returns:
        dict with keys: loss, recon_loss, kl_loss
    """
    model.train()
    total_loss = recon_total = kl_total = 0.0
    n_batches  = 0

    for batch_idx, x in enumerate(loader):
        x = x.to(device)

        optimizer.zero_grad()

        # Forward pass: one-hot → (logits, mu, logvar) via teacher forcing
        logits, mu, logvar = model(x)

        # Loss: CrossEntropy reconstruction + KL divergence
        loss, recon_loss, kl_loss = model.loss_function(
            logits, x, mu, logvar, kl_weight=kl_weight
        )

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRADIENT_CLIP)
        optimizer.step()

        total_loss  += loss.item()
        recon_total += recon_loss.item()
        kl_total    += kl_loss.item()
        n_batches   += 1

        if (batch_idx + 1) % log_interval == 0:
            logger.info(
                "Epoch %d  batch %d/%d  loss=%.4f recon=%.4f kl=%.4f",
                epoch + 1, batch_idx + 1, len(loader),
                loss.item(), recon_loss.item(), kl_loss.item(),
            )

    n = max(n_batches, 1)
    return {
        "loss":       total_loss  / n,
        "recon_loss": recon_total / n,
        "kl_loss":    kl_total    / n,
    }


def validate_epoch(
    model: SMILESVAE,
    loader: DataLoader,
    kl_weight: float,
    device: torch.device,
) -> Dict[str, float]:
    """
    Run the validation loop (no gradient updates).

    Returns:
        dict with keys: val_loss, val_recon_loss, val_kl_loss
    """
    model.eval()
    total_loss = recon_total = kl_total = 0.0
    n_batches  = 0

    with torch.no_grad():
        for x in loader:
            x = x.to(device)
            logits, mu, logvar = model(x)
            loss, recon_loss, kl_loss = model.loss_function(
                logits, x, mu, logvar, kl_weight=kl_weight
            )
            total_loss  += loss.item()
            recon_total += recon_loss.item()
            kl_total    += kl_loss.item()
            n_batches   += 1

    n = max(n_batches, 1)
    return {
        "val_loss":       total_loss  / n,
        "val_recon_loss": recon_total / n,
        "val_kl_loss":    kl_total    / n,
    }


# ============================================================================
# GENERATION SANITY CHECK
# ============================================================================

def generation_sanity_check(
    model: SMILESVAE,
    char2idx: dict,
    idx2char: dict,
    device: torch.device,
    n_samples: int = SANITY_SAMPLES,
    temperature: float = SANITY_TEMPERATURE,
    top_k: int = SANITY_TOP_K,
    min_generation_length: int = DEFAULT_MIN_GENERATION_LENGTH,
) -> Dict:
    """
    Generate a small batch of SMILES and measure basic validity.

    This runs every SANITY_EVERY epochs so you can catch early if the
    redesigned model is still generating garbage.

    Returns a dict with validity_pct, valid_count, sample_smiles.
    """
    try:
        from rdkit import Chem as _Chem
        from rdkit import RDLogger as _RL
        _RL.DisableLog("rdApp.*")
        rdkit_ok = True
    except Exception:
        _Chem  = None
        rdkit_ok = False

    special = get_special_token_ids(char2idx)
    bos_idx = special["bos"] if special["bos"] is not None else 1
    eos_idx = special["eos"] if special["eos"] is not None else 2
    pad_idx = special["pad"] if special["pad"] is not None else 0

    model.eval()
    with torch.no_grad():
        token_ids = model.generate(
            num_molecules=n_samples,
            bos_idx=bos_idx,
            eos_idx=eos_idx,
            pad_idx=pad_idx,
            temperature=temperature,
            top_k=top_k,
            min_generation_length=min_generation_length,
            device=device,
        )  # [n_samples, max_len]

    decoded = [
        decode_token_ids(seq, idx2char, char2idx=char2idx)
        for seq in token_ids
    ]

    valid_count = 0
    valid_lengths = []
    for row in decoded:
        smi = row["raw_smiles"]
        if not smi:
            continue
        if rdkit_ok:
            mol = _Chem.MolFromSmiles(smi)
            if mol is not None and mol.GetNumAtoms() > 1:
                valid_count += 1
                valid_lengths.append(row["raw_length"])
        else:
            if len(smi) > 2:
                valid_count += 1
                valid_lengths.append(row["raw_length"])

    sample_smiles = [row["raw_smiles"] for row in decoded[:8]]
    validity_pct  = round(100.0 * valid_count / max(1, len(decoded)), 2)
    raw_lengths = [row["raw_length"] for row in decoded if row["raw_smiles"]]

    return {
        "validity_pct":   validity_pct,
        "valid_count":    valid_count,
        "sample_count":   len(decoded),
        "sample_smiles":  sample_smiles,
        "missing_eos":    sum(
            1 for row in decoded
            if row["first_eos_position"] is None and "<eos>" in char2idx
        ),
        "mean_length": round(float(np.mean(raw_lengths)), 4) if raw_lengths else None,
        "mean_valid_length": round(float(np.mean(valid_lengths)), 4) if valid_lengths else None,
        "top_k": int(top_k),
        "temperature": float(temperature),
        "min_generation_length": int(min_generation_length),
    }


# ============================================================================
# MAIN TRAINING FUNCTION
# ============================================================================

def train_autoregressive(
    dataset_name: str  = "moses",
    epochs: int        = EPOCHS,
    batch_size: int    = BATCH_SIZE,
    learning_rate: float = LEARNING_RATE,
    max_samples: int   = 50_000,
    min_len: int       = 10,
    max_len: int       = 100,
    resume_from: str   = None,
    hidden_dim: int    = HIDDEN_DIM,
    num_gru_layers: int = NUM_GRU_LAYERS,
    embed_dim: int     = EMBED_DIM,
    run_name: str | None = None,
    min_generation_length: int = DEFAULT_MIN_GENERATION_LENGTH,
    sanity_temperature: float = SANITY_TEMPERATURE,
    sanity_top_k: int = SANITY_TOP_K,
) -> Path:
    """
    Train the SMILESVAE autoregressive model on a real molecular dataset.

    Args:
        dataset_name : "moses" or a path to a CSV with a "smiles" column
        epochs       : total training epochs
        batch_size   : molecules per gradient step
        learning_rate: Adam LR
        max_samples  : cap on number of training molecules
        min_len      : discard SMILES shorter than this
        max_len      : discard SMILES longer than this
        resume_from  : path to checkpoint to resume from

    Returns:
        Path to the best checkpoint file.
    """
    set_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_dir, log_dir, vocab_path, run_label = _resolve_run_paths(run_name)
    logger, log_file = setup_logger(log_dir)

    logger.info("=" * 60)
    logger.info("Genorova AR VAE Training")
    logger.info("dataset=%s  epochs=%d  batch=%d  device=%s",
                dataset_name, epochs, batch_size, device)
    logger.info(
        "run=%s  hidden=%d  layers=%d  embed=%d  min_generation_length=%d",
        run_label,
        hidden_dim,
        num_gru_layers,
        embed_dim,
        min_generation_length,
    )
    logger.info("=" * 60)

    # ── Load data ────────────────────────────────────────────────────────────
    logger.info("Loading dataset: %s (max_samples=%d)", dataset_name, max_samples)
    df = load_smiles_dataset(
        name=dataset_name,
        max_samples=max_samples,
        min_len=min_len,
        max_len=max_len,
    )
    assert len(df) >= 1_000, (
        f"Only {len(df)} molecules loaded — dataset too small for meaningful "
        f"training. Check that data/moses/train.csv exists and is readable."
    )
    logger.info("Loaded %d molecules.", len(df))

    # ── Vocabulary ───────────────────────────────────────────────────────────
    smiles_list = df["smiles"].tolist()
    char2idx, idx2char = build_vocab(smiles_list)
    save_vocab(char2idx, vocab_path)
    logger.info("Vocabulary size: %d", len(char2idx))
    logger.info("Vocabulary saved to %s", vocab_path)

    # ── Encoding ─────────────────────────────────────────────────────────────
    observed_max = int(df["smiles"].str.len().max())
    # Use max_len cap + BOS/EOS headroom; fall back to DEFAULT_MAX_LENGTH if larger
    model_max_length = max(max_len + 2, observed_max + 2)  # +2 for BOS+EOS
    logger.info(
        "SMILES length: max_observed=%d  model_max_length=%d",
        observed_max, model_max_length,
    )

    logger.info("Encoding %d SMILES to one-hot (this may take a moment)...", len(smiles_list))
    encoded = preprocess_batch(smiles_list, char2idx, max_length=model_max_length)
    dataset = SmilesDataset(encoded, smiles_list)

    # ── Train / val split ────────────────────────────────────────────────────
    train_size = max(1, int(TRAIN_SPLIT * len(dataset)))
    val_size   = len(dataset) - train_size
    if val_size == 0:
        val_size = 1
        train_size -= 1

    train_set, val_set = random_split(
        dataset, [train_size, val_size],
        generator=torch.Generator().manual_seed(SEED),
    )
    logger.info("Split: train=%d  val=%d", train_size, val_size)

    train_loader = DataLoader(
        train_set, batch_size=batch_size, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        val_set, batch_size=batch_size, shuffle=False,
        num_workers=NUM_WORKERS,
    )

    # ── Model ────────────────────────────────────────────────────────────────
    model = SMILESVAE(
        vocab_size=len(char2idx),
        max_length=model_max_length,
        hidden_dim=hidden_dim,
        num_gru_layers=num_gru_layers,
        embed_dim=embed_dim,
    ).to(device)
    model.set_special_tokens(char2idx)
    logger.info("Model parameters: %d", model.count_parameters())

    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.StepLR(
        optimizer, step_size=LR_DECAY_EVERY, gamma=LR_DECAY
    )

    # ── Optionally resume ────────────────────────────────────────────────────
    start_epoch    = 0
    best_val_loss  = float("inf")
    patience       = 0

    if resume_from:
        resume_path = Path(resume_from)
        if resume_path.exists():
            start_epoch, best_val_loss = load_checkpoint(
                resume_path, model, optimizer, device
            )
            logger.info(
                "Resumed from %s (epoch %d, best_val_loss=%.4f)",
                resume_path, start_epoch, best_val_loss,
            )
        else:
            logger.warning("resume_from path %s not found — starting fresh.", resume_from)

    best_ckpt_path = model_dir / "smilesvae_ar_best.pt"
    sanity_log     = log_dir / "train_ar_sanity.jsonl"
    if sanity_log.exists():
        sanity_log.unlink()

    all_metrics: list[dict] = []
    kl_warmup_epochs = max(KL_WARMUP_EPOCHS, epochs // 2)
    checkpoint_metadata = {
        "vocab_path": str(vocab_path),
        "dataset_name": dataset_name,
        "max_samples": int(max_samples),
        "min_smiles_length": int(min_len),
        "max_smiles_length": int(max_len),
        "run_name": run_label,
        "min_generation_length": int(min_generation_length),
        "sanity_temperature": float(sanity_temperature),
        "sanity_top_k": int(sanity_top_k),
    }

    # ── Training loop ────────────────────────────────────────────────────────
    for epoch in range(start_epoch, epochs):
        # Linear KL warmup: 0 at epoch 0, KL_WEIGHT_TARGET at epoch kl_warmup_epochs
        kl_weight = min(
            KL_WEIGHT_TARGET,
            KL_WEIGHT_TARGET * epoch / max(1, kl_warmup_epochs),
        )

        t0 = time.time()
        train_m = train_epoch(
            model, train_loader, optimizer, kl_weight, device, logger, epoch
        )
        val_m   = validate_epoch(model, val_loader, kl_weight, device)
        dt      = time.time() - t0

        scheduler.step()

        # Sanity generation check
        sanity_m = None
        if epoch == 0 or (epoch + 1) % SANITY_EVERY == 0 or (epoch + 1) == epochs:
            sanity_m = generation_sanity_check(
                model,
                char2idx,
                idx2char,
                device,
                temperature=sanity_temperature,
                top_k=sanity_top_k,
                min_generation_length=min_generation_length,
            )
            with open(sanity_log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"epoch": epoch + 1, **sanity_m}) + "\n")

        logger.info(
            "Epoch %d/%d | train=%.4f recon=%.4f kl=%.4f | val=%.4f | "
            "kl_w=%.3f | lr=%.6f | %.1fs%s",
            epoch + 1, epochs,
            train_m["loss"], train_m["recon_loss"], train_m["kl_loss"],
            val_m["val_loss"],
            kl_weight,
            optimizer.param_groups[0]["lr"],
            dt,
            f" | sanity={sanity_m['validity_pct']:.1f}%" if sanity_m else "",
        )
        if sanity_m:
            logger.info("  sample SMILES: %s", sanity_m["sample_smiles"])

        # Save periodic checkpoint
        if (epoch + 1) % CHECKPOINT_EVERY == 0:
            ckpt = save_checkpoint(
                model, optimizer, epoch, val_m["val_loss"], char2idx,
                model_max_length,
                filename=f"smilesvae_ar_epoch{epoch + 1}.pt",
                model_dir=model_dir,
                metadata=checkpoint_metadata,
            )
            logger.info("Saved checkpoint: %s", ckpt)

        # Save best model
        if val_m["val_loss"] < best_val_loss:
            best_val_loss = val_m["val_loss"]
            patience      = 0
            save_checkpoint(
                model, optimizer, epoch, best_val_loss, char2idx,
                model_max_length,
                filename="smilesvae_ar_best.pt",
                model_dir=model_dir,
                metadata=checkpoint_metadata,
            )
            logger.info("New best val_loss=%.4f — saved best checkpoint.", best_val_loss)
        else:
            patience += 1
            if patience >= EARLY_STOPPING_PATIENCE:
                logger.info(
                    "Early stopping after %d epochs without improvement.", patience
                )
                break

        # Record metrics
        row = {
            "epoch":            epoch + 1,
            "kl_weight":        kl_weight,
            "lr":               optimizer.param_groups[0]["lr"],
            "epoch_seconds":    dt,
            "sanity_validity":  sanity_m["validity_pct"] if sanity_m else None,
            "sanity_mean_length": sanity_m["mean_length"] if sanity_m else None,
            "sanity_mean_valid_length": sanity_m["mean_valid_length"] if sanity_m else None,
            **train_m,
            **val_m,
        }
        all_metrics.append(row)

    # ── Save metrics CSV ─────────────────────────────────────────────────────
    metrics_csv = log_dir / "train_ar_metrics.csv"
    pd.DataFrame(all_metrics).to_csv(metrics_csv, index=False)
    logger.info("Metrics saved to %s", metrics_csv)

    # Save final checkpoint
    save_checkpoint(
        model, optimizer, epoch, val_m["val_loss"], char2idx,
        model_max_length,
        filename="smilesvae_ar_final.pt",
        model_dir=model_dir,
        metadata=checkpoint_metadata,
    )

    logger.info("=" * 60)
    logger.info("Training complete. Best val_loss=%.4f", best_val_loss)
    logger.info("Best checkpoint: %s", best_ckpt_path)
    logger.info("Run vocab path: %s", vocab_path)
    logger.info("=" * 60)

    return best_ckpt_path


# ============================================================================
# CLI
# ============================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Train Genorova SMILESVAE (autoregressive decoder)"
    )
    p.add_argument("--dataset",     default="moses",
                   help="Dataset name ('moses') or path to CSV with 'smiles' column")
    p.add_argument("--epochs",      type=int,   default=EPOCHS)
    p.add_argument("--batch-size",  type=int,   default=BATCH_SIZE)
    p.add_argument("--lr",          type=float, default=LEARNING_RATE,
                   dest="learning_rate")
    p.add_argument("--max-samples", type=int,   default=50_000,
                   dest="max_samples")
    p.add_argument("--max-len",     type=int,   default=100,
                   dest="max_len")
    p.add_argument("--checkpoint",  default=None,
                   help="Path to SMILESVAE_AR checkpoint to resume from")
    p.add_argument("--hidden-dim",  type=int,   default=HIDDEN_DIM,
                   dest="hidden_dim",
                   help="GRU hidden state size (default: 512; use 256 for CPU speed)")
    p.add_argument("--num-layers",  type=int,   default=NUM_GRU_LAYERS,
                   dest="num_gru_layers",
                   help="Number of stacked GRU layers (default: 2; use 1 for CPU speed)")
    p.add_argument("--embed-dim",   type=int,   default=EMBED_DIM,
                   dest="embed_dim",
                   help="Token embedding dimension (default: 128)")
    p.add_argument("--run-name", default=None,
                   help="Optional run name. Saves checkpoints under outputs/models/ar/<run-name>/ and saves the matching vocab beside them.")
    p.add_argument("--min-generation-length", type=int, default=DEFAULT_MIN_GENERATION_LENGTH,
                   dest="min_generation_length",
                   help="Minimum number of generated tokens before EOS is allowed during AR sanity generation and recommended inference.")
    p.add_argument("--sanity-temperature", type=float, default=SANITY_TEMPERATURE,
                   dest="sanity_temperature",
                   help="Sampling temperature used for train-time AR sanity generation.")
    p.add_argument("--sanity-top-k", type=int, default=SANITY_TOP_K,
                   dest="sanity_top_k",
                   help="Top-k token filtering used for train-time AR sanity generation.")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    best = train_autoregressive(
        dataset_name  = args.dataset,
        epochs        = args.epochs,
        batch_size    = args.batch_size,
        learning_rate = args.learning_rate,
        max_samples   = args.max_samples,
        max_len       = args.max_len,
        resume_from   = args.checkpoint,
        hidden_dim    = args.hidden_dim,
        num_gru_layers= args.num_gru_layers,
        embed_dim     = args.embed_dim,
        run_name      = args.run_name,
        min_generation_length = args.min_generation_length,
        sanity_temperature = args.sanity_temperature,
        sanity_top_k = args.sanity_top_k,
    )
    print(f"\nBest checkpoint saved to: {best}")
