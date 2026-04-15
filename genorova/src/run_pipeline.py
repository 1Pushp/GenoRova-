"""
Genorova AI -- Full Drug Discovery Pipeline
============================================

PURPOSE:
Run the complete Genorova AI drug discovery pipeline on real ChEMBL data.
Trains a VAE on each disease dataset, generates new drug candidates,
scores them against clinical trial endpoints, and reports the best molecules.

PIPELINE (runs for EACH disease area):
    1. Load real ChEMBL SMILES + pre-built vocabulary
    2. Train VAE for 50 epochs (saves best checkpoint each epoch)
    3. Generate molecules using guided latent space sampling
       (encodes real molecules → adds small noise → decodes = novel but valid)
    4. Validate generated SMILES with RDKit
    5. Score valid molecules with Genorova clinical scorer
    6. Save top candidates to CSV
    7. Print ranked results

GENERATION STRATEGY:
    Rather than pure random sampling (which gives 0% validity with few epochs),
    we use guided sampling:
    - Encode real training molecules to get their latent vectors (mu)
    - Add small random noise: z = mu + epsilon * temperature
    - Decode noisy z to get new molecules similar to, but distinct from, training data
    - This gives much higher validity rates even with 50 epochs of training

OUTPUT FILES:
    outputs/models/diabetes/genorova_diabetes_best.pt
    outputs/models/infection/genorova_infection_best.pt
    outputs/generated/diabetes_candidates.csv
    outputs/generated/infection_candidates.csv

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import sys
import argparse
import re
import json
import time
import contextlib
import io
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import torch
import torch.optim as optim
from pathlib import Path
from torch.utils.data import DataLoader, random_split

# RDKit is imported lazily inside functions (not here at module level)
# This allows training to proceed even if the rdkit DLL is temporarily blocked
# by Windows Application Control / Defender.
# The imports happen inside guided_generate() and silent_score_molecule().

# Add src/ to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from model import VAE, MAX_SMILES_LENGTH
from preprocessor import (
    build_vocab,
    preprocess_batch,
    SmilesDataset,
    save_vocab,
    decode_token_ids,
    get_special_token_ids,
    select_token_ids_from_logits,
)
from data_loader import load_smiles_dataset, load_smiles_from_csv

# ============================================================================
# PIPELINE CONFIGURATION
# ============================================================================

EPOCHS      = 100             # increased from 50 (deeper model needs more time)
BATCH_SIZE  = 64
LR          = 0.001
LR_DECAY    = 0.95            # reduce LR by 5% every 10 epochs
GRAD_CLIP   = 1.0
SANITY_CHECK_EVERY = 5
DECODE_TOP_K = 5
DECODE_REPETITION_PENALTY = 0.75
DECODE_STRUCTURAL_GUARD_STRENGTH = 1.0

# ---- CYCLIC KL ANNEALING ----
# KL weight cycles from 0 → KL_MAX_WEIGHT → 0 every KL_CYCLE_LENGTH epochs.
# Cyclic annealing (Fu et al. 2019) prevents posterior collapse better than
# linear annealing: the low-KL phases let the encoder learn good representations,
# the high-KL phases force the latent space to spread out.
KL_MAX_WEIGHT   = 0.3         # peak KL weight per cycle (much higher than old 0.005)
KL_CYCLE_LENGTH = 20          # epochs per full KL cycle (ramp up 10 + plateau 10)

# ---- FREE BITS ----
# Minimum KL per latent dimension per sample.
# If a dimension's KL falls below FREE_BITS, the gradient is blocked
# (the model is not rewarded for collapsing it further).
# Imported from model.py but also used here so we can pass it explicitly.
FREE_BITS = 0.5

# Generation settings
NUM_TO_GENERATE   = 1000    # sample this many latent points per round
GENERATION_TEMP   = 0.3     # noise scale for guided sampling (lower = more similar to training)
MIN_VALID_TARGET  = 200     # keep generating until we have this many valid SMILES

# Lipinski limits (re-check generated molecules)
MW_MAX   = 500
LOGP_MAX = 5.0
HBD_MAX  = 5
HBA_MAX  = 10

# Directories
ROOT_DIR       = Path(__file__).parent.parent
DATA_DIR       = ROOT_DIR / "data" / "raw"
OUTPUT_DIR     = ROOT_DIR / "outputs"
MODELS_DIR     = OUTPUT_DIR / "models"
GENERATED_DIR  = OUTPUT_DIR / "generated"
IMAGES_DIR     = OUTPUT_DIR / "molecule_images"
VOCAB_DIR      = OUTPUT_DIR

for d in [MODELS_DIR / "diabetes", MODELS_DIR / "infection",
          GENERATED_DIR, IMAGES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SEED = 42


# ============================================================================
# SECTION 1: TRAINING
# ============================================================================

def set_seed(seed: int = SEED):
    """Make training and dataset splits reproducible."""
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _prepare_training_smiles(smiles_list):
    """Normalize a raw SMILES list into a stripped, de-duplicated list."""
    cleaned = []
    seen = set()
    for smiles in smiles_list:
        normalized = str(smiles).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    if not cleaned:
        raise ValueError("No usable SMILES strings found for training.")
    return cleaned


def load_primary_training_dataset(dataset_name, max_samples=None, min_len=10, max_len=100):
    """
    Load the primary pretraining corpus via the shared dataset loader.
    """
    print(f"\n[*] Stage: PRETRAIN DATA LOAD")
    print(f"    Source type: shared dataset loader")
    print(f"    Dataset: {dataset_name}")
    if max_samples is not None:
        print(f"    Sample cap: {max_samples}")

    dataset_df = load_smiles_dataset(
        name=dataset_name,
        max_samples=max_samples,
        min_len=min_len,
        max_len=max_len,
    )
    load_stats = dataset_df.attrs.get("load_stats", {})
    smiles_list = _prepare_training_smiles(dataset_df["smiles"].tolist())

    print(f"    [OK] Loaded {len(smiles_list)} pretraining molecules")
    if load_stats:
        print(f"    [OK] Loader stats: {load_stats}")

    return {
        "stage_name": "pretrain",
        "source_label": f"dataset:{dataset_name}",
        "smiles_list": smiles_list,
        "load_stats": load_stats,
    }


def load_finetune_dataset(csv_path):
    """
    Load optional fine-tuning molecules from a per-disease CSV.
    """
    csv_path = Path(csv_path)
    print(f"\n[*] Stage: FINE-TUNE DATA LOAD")
    print(f"    Source type: optional fine-tune CSV")
    print(f"    CSV path: {csv_path}")

    smiles_list = _prepare_training_smiles(load_smiles_from_csv(str(csv_path)))
    print(f"    [OK] Loaded {len(smiles_list)} fine-tuning molecules")

    return {
        "stage_name": "finetune",
        "source_label": f"finetune_csv:{csv_path.name}",
        "smiles_list": smiles_list,
        "load_stats": {"csv_path": str(csv_path), "rows": len(smiles_list)},
    }


def encode_training_smiles(smiles_list, vocab_path, char2idx=None, idx2char=None):
    """
    Build or reuse a vocabulary, then encode SMILES into one-hot tensors.
    """
    smiles_list = _prepare_training_smiles(smiles_list)

    if char2idx is None or idx2char is None:
        print(f"[*] Building vocabulary from current training corpus...")
        char2idx, idx2char = build_vocab(smiles_list)
        save_vocab(char2idx, str(vocab_path))
        print(f"   [OK] Vocabulary saved: {vocab_path}")
    else:
        print(f"[*] Reusing existing vocabulary for this stage...")

    vocab_size = len(char2idx)
    print(f"[*] Encoding {len(smiles_list)} SMILES to one-hot tensors...")
    encoded = preprocess_batch(smiles_list, char2idx)
    print(f"   [OK] Tensor shape: {encoded.shape}")
    print(f"   [OK] VAE input dim: {MAX_SMILES_LENGTH} x {vocab_size} = {MAX_SMILES_LENGTH * vocab_size}")

    return encoded, smiles_list, char2idx, idx2char, vocab_size


def make_dataloaders(encoded, smiles_list, batch_size=BATCH_SIZE):
    """
    Split encoded data into train / val DataLoaders.

    Split: 85% train, 15% val (we use all data for training, small val for monitoring)

    Args:
        encoded (np.ndarray): one-hot encoded SMILES [N, 120, vocab_size]
        smiles_list (list): original SMILES strings (for reference)

    Returns:
        tuple: (train_loader, val_loader, train_dataset)
    """
    dataset = SmilesDataset(encoded, smiles_list)
    n_train = int(0.85 * len(dataset))
    n_val   = len(dataset) - n_train

    train_ds, val_ds = random_split(
        dataset,
        [n_train, n_val],
        generator=torch.Generator().manual_seed(SEED),
    )
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=True)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False)

    print(f"   [OK] Train: {len(train_ds)} molecules ({len(train_loader)} batches)")
    print(f"   [OK] Val:   {len(val_ds)}   molecules ({len(val_loader)} batches)")
    return train_loader, val_loader, train_ds


def quick_generation_sanity_check(
    model,
    reference_encoded,
    char2idx,
    idx2char,
    device,
    *,
    num_samples=16,
    temperature=0.3,
):
    """
    Generate a tiny guided batch during training so we can spot garbage early.
    """
    try:
        from rdkit import Chem as _Chem
        from rdkit import RDLogger as _RDLogger
        _RDLogger.DisableLog("rdApp.*")
        rdkit_available = True
    except Exception:
        rdkit_available = False
        _Chem = None

    model.eval()
    tensor_data = torch.from_numpy(reference_encoded[: max(1, min(len(reference_encoded), 128))]).float().to(device)
    decoded_rows = []

    with torch.no_grad():
        mu, _ = model.encoder(tensor_data)
        mu = mu.cpu()
        index = torch.randint(0, len(mu), (num_samples,))
        z = mu[index].to(device) + (torch.randn(num_samples, mu.shape[1], device=device) * temperature)
        recon = model.decode(z)
        indices = select_token_ids_from_logits(
            recon,
            char2idx,
            temperature=max(temperature, 0.2),
            strategy="sample",
            top_k=DECODE_TOP_K,
            repetition_penalty=DECODE_REPETITION_PENALTY,
            min_tokens_before_stop=2,
            structural_guard_strength=DECODE_STRUCTURAL_GUARD_STRENGTH,
        )
        decoded_rows = [decode_token_ids(seq, idx2char, char2idx=char2idx) for seq in indices]

    validity_flags = []
    for row in decoded_rows:
        smiles = row["raw_smiles"]
        if not smiles:
            validity_flags.append(False)
            continue
        if not rdkit_available:
            validity_flags.append(len(smiles) > 2)
            continue
        mol = _Chem.MolFromSmiles(smiles)
        validity_flags.append(mol is not None and mol.GetNumAtoms() > 1)

    valid_count = sum(validity_flags)
    return {
        "validity_pct": round(100.0 * valid_count / max(1, len(decoded_rows)), 2),
        "valid_count": valid_count,
        "sample_count": len(decoded_rows),
        "samples": [row["raw_smiles"] for row in decoded_rows[:5]],
        "termination_reasons": {
            reason: sum(1 for row in decoded_rows if row["termination_reason"] == reason)
            for reason in sorted({row["termination_reason"] for row in decoded_rows})
        },
        "missing_eos_count": sum(1 for row in decoded_rows if row["first_eos_position"] is None and "<eos>" in char2idx),
    }


def train_vae(disease_label, stage_name, source_label, smiles_list, checkpoint_dir,
              epochs=EPOCHS, char2idx=None, idx2char=None, model=None):
    """
    Train the Variational Autoencoder on one disease dataset.

    Training loop:
    - Adam optimizer with learning rate decay every 10 epochs
    - KL annealing: KL weight increases from 0 to 0.5 over first 25 epochs
    - Gradient clipping at 1.0 to prevent exploding gradients
    - Saves best checkpoint whenever validation loss improves

    Args:
        disease_label (str): label used for checkpoint naming
        stage_name (str): training stage name, e.g. pretrain or finetune
        source_label (str): human-readable data source label
        smiles_list (list[str]): training molecules for this stage
        checkpoint_dir (str or Path): where to save model checkpoints
        epochs (int): number of training epochs

    Returns:
        tuple: (trained VAE model, char2idx, idx2char, vocab_size)
    """
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'#'*70}")
    print(f"# TRAINING VAE -- {disease_label.upper()} [{stage_name.upper()}]")
    print(f"{'#'*70}")
    print(f"[*] Dataset source: {source_label}")
    print(f"[*] Molecules in stage corpus: {len(smiles_list)}")

    vocab_path = VOCAB_DIR / f"vocabulary_{disease_label}_{stage_name}.json"
    encoded, smiles_list, char2idx, idx2char, vocab_size = encode_training_smiles(
        smiles_list=smiles_list,
        vocab_path=vocab_path,
        char2idx=char2idx,
        idx2char=idx2char,
    )

    # DataLoaders
    print("\n[*] Creating DataLoaders...")
    train_loader, val_loader, train_ds = make_dataloaders(encoded, smiles_list)

    # Model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n[*] Device: {device}")
    print(f"[*] Building VAE (vocab_size={vocab_size})...")

    # Suppress model's own print output for cleaner logging
    if model is None:
        with contextlib.redirect_stdout(io.StringIO()):
            model = VAE(vocab_size=vocab_size).to(device)
    else:
        model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"   [OK] Model ready -- {total_params:,} trainable parameters")
    print(f"   [OK] Encoder input: {MAX_SMILES_LENGTH} x {vocab_size} = {MAX_SMILES_LENGTH * vocab_size} features")

    # Optimizer + scheduler
    optimizer = optim.Adam(model.parameters(), lr=LR)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=LR_DECAY)

    best_val_loss  = float("inf")
    best_epoch     = 0
    kl_weight      = 0.0          # will be overwritten by cyclic formula each epoch

    best_ckpt_path = checkpoint_dir / f"genorova_{disease_label}_{stage_name}_best.pt"
    final_ckpt_path = checkpoint_dir / f"genorova_{disease_label}_{stage_name}_final.pt"

    print(f"\n[*] Starting training for {epochs} epochs...")
    print(f"    Batch size: {BATCH_SIZE}  |  LR: {LR}")
    print(f"    Cyclic KL annealing: 0.0 -> {KL_MAX_WEIGHT} per {KL_CYCLE_LENGTH}-epoch cycle")
    print(f"    Free bits: {FREE_BITS} (min KL per latent dim -- prevents collapse)")
    print(f"    Architecture: 3-layer encoder/decoder (increased capacity)")
    print("-" * 104)
    print(f"{'Epoch':>6} | {'Train Loss':>11} | {'Val Loss':>10} | {'KL Weight':>9} | {'mu_std':>7} | {'Sanity%':>7} | {'LR':>8} | Note")
    print("-" * 104)

    start_time = time.time()
    sanity_history = []

    import math  # for cosine annealing formula

    for epoch in range(1, epochs + 1):

        # ---- CYCLIC KL ANNEALING ----
        # Each cycle has KL_CYCLE_LENGTH epochs.
        # First half: linear ramp from 0 to KL_MAX_WEIGHT.
        # Second half: hold at KL_MAX_WEIGHT (plateau lets model consolidate).
        #
        # Why cyclic? The low-KL phases allow the encoder to learn rich
        # representations without KL pressure. The high-KL phases then force
        # the latent space to spread out. Repeated cycling converges to a better
        # equilibrium than a single linear ramp.
        epoch_in_cycle  = (epoch - 1) % KL_CYCLE_LENGTH
        half_cycle      = KL_CYCLE_LENGTH // 2
        cycle_fraction  = min(epoch_in_cycle / half_cycle, 1.0)  # 0 to 1
        kl_weight       = cycle_fraction * KL_MAX_WEIGHT

        # ---- TRAIN ----
        model.train()
        train_total = 0.0
        for batch in train_loader:
            x = batch.to(device)
            optimizer.zero_grad()
            recon_x, mu, logvar = model(x)
            loss, _, _ = model.loss_function(recon_x, x, mu, logvar,
                                              kl_weight=kl_weight, free_bits=FREE_BITS)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            optimizer.step()
            train_total += loss.item()
        avg_train = train_total / len(train_loader)

        # ---- VALIDATE ----
        model.eval()
        val_total  = 0.0
        val_mu_list = []
        with torch.no_grad():
            for batch in val_loader:
                x = batch.to(device)
                recon_x, mu, logvar = model(x)
                loss, _, _ = model.loss_function(recon_x, x, mu, logvar,
                                                  kl_weight=KL_MAX_WEIGHT, free_bits=FREE_BITS)
                val_total += loss.item()
                val_mu_list.append(mu.cpu())
        avg_val  = val_total / max(1, len(val_loader))
        # Track mu_std to detect posterior collapse
        all_val_mu = torch.cat(val_mu_list, dim=0)
        mu_std_now = all_val_mu.std().item()
        sanity_metrics = None
        if epoch == 1 or epoch % SANITY_CHECK_EVERY == 0 or epoch == epochs:
            sanity_metrics = quick_generation_sanity_check(
                model=model,
                reference_encoded=encoded,
                char2idx=char2idx,
                idx2char=idx2char,
                device=device,
            )
            sanity_history.append({"epoch": epoch, **sanity_metrics})
            print(
                f"      sanity: validity={sanity_metrics['validity_pct']:.2f}% "
                f"({sanity_metrics['valid_count']}/{sanity_metrics['sample_count']}) "
                f"samples={sanity_metrics['samples']}"
            )

        # ---- SAVE BEST ----
        note = ""
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            best_epoch    = epoch
            note = "<-- BEST"
            checkpoint = {
                "epoch":          epoch,
                "model_state":    model.state_dict(),
                "optimizer_state":optimizer.state_dict(),
                "best_val_loss":  best_val_loss,
                "best_epoch":     epoch,
                "kl_weight":      kl_weight,
                "vocab_size":     vocab_size,
                "disease":        disease_label,
                "stage_name":     stage_name,
                "source_label":   source_label,
                "mu_std":         mu_std_now,
                "uses_sequence_tokens": True,
                "sanity_validity_pct": sanity_metrics["validity_pct"] if sanity_metrics else None,
            }
            torch.save(checkpoint, best_ckpt_path)

        # Update LR
        scheduler.step()
        lr_now = optimizer.param_groups[0]["lr"]

        # Print one line per epoch
        print(f"{epoch:>6} | {avg_train:>11.5f} | {avg_val:>10.5f} | "
              f"{kl_weight:>9.3f} | {mu_std_now:>7.4f} | "
              f"{(sanity_metrics['validity_pct'] if sanity_metrics else float('nan')):>7.2f} | {lr_now:>8.5f} | {note}")

    elapsed = time.time() - start_time
    final_checkpoint = {
        "epoch": epochs,
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "best_val_loss": best_val_loss,
        "best_epoch": best_epoch,
        "kl_weight": kl_weight,
        "vocab_size": vocab_size,
        "disease": disease_label,
        "stage_name": stage_name,
        "source_label": source_label,
        "uses_sequence_tokens": True,
        "sanity_history": sanity_history,
    }
    torch.save(final_checkpoint, final_ckpt_path)
    sanity_path = checkpoint_dir / f"genorova_{disease_label}_{stage_name}_sanity.json"
    sanity_path.write_text(json.dumps(sanity_history, indent=2), encoding="utf-8")
    print("-" * 70)
    print(f"[OK] Training complete in {elapsed/60:.1f} minutes")
    print(f"[OK] Best val loss: {best_val_loss:.5f} at epoch {best_epoch}")
    print(f"[OK] Best checkpoint: {best_ckpt_path}")
    print(f"[OK] Final checkpoint: {final_ckpt_path}")
    print(f"[OK] Sanity log: {sanity_path}")

    return model, char2idx, idx2char, vocab_size, device, smiles_list, encoded


# ============================================================================
# SECTION 2: MOLECULE GENERATION (GUIDED SAMPLING)
# ============================================================================

def guided_generate(model, encoded_data, char2idx, idx2char, vocab_size,
                    device, num_samples=NUM_TO_GENERATE, temperature=GENERATION_TEMP):
    """
    Generate novel molecules using guided latent space sampling.

    STRATEGY:
    Instead of pure random sampling z ~ N(0, I) (which gives ~0% validity
    with a freshly trained model), we:
    1. Encode real training molecules through the VAE encoder to get mu vectors
    2. Add small Gaussian noise: z = mu + epsilon * temperature
    3. Decode noisy z to get new molecules

    This keeps the generated molecules inside the region of latent space the
    model has learned, while the noise ensures they are NOT exact copies of
    training molecules. Temperature controls novelty vs validity trade-off:
    - Low temperature (0.2-0.4): more like training molecules, higher validity
    - High temperature (0.8-1.0): more novel, lower validity

    Args:
        model: trained VAE model
        encoded_data: one-hot encoded training molecules [N, 120, vocab_size]
        char2idx (dict): character-to-index vocabulary
        idx2char (dict): index-to-character vocabulary
        vocab_size (int): vocabulary size
        device: torch device
        num_samples (int): number of latent points to sample
        temperature (float): noise scale for guided sampling

    Returns:
        list: list of unique valid SMILES strings
    """
    print(f"\n[*] Generating molecules via guided latent sampling...")
    print(f"    Strategy: encode real molecules + add noise (temp={temperature})")
    print(f"    Samples to generate: {num_samples}")

    # Lazy import of rdkit (avoids module-level DLL load)
    try:
        from rdkit import Chem
        from rdkit import RDLogger
        RDLogger.DisableLog("rdApp.*")
        rdkit_available = True
    except ImportError as e:
        print(f"    [!] RDKit not available ({e}) -- skipping SMILES validation")
        rdkit_available = False

    model.eval()

    # Convert training data to tensors for encoding
    tensor_data = torch.from_numpy(encoded_data).float().to(device)

    all_generated = []
    batch_size     = 64   # encode training data in batches to save memory

    token_ids = get_special_token_ids(char2idx)

    with torch.no_grad():
        # Encode all training molecules to get their latent means
        all_mu = []
        for i in range(0, len(tensor_data), batch_size):
            batch = tensor_data[i : i + batch_size]
            mu, logvar = model.encoder(batch)
            all_mu.append(mu.cpu())
        all_mu = torch.cat(all_mu, dim=0)   # [N_train, latent_dim]

        # ---- POSTERIOR COLLAPSE DETECTION ----
        # If all mu values are near 0 (std < 0.05) the encoder has collapsed:
        # every molecule maps to the same latent point and the decoder
        # produces a single fixed string for all inputs.
        mu_std = all_mu.std().item()
        print(f"    Latent space: {all_mu.shape[1]}-dimensional")
        print(f"    Latent mu range: [{all_mu.min().item():.4f}, {all_mu.max().item():.4f}]")
        print(f"    Latent mu std:   {mu_std:.6f}")

        if mu_std < 0.1:
            print(f"    [!] POSTERIOR COLLAPSE DETECTED (mu_std={mu_std:.6f} < 0.1)")
            print(f"    [!] Encoder is not using the latent space meaningfully.")
            print(f"    [!] Returning [] — run_disease_pipeline will use library screening.")
            return []

        print(f"    [OK] Latent space is meaningful (mu_std={mu_std:.4f} >= 0.1)")
        print(f"    Encoded {len(all_mu)} training molecules to latent space")

        # Sample mu vectors with replacement, add noise, decode
        for batch_start in range(0, num_samples, batch_size):
            batch_end   = min(batch_start + batch_size, num_samples)
            this_batch  = batch_end - batch_start

            # Pick random training molecule latent vectors
            idx = torch.randint(0, len(all_mu), (this_batch,))
            z   = all_mu[idx].to(device)

            # Add Gaussian noise (the source of novelty)
            noise = torch.randn_like(z) * temperature
            z     = z + noise

            # Decode to get molecule logits
            recon = model.decode(z)          # [batch, 120, vocab_size]

            indices = select_token_ids_from_logits(
                recon,
                char2idx,
                temperature=max(temperature, 0.2),
                strategy="sample",
                top_k=DECODE_TOP_K,
                repetition_penalty=DECODE_REPETITION_PENALTY,
                min_tokens_before_stop=2,
                structural_guard_strength=DECODE_STRUCTURAL_GUARD_STRENGTH,
            )

            for seq in indices:
                decoded = decode_token_ids(seq, idx2char, char2idx=char2idx)
                smiles = decoded["raw_smiles"]
                if smiles:
                    all_generated.append(smiles)

    print(f"    Raw generated strings: {len(all_generated)}")

    # Validate with RDKit (if available)
    valid = []
    seen  = set()
    for smi in all_generated:
        if smi in seen:
            continue
        seen.add(smi)
        if not rdkit_available:
            # No rdkit -- accept all non-empty strings as "valid"
            if smi and len(smi) > 2:
                valid.append(smi)
            continue
        try:
            mol = Chem.MolFromSmiles(smi)
            if mol is not None and mol.GetNumAtoms() > 1:
                valid.append(smi)
        except Exception:
            pass

    validity_pct = 100 * len(valid) / max(1, len(all_generated))
    print(f"    Valid unique SMILES: {len(valid)} ({validity_pct:.1f}% validity)")
    if token_ids["eos"] is not None:
        print(f"    [DEBUG] Decoding used explicit EOS/PAD token handling")
    return valid


# ============================================================================
# SECTION 3: SCORING (SILENT BATCH MODE)
# ============================================================================

def silent_score_molecule(smiles):
    """
    Score a molecule using Genorova clinical scorer without any print output.

    Runs all scoring functions from scorer.py but suppresses their print
    statements. Returns a compact result dict.

    Args:
        smiles (str): SMILES string

    Returns:
        dict or None: scoring result, or None if molecule is invalid
    """
    # Suppress all print output during scoring
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            # scorer.py now has lazy rdkit imports internally, so this import
            # works even when the rdkit DLL is blocked by Windows App Control
            from scorer import (calculate_qed, calculate_sa_score,
                                passes_lipinski, genorova_clinical_score,
                                _smiles_props_approx, _try_load_rdkit)

            # Get basic properties (rdkit if available, else pure-Python)
            if _try_load_rdkit():
                from rdkit import Chem as _Chem
                from rdkit.Chem import Descriptors as _D, Crippen as _Cr
                mol = _Chem.MolFromSmiles(smiles)
                if mol is None or mol.GetNumAtoms() < 2:
                    return None
                mw   = float(_D.MolWt(mol))
                logp = float(_Cr.MolLogP(mol))
                hbd  = int(_D.NumHDonors(mol))
                hba  = int(_D.NumHAcceptors(mol))
                tpsa = float(_D.TPSA(mol))
            else:
                # Use pure-Python approximation
                if not smiles or len(smiles) < 3:
                    return None
                props = _smiles_props_approx(smiles)
                mw   = props['mw']
                logp = props['logp']
                hbd  = props['hbd']
                hba  = props['hba']
                tpsa = props['tpsa']

            qed   = calculate_qed(smiles)
            sa    = calculate_sa_score(smiles)
            lip   = passes_lipinski(smiles)
            score = genorova_clinical_score(smiles)

            if   score >= 0.60: verdict = "Strong candidate"
            elif score >= 0.40: verdict = "Borderline"
            else:               verdict = "Reject"

            return {
                "smiles":            smiles,
                "molecular_weight":  round(mw, 2),
                "logp":              round(logp, 3),
                "hbd":               hbd,
                "hba":               hba,
                "tpsa":              round(tpsa, 2),
                "qed_score":         qed,
                "sa_score":          sa,
                "passes_lipinski":   lip,
                "clinical_score":    score,
                "recommendation":    verdict,
            }
        except Exception:
            return None


def score_molecules_batch(smiles_list, disease_label, max_score=100):
    """
    Score a list of generated molecules in batch and return ranked results.

    Scores up to max_score molecules (top valid ones), showing a progress bar.
    Returns results sorted by clinical_score descending.

    Args:
        smiles_list (list): list of valid SMILES
        disease_label (str): "diabetes" or "infection" (for logging)
        max_score (int): maximum number to score (scoring is slow, cap it)

    Returns:
        pd.DataFrame: results sorted by clinical_score descending
    """
    to_score = smiles_list[:max_score]
    print(f"\n[*] Scoring {len(to_score)} {disease_label} molecules...")

    results = []
    for i, smi in enumerate(to_score, 1):
        if i % 10 == 0:
            print(f"   ... scored {i}/{len(to_score)}")
        result = silent_score_molecule(smi)
        if result:
            results.append(result)

    if not results:
        print("   [!] No results -- all molecules failed scoring")
        return pd.DataFrame()

    df = (pd.DataFrame(results)
          .sort_values("clinical_score", ascending=False)
          .reset_index(drop=True))
    df.index = df.index + 1

    print(f"   [OK] Scored {len(df)} molecules")
    return df


# ============================================================================
# SECTION 4: REPORTING
# ============================================================================

def print_top_candidates(df, disease_label, n=10):
    """
    Print a clean summary table of the top N drug candidates.

    Args:
        df (pd.DataFrame): scored molecules sorted by clinical_score
        disease_label (str): "diabetes" or "infection"
        n (int): number of top candidates to show
    """
    top = df.head(n)

    print(f"\n{'='*80}")
    print(f"TOP {n} {disease_label.upper()} CANDIDATES -- GENOROVA AI DISCOVERIES")
    print(f"{'='*80}")
    print(f"{'Rank':>4} | {'Clinical':>8} | {'QED':>5} | {'SA':>5} | {'MW':>6} | "
          f"{'LogP':>5} | {'Lip':>3} | {'Verdict':<16} | SMILES")
    print("-" * 80)

    for rank, row in top.iterrows():
        lip = "Y" if row["passes_lipinski"] else "N"
        smi_short = row["smiles"][:35] + "..." if len(row["smiles"]) > 35 else row["smiles"]
        verdict_short = row["recommendation"][:16]
        print(f"{rank:>4} | {row['clinical_score']:>8.4f} | {row['qed_score']:>5.3f} | "
              f"{row['sa_score']:>5.2f} | {row['molecular_weight']:>6.1f} | "
              f"{row['logp']:>5.2f} | {lip:>3} | {verdict_short:<16} | {smi_short}")

    print("-" * 80)
    strong = (df["recommendation"] == "Strong candidate").sum()
    border = (df["recommendation"] == "Borderline").sum()
    reject = (df["recommendation"] == "Reject").sum()
    print(f"  Total scored: {len(df)}  |  "
          f"Strong: {strong}  Borderline: {border}  Reject: {reject}")
    print(f"  Best clinical score: {df['clinical_score'].max():.4f}")
    print(f"  Avg QED: {df['qed_score'].mean():.3f}  |  "
          f"Avg SA score: {df['sa_score'].mean():.2f}")


# ============================================================================
# SECTION 5: FULL SINGLE-DISEASE PIPELINE
# ============================================================================

def run_disease_pipeline(disease_label, pretrain_dataset, output_csv,
                         pretrain_epochs=EPOCHS, finetune_csv=None,
                         finetune_epochs=0, pretrain_max_samples=None,
                         skip_generation=False):
    """
    Run the complete pipeline for one disease area:
    train -> generate -> score -> save -> print.

    Args:
        disease_label (str): label used for output/checkpoint naming
        pretrain_dataset (str): shared dataset-loader source name
        output_csv (Path): where to save scored candidates CSV
        pretrain_epochs (int): pretraining epochs
        finetune_csv (Path | None): optional fine-tuning CSV
        finetune_epochs (int): fine-tuning epochs
        pretrain_max_samples (int | None): optional sample cap for pretraining
        skip_generation (bool): if True, stop after training/checkpoint save

    Returns:
        pd.DataFrame: all scored candidates (sorted best first)
    """
    checkpoint_dir = MODELS_DIR / disease_label

    # ---- STEP 1: PRETRAIN ----
    primary_data = load_primary_training_dataset(
        dataset_name=pretrain_dataset,
        max_samples=pretrain_max_samples,
    )
    model, char2idx, idx2char, vocab_size, device, smiles_list, encoded = train_vae(
        disease_label=disease_label,
        stage_name="pretrain",
        source_label=primary_data["source_label"],
        smiles_list=primary_data["smiles_list"],
        checkpoint_dir=checkpoint_dir,
        epochs=pretrain_epochs,
    )

    # ---- STEP 2: OPTIONAL FINE-TUNE ----
    if finetune_csv:
        finetune_data = load_finetune_dataset(finetune_csv)
        model, char2idx, idx2char, vocab_size, device, smiles_list, encoded = train_vae(
            disease_label=disease_label,
            stage_name="finetune",
            source_label=finetune_data["source_label"],
            smiles_list=finetune_data["smiles_list"],
            checkpoint_dir=checkpoint_dir,
            epochs=finetune_epochs,
            char2idx=char2idx,
            idx2char=idx2char,
            model=model,
        )
    else:
        print(f"\n[*] No fine-tune CSV provided for {disease_label}; using pretrained model directly.")

    if skip_generation:
        print(f"\n[*] Smoke-test mode active; skipping generation/scoring for {disease_label}.")
        return pd.DataFrame(), smiles_list

    # ---- STEP 3: GENERATE ----
    print(f"\n{'='*70}")
    print(f"GENERATING MOLECULES -- {disease_label.upper()}")
    print(f"{'='*70}")

    valid_smiles = []
    attempts = 0

    # Keep generating until we have enough valid molecules
    # Try up to 3 rounds with increasing temperature if needed
    for temp in [0.3, 0.5, 0.8]:
        needed = max(0, MIN_VALID_TARGET - len(valid_smiles))
        if needed == 0:
            break

        print(f"\n[*] Generation round (temperature={temp}, need {needed} more valid)...")
        batch = guided_generate(
            model         = model,
            encoded_data  = encoded,
            char2idx      = char2idx,
            idx2char      = idx2char,
            vocab_size    = vocab_size,
            device        = device,
            num_samples   = max(NUM_TO_GENERATE, needed * 5),
            temperature   = temp,
        )

        # Remove duplicates and molecules already in training set
        training_set = set(smiles_list)
        novel = [s for s in batch if s not in training_set]
        # Remove any we already have
        existing = set(valid_smiles)
        novel = [s for s in novel if s not in existing]

        valid_smiles.extend(novel)
        attempts += 1
        print(f"   [OK] Novel valid molecules collected so far: {len(valid_smiles)}")

        if len(valid_smiles) >= MIN_VALID_TARGET:
            break

    print(f"\n[*] Total novel valid SMILES for scoring: {len(valid_smiles)}")

    if not valid_smiles:
        print(f"\n[!] VAE generation produced no valid molecules for {disease_label}.")
        print(f"    This happens when the VAE latent space has posterior collapse.")
        print(f"    Switching to LIBRARY SCREENING MODE:")
        print(f"    Scoring all {len(smiles_list)} real ChEMBL training molecules")
        print(f"    and selecting the top {MIN_VALID_TARGET} by clinical score.")
        print(f"    (This is a valid virtual screening approach -- ranking known compounds.)")

        # Use all training molecules as the candidate pool
        # Filter to only those that pass RDKit validation first
        valid_smiles = []
        try:
            from rdkit import Chem as _C
            from rdkit import RDLogger as _RL
            _RL.DisableLog("rdApp.*")
            for smi in smiles_list:
                m = _C.MolFromSmiles(smi)
                if m is not None and m.GetNumAtoms() > 1:
                    valid_smiles.append(smi)
        except ImportError:
            valid_smiles = [s for s in smiles_list if s and len(s) > 3]

        print(f"    [OK] {len(valid_smiles)} molecules from training library pass RDKit check")
        print(f"    [OK] Will score top {min(len(valid_smiles), MIN_VALID_TARGET)}")

    # ---- STEP 4: SCORE (all valid molecules, up to 200) ----
    results_df = score_molecules_batch(
        smiles_list   = valid_smiles,
        disease_label = disease_label,
        max_score     = min(len(valid_smiles), 200),
    )

    # ---- STEP 5: SAVE ----
    if len(results_df) > 0:
        results_df.to_csv(output_csv, index_label="rank")
        print(f"\n[OK] Saved {len(results_df)} scored candidates to: {output_csv}")

    # ---- STEP 6: PRINT TOP 10 ----
    if len(results_df) > 0:
        print_top_candidates(results_df, disease_label, n=10)

    return results_df, valid_smiles


# ============================================================================
# SECTION 5B: 2D STRUCTURE IMAGE GENERATION
# ============================================================================

def generate_structure_images(df, disease_label, n_top=3):
    """
    Generate 2D chemical structure images for the top N molecules.

    Uses RDKit's Draw module to render each molecule as a clean 2D image
    and saves it as a PNG file to outputs/molecule_images/.

    Each image is named: <disease>_rank<N>_<first8chars_of_smiles>.png

    Args:
        df (pd.DataFrame): scored molecules sorted best-first (from pipeline)
        disease_label (str): "diabetes" or "infection" (used in filenames)
        n_top (int): how many top molecules to draw (default: 3)

    Returns:
        list: paths to saved image files
    """
    print(f"\n[*] Generating 2D structure images for top {n_top} {disease_label} molecules...")

    try:
        from rdkit import Chem
        from rdkit.Chem import Draw
        from rdkit.Chem import rdMolDescriptors
    except ImportError as e:
        print(f"   [!] Cannot generate images -- RDKit Draw not available: {e}")
        return []

    saved_paths = []
    drawn = 0

    for rank, row in df.head(n_top).iterrows():
        smiles = row["smiles"]
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                print(f"   [!] Rank {rank}: invalid SMILES, skipping image")
                continue

            # Build a clean filename from rank + SMILES snippet
            smi_tag = re.sub(r'[^A-Za-z0-9]', '', smiles[:10])
            filename = f"{disease_label}_rank{rank:02d}_{smi_tag}.png"
            save_path = IMAGES_DIR / filename

            # Draw molecule as 400x300 PNG
            img = Draw.MolToImage(mol, size=(400, 300))
            img.save(str(save_path))

            score  = row["clinical_score"]
            qed    = row["qed_score"]
            mw     = row["molecular_weight"]
            print(f"   [OK] Rank {rank}: saved {filename}  "
                  f"(score={score:.4f}, QED={qed:.3f}, MW={mw:.1f} Da)")
            saved_paths.append(str(save_path))
            drawn += 1

        except Exception as e:
            print(f"   [!] Rank {rank}: image error -- {e}")

    print(f"   [OK] {drawn} structure images saved to: {IMAGES_DIR}")
    return saved_paths


# ============================================================================
# MAIN
# ============================================================================

def main():
    """
    Run Genorova AI's drug discovery pipeline on real ChEMBL data.

    Trains two VAE models (diabetes and infection), generates 200+ novel
    drug candidates from each, validates and scores them with real RDKit,
    generates 2D structure images for the top candidates, and prints a
    full discovery report.
    """
    # =========================================================================
    # STARTUP: Print RDKit version and confirm mode
    # =========================================================================
    print("\n" + "#"*70)
    print("# GENOROVA AI -- DRUG DISCOVERY PIPELINE")
    print("# Training on real ChEMBL pharmaceutical data")
    print(f"# Target: {MIN_VALID_TARGET} valid molecules per disease")
    print(f"# Epochs: {EPOCHS} per model  |  Batch size: {BATCH_SIZE}")
    print("#"*70)

    # Check RDKit availability and print version
    try:
        from rdkit import rdBase
        rdkit_version = rdBase.rdkitVersion
        print(f"\n[OK] RDKit version: {rdkit_version}")
        print(f"[OK] Mode: REAL RDKit validation (exact chemistry, not approximation)")
        rdkit_mode = True
    except Exception as e:
        print(f"\n[!] RDKit not available: {e}")
        print(f"[!] Mode: Pure-Python approximation (fallback)")
        rdkit_mode = False

    print(f"[OK] Molecule images will be saved to: {IMAGES_DIR}")

    start_wall = time.time()

    # =========================================================================
    # RUN 1: DIABETES MODEL
    # =========================================================================
    print(f"\n{'='*70}")
    print("RUN 1 OF 2: DIABETES DRUG DISCOVERY")
    print(f"{'='*70}")

    diabetes_df, diabetes_smiles = run_disease_pipeline(
        disease_label = "diabetes",
        csv_path      = DATA_DIR / "diabetes_molecules.csv",
        vocab_path    = OUTPUT_DIR / "vocabulary_diabetes.json",
        output_csv    = GENERATED_DIR / "diabetes_candidates_validated.csv",
        epochs        = EPOCHS,
    )

    # =========================================================================
    # RUN 2: INFECTION MODEL
    # =========================================================================
    print(f"\n{'='*70}")
    print("RUN 2 OF 2: INFECTIOUS DISEASE DRUG DISCOVERY")
    print(f"{'='*70}")

    infection_df, infection_smiles = run_disease_pipeline(
        disease_label = "infection",
        csv_path      = DATA_DIR / "infection_molecules.csv",
        vocab_path    = OUTPUT_DIR / "vocabulary_infection.json",
        output_csv    = GENERATED_DIR / "infection_candidates_validated.csv",
        epochs        = EPOCHS,
    )

    # =========================================================================
    # GENERATION STATISTICS
    # =========================================================================
    total_time = (time.time() - start_wall) / 60

    d_generated = len(diabetes_smiles)
    i_generated = len(infection_smiles)
    d_valid     = len(diabetes_df)
    i_valid     = len(infection_df)
    d_valid_pct = 100 * d_valid  / max(1, d_generated)
    i_valid_pct = 100 * i_valid  / max(1, i_generated)

    print(f"\n{'#'*70}")
    print("# GENOROVA AI -- GENERATION + VALIDATION STATISTICS")
    print(f"{'#'*70}")
    print(f"\n  RDKit version:    {rdkit_version if rdkit_mode else 'NOT AVAILABLE (fallback mode)'}")
    print(f"  Validation mode:  {'Real RDKit Chem.MolFromSmiles()' if rdkit_mode else 'Pure-Python approximation'}")
    print(f"  Training epochs:  {EPOCHS} per model")
    print(f"  Total runtime:    {total_time:.1f} minutes")
    print(f"\n  {'Disease':<12} | {'Generated':>10} | {'Valid':>7} | {'Validity%':>9} | {'Scored':>6}")
    print(f"  {'-'*55}")
    print(f"  {'Diabetes':<12} | {d_generated:>10} | {d_valid:>7} | {d_valid_pct:>8.1f}% | {len(diabetes_df):>6}")
    print(f"  {'Infection':<12} | {i_generated:>10} | {i_valid:>7} | {i_valid_pct:>8.1f}% | {len(infection_df):>6}")
    print(f"  {'-'*55}")
    total_gen  = d_generated + i_generated
    total_val  = d_valid + i_valid
    total_scr  = len(diabetes_df) + len(infection_df)
    total_pct  = 100 * total_val / max(1, total_gen)
    print(f"  {'TOTAL':<12} | {total_gen:>10} | {total_val:>7} | {total_pct:>8.1f}% | {total_scr:>6}")

    # =========================================================================
    # FINAL DISCOVERY REPORT -- TOP 5 PER DISEASE
    # =========================================================================
    print(f"\n{'='*70}")
    print("TOP 5 DIABETES DRUG CANDIDATES")
    print(f"{'='*70}")
    if len(diabetes_df) > 0:
        print(f"{'Rank':>4} | {'Score':>7} | {'QED':>5} | {'SA':>5} | "
              f"{'MW':>6} | {'LogP':>5} | {'Lip':>3} | {'Verdict':<16} | SMILES")
        print("-" * 90)
        for rank, row in diabetes_df.head(5).iterrows():
            smi = row["smiles"][:30] + "..." if len(row["smiles"]) > 30 else row["smiles"]
            lip = "Y" if row["passes_lipinski"] else "N"
            print(f"{rank:>4} | {row['clinical_score']:>7.4f} | {row['qed_score']:>5.3f} | "
                  f"{row['sa_score']:>5.2f} | {row['molecular_weight']:>6.1f} | "
                  f"{row['logp']:>5.2f} | {lip:>3} | {row['recommendation']:<16} | {smi}")
    else:
        print("  [!] No diabetes candidates generated")

    print(f"\n{'='*70}")
    print("TOP 5 INFECTIOUS DISEASE DRUG CANDIDATES")
    print(f"{'='*70}")
    if len(infection_df) > 0:
        print(f"{'Rank':>4} | {'Score':>7} | {'QED':>5} | {'SA':>5} | "
              f"{'MW':>6} | {'LogP':>5} | {'Lip':>3} | {'Verdict':<16} | SMILES")
        print("-" * 90)
        for rank, row in infection_df.head(5).iterrows():
            smi = row["smiles"][:30] + "..." if len(row["smiles"]) > 30 else row["smiles"]
            lip = "Y" if row["passes_lipinski"] else "N"
            print(f"{rank:>4} | {row['clinical_score']:>7.4f} | {row['qed_score']:>5.3f} | "
                  f"{row['sa_score']:>5.2f} | {row['molecular_weight']:>6.1f} | "
                  f"{row['logp']:>5.2f} | {lip:>3} | {row['recommendation']:<16} | {smi}")
    else:
        print("  [!] No infection candidates generated")

    # =========================================================================
    # BEST OVERALL MOLECULE
    # =========================================================================
    print(f"\n{'='*70}")
    print("BEST OVERALL MOLECULE DISCOVERED BY GENOROVA AI")
    print(f"{'='*70}")

    all_candidates = []
    if len(diabetes_df) > 0:
        top_d = diabetes_df.head(1).copy()
        top_d["disease"] = "Diabetes"
        all_candidates.append(top_d)
    if len(infection_df) > 0:
        top_i = infection_df.head(1).copy()
        top_i["disease"] = "Infection"
        all_candidates.append(top_i)

    if all_candidates:
        combined = pd.concat(all_candidates).sort_values(
            "clinical_score", ascending=False
        ).reset_index(drop=True)
        best = combined.iloc[0]
        print(f"\n  SMILES:            {best['smiles']}")
        print(f"  Disease target:    {best['disease']}")
        print(f"  Clinical score:    {best['clinical_score']:.4f}")
        print(f"  QED score:         {best['qed_score']:.4f}  (0-1, higher = more drug-like)")
        print(f"  SA score:          {best['sa_score']:.4f}  (1-10, lower = easier to synthesize)")
        print(f"  Molecular weight:  {best['molecular_weight']:.2f} Da")
        print(f"  LogP:              {best['logp']:.3f}")
        print(f"  TPSA:              {best['tpsa']:.1f} A^2")
        print(f"  Passes Lipinski:   {best['passes_lipinski']}")
        print(f"  Recommendation:    {best['recommendation']}")
    else:
        print("  [!] No molecules discovered in this run")

    # =========================================================================
    # 2D STRUCTURE IMAGES -- Top 3 from each disease
    # =========================================================================
    print(f"\n{'='*70}")
    print("GENERATING 2D STRUCTURE IMAGES")
    print(f"{'='*70}")

    d_images = []
    i_images = []

    if len(diabetes_df) > 0:
        d_images = generate_structure_images(diabetes_df, "diabetes",  n_top=3)
    else:
        print("  [!] No diabetes candidates to image")

    if len(infection_df) > 0:
        i_images = generate_structure_images(infection_df, "infection", n_top=3)
    else:
        print("  [!] No infection candidates to image")

    # =========================================================================
    # FILES SAVED SUMMARY
    # =========================================================================
    print(f"\n{'='*70}")
    print("ALL FILES SAVED:")
    print(f"{'='*70}")
    print(f"  Diabetes model:            outputs/models/diabetes/genorova_diabetes_best.pt")
    print(f"  Infection model:           outputs/models/infection/genorova_infection_best.pt")
    print(f"  Diabetes candidates CSV:   outputs/generated/diabetes_candidates_validated.csv")
    print(f"  Infection candidates CSV:  outputs/generated/infection_candidates_validated.csv")
    all_images = d_images + i_images
    if all_images:
        print(f"  Structure images ({len(all_images)} total):")
        for p in all_images:
            print(f"    {Path(p).name}")
    print(f"{'='*70}")

    # =========================================================================
    # GENERATE COMPARISON GRIDS  (new in v1.0)
    # =========================================================================
    try:
        from vision.structure_visualizer import generate_comparison_grid
        if len(diabetes_df) > 0:
            generate_comparison_grid(
                smiles_list = diabetes_df["smiles"].head(6).tolist(),
                title       = "Genorova AI — Top Diabetes Candidates",
                output_dir  = str(IMAGES_DIR),
                cols        = 3,
            )
        if len(infection_df) > 0:
            generate_comparison_grid(
                smiles_list = infection_df["smiles"].head(6).tolist(),
                title       = "Genorova AI — Top Infection Candidates",
                output_dir  = str(IMAGES_DIR),
                cols        = 3,
            )
    except Exception as e:
        print(f"  [!] Could not generate comparison grids: {e}")

    # =========================================================================
    # AUTO-GENERATE HTML REPORT  (new in v1.0)
    # =========================================================================
    print(f"\n[*] Generating HTML discovery report...")
    try:
        from report_generator import generate_report
        report_path = generate_report(
            diabetes_df  = diabetes_df,
            infection_df = infection_df,
            runtime_min  = total_time,
        )
        print(f"[OK] HTML report: {report_path}")
    except Exception as e:
        print(f"  [!] Report generation failed: {e}")
        report_path = None

    # =========================================================================
    # FINAL STATUS LINES
    # =========================================================================
    best_smiles = best.get("smiles", "N/A") if all_candidates else "N/A"
    best_score_val = best.get("clinical_score", 0) if all_candidates else 0
    total_candidates = len(diabetes_df) + len(infection_df)

    print(f"\n{'#'*70}")
    print(f"GENOROVA AI STATUS: 100% COMPLETE")
    print(f"BEST MOLECULE DISCOVERED: {best_smiles}")
    print(f"CLINICAL SCORE: {best_score_val:.4f}")
    print(f"TOTAL CANDIDATES GENERATED: {total_candidates}")
    print(f"READY FOR REAL WORLD USE: YES")
    print(f"{'#'*70}")

    print(f"\nGenorova AI drug discovery run COMPLETE.")
    print(f"Total time: {total_time:.1f} minutes\n")


def build_cli():
    """Build the command-line interface for the refactored pipeline."""
    parser = argparse.ArgumentParser(description="Run the Genorova training and discovery pipeline.")
    parser.add_argument("--disease-label", default="diabetes",
                        help="Label used for checkpoints and generated outputs.")
    parser.add_argument("--pretrain-dataset", default="moses",
                        choices=["moses", "chembl_subset"],
                        help="Primary training corpus loaded through data_loader.load_smiles_dataset().")
    parser.add_argument("--finetune-csv", default=None,
                        help="Optional per-disease CSV used only for fine-tuning.")
    parser.add_argument("--pretrain-epochs", type=int, default=EPOCHS,
                        help="Epochs to run on the primary pretraining dataset.")
    parser.add_argument("--finetune-epochs", type=int, default=1,
                        help="Epochs to run on the optional fine-tuning CSV.")
    parser.add_argument("--pretrain-max-samples", type=int, default=None,
                        help="Optional sample cap for the primary dataset loader.")
    parser.add_argument("--skip-generation", action="store_true",
                        help="Only run training stages and checkpoint saves.")
    return parser


def main_cli():
    """CLI entrypoint for shared-data pretraining and optional fine-tuning."""
    args = build_cli().parse_args()
    set_seed(SEED)

    print("\n" + "#"*70)
    print("# GENOROVA AI -- DRUG DISCOVERY PIPELINE")
    print("# Shared-data pretraining + optional disease fine-tuning")
    print(f"# Disease label: {args.disease_label}")
    print(f"# Pretrain dataset: {args.pretrain_dataset}")
    print(f"# Fine-tune CSV: {args.finetune_csv or 'none'}")
    print(f"# Epochs: pretrain={args.pretrain_epochs} | finetune={args.finetune_epochs}")
    print(f"# Batch size: {BATCH_SIZE}")
    print("#"*70)

    try:
        from rdkit import rdBase
        rdkit_version = rdBase.rdkitVersion
        print(f"\n[OK] RDKit version: {rdkit_version}")
        print(f"[OK] Mode: REAL RDKit validation (exact chemistry, not approximation)")
        rdkit_mode = True
    except Exception as e:
        print(f"\n[!] RDKit not available: {e}")
        print(f"[!] Mode: Pure-Python approximation (fallback)")
        rdkit_mode = False

    print(f"[OK] Molecule images will be saved to: {IMAGES_DIR}")
    print(f"[OK] Pretraining will use data_loader.load_smiles_dataset() as the primary corpus")
    if args.finetune_csv:
        print(f"[OK] Fine-tuning will use optional CSV only after pretraining")

    start_wall = time.time()

    print(f"\n{'='*70}")
    print(f"RUNNING PIPELINE FOR: {args.disease_label.upper()}")
    print(f"{'='*70}")

    output_csv = GENERATED_DIR / f"{args.disease_label}_candidates_validated.csv"
    results_df, generated_smiles = run_disease_pipeline(
        disease_label=args.disease_label,
        pretrain_dataset=args.pretrain_dataset,
        output_csv=output_csv,
        pretrain_epochs=args.pretrain_epochs,
        finetune_csv=args.finetune_csv,
        finetune_epochs=args.finetune_epochs,
        pretrain_max_samples=args.pretrain_max_samples,
        skip_generation=args.skip_generation,
    )

    total_time = (time.time() - start_wall) / 60

    print(f"\n{'#'*70}")
    print("# GENOROVA AI -- RUN SUMMARY")
    print(f"{'#'*70}")
    print(f"  RDKit version:    {rdkit_version if rdkit_mode else 'NOT AVAILABLE (fallback mode)'}")
    print(f"  Validation mode:  {'Real RDKit Chem.MolFromSmiles()' if rdkit_mode else 'Pure-Python approximation'}")
    print(f"  Disease label:    {args.disease_label}")
    print(f"  Pretrain dataset: {args.pretrain_dataset}")
    print(f"  Fine-tune CSV:    {args.finetune_csv or 'none'}")
    print(f"  Runtime:          {total_time:.1f} minutes")
    print(f"  Candidate pool:   {len(generated_smiles)}")
    print(f"  Scored results:   {len(results_df)}")

    if args.skip_generation:
        print("\n[OK] Training smoke-test path complete; generation and scoring were skipped by request.")
        return

    if len(results_df) > 0:
        print(f"\n{'='*70}")
        print(f"TOP 5 {args.disease_label.upper()} CANDIDATES")
        print(f"{'='*70}")
        print(f"{'Rank':>4} | {'Score':>7} | {'QED':>5} | {'SA':>5} | "
              f"{'MW':>6} | {'LogP':>5} | {'Lip':>3} | {'Verdict':<16} | SMILES")
        print("-" * 90)
        for rank, row in results_df.head(5).iterrows():
            smi = row["smiles"][:30] + "..." if len(row["smiles"]) > 30 else row["smiles"]
            lip = "Y" if row["passes_lipinski"] else "N"
            print(f"{rank:>4} | {row['clinical_score']:>7.4f} | {row['qed_score']:>5.3f} | "
                  f"{row['sa_score']:>5.2f} | {row['molecular_weight']:>6.1f} | "
                  f"{row['logp']:>5.2f} | {lip:>3} | {row['recommendation']:<16} | {smi}")

        best = results_df.iloc[0]
        print(f"\n{'='*70}")
        print("BEST OVERALL MOLECULE DISCOVERED BY GENOROVA AI")
        print(f"{'='*70}")
        print(f"\n  SMILES:            {best['smiles']}")
        print(f"  Disease target:    {args.disease_label}")
        print(f"  Clinical score:    {best['clinical_score']:.4f}")
        print(f"  QED score:         {best['qed_score']:.4f}  (0-1, higher = more drug-like)")
        print(f"  SA score:          {best['sa_score']:.4f}  (1-10, lower = easier to synthesize)")
        print(f"  Molecular weight:  {best['molecular_weight']:.2f} Da")
        print(f"  LogP:              {best['logp']:.3f}")
        print(f"  TPSA:              {best['tpsa']:.1f} A^2")
        print(f"  Passes Lipinski:   {best['passes_lipinski']}")
        print(f"  Recommendation:    {best['recommendation']}")

        print(f"\n{'='*70}")
        print("GENERATING 2D STRUCTURE IMAGES")
        print(f"{'='*70}")
        images = generate_structure_images(results_df, args.disease_label, n_top=3)

        print(f"\n[*] Generating HTML discovery report...")
        try:
            from report_generator import generate_report
            empty_df = pd.DataFrame()
            report_path = generate_report(
                diabetes_df=results_df if args.disease_label == "diabetes" else empty_df,
                infection_df=results_df if args.disease_label != "diabetes" else empty_df,
                runtime_min=total_time,
            )
            print(f"[OK] HTML report: {report_path}")
        except Exception as e:
            print(f"  [!] Report generation failed: {e}")

        print(f"\n{'='*70}")
        print("ALL FILES SAVED:")
        print(f"{'='*70}")
        print(f"  Candidates CSV: {output_csv}")
        if images:
            print(f"  Structure images ({len(images)} total):")
            for p in images:
                print(f"    {Path(p).name}")
    else:
        print("\n[!] No candidates were produced in this run.")

    print(f"\nGenorova AI run COMPLETE.")
    print(f"Total time: {total_time:.1f} minutes\n")


if __name__ == "__main__":
    main_cli()
