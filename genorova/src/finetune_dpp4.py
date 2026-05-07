"""
Fine-tune the Genorova CVAE on potent DPP-4 inhibitors.

Default run:
    python -u genorova/src/finetune_dpp4.py

Outputs:
    genorova/outputs/checkpoints/dpp4_finetuned.pt
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

_SRC = Path(__file__).resolve().parent
_GENOROVA = _SRC.parent
_PROJECT_ROOT = _GENOROVA.parent

sys.path.insert(0, str(_GENOROVA))
sys.path.insert(0, str(_SRC))

from models.cvae import (  # noqa: E402
    BOS_ID,
    EOS_ID,
    MAX_SEQ_LEN,
    NUM_PROPS,
    PAD_ID,
    CVAE,
    cvae_loss,
)
from tokenizers import Tokenizer as HFTokenizer  # noqa: E402

from rdkit import Chem, DataStructs, RDLogger  # noqa: E402
from rdkit.Chem import AllChem, Descriptors, QED  # noqa: E402

from admet.scorer import score_smiles  # noqa: E402

RDLogger.DisableLog("rdApp.*")

try:
    from rdkit.Chem import RDConfig  # noqa: E402

    sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
    from sascorer import calculateScore as _calc_sa  # type: ignore  # noqa: E402
except Exception:
    _calc_sa = None


DEFAULT_BASE_CKPT = "genorova/outputs/checkpoints/best.pt"
DEFAULT_DPP4_CSV = "genorova/data/chembl/dpp4_actives.csv"
DEFAULT_TOKENIZER = "genorova/tokenizer/genorova_bpe.json"
DEFAULT_OUT_CKPT = "genorova/outputs/checkpoints/dpp4_finetuned.pt"

PROP_COLS = ["qed", "logp", "mol_weight", "sa_score"]
SITA_SMI = "O=C(N1CCC[C@@H]1C(=O)N1CCn2c(nnc2-c2ccc(F)cc2)C1)CC(F)(F)F"

REFERENCE_ANCHORS = [
    "CN(C)C(=O)[C@@H](c1ccc(-c2ccc(F)cc2)cc1)[C@H](N)C(=O)N1CC[C@H](F)C1",
    "N#Cc1cccc(NC(=O)CN2CCn3c(nnc3C(F)(F)F)C2)c1",
    "O=C(CN1CCn2c(nnc2C(F)(F)F)C1)NC1CCCCC1",
]


def log(message: str = "") -> None:
    print(message, flush=True)


def resolve_path(path_text: str | Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return _PROJECT_ROOT / path


@dataclass
class FineTuneConfig:
    epochs: int = 20
    batch_size: int = 32
    lr: float = 1e-4
    weight_decay: float = 1e-4
    grad_clip: float = 1.0
    beta: float = 0.5
    lambda_prop: float = 0.5
    val_fraction: float = 0.10
    eval_every: int = 5
    eval_n: int = 50
    final_n: int = 200
    temperature: float = 0.8
    seed: int = 42
    num_workers: int = 0
    resume: bool = False

    vocab_size: int = 1000
    max_seq_len: int = MAX_SEQ_LEN
    latent_dim: int = 512
    d_model: int = 256
    num_heads: int = 4
    num_layers: int = 3


class CVAETokenizer:
    """BOS/EOS framing wrapper around the Genorova BPE tokenizer."""

    def __init__(self, path: Path, max_len: int = MAX_SEQ_LEN):
        if not path.exists():
            raise FileNotFoundError(f"BPE tokenizer not found: {path}")
        self.hf = HFTokenizer.from_file(str(path))
        self.max_len = max_len

    @property
    def vocab_size(self) -> int:
        return self.hf.get_vocab_size()

    def encode(self, smiles: str) -> list[int]:
        ids = self.hf.encode(smiles).ids
        ids = [BOS_ID] + ids[: self.max_len - 2] + [EOS_ID]
        ids += [PAD_ID] * (self.max_len - len(ids))
        return ids

    def encode_batch(self, smiles_list: list[str]) -> np.ndarray:
        return np.array([self.encode(s) for s in smiles_list], dtype=np.int64)

    def ids_to_smiles(self, token_ids: list[int] | torch.Tensor) -> str:
        skip = {PAD_ID, BOS_ID, EOS_ID}
        pieces: list[str] = []
        for token_id in token_ids:
            i = int(token_id)
            if i in skip:
                continue
            token = self.hf.id_to_token(i)
            if token:
                pieces.append(token)
        return "".join(pieces)


class DPP4Dataset(Dataset):
    def __init__(self, smiles: list[str], props_norm: np.ndarray, tokenizer: CVAETokenizer):
        self.smiles = smiles
        self.props = torch.from_numpy(props_norm.astype(np.float32)).float()
        self.tokens = torch.from_numpy(tokenizer.encode_batch(smiles)).long()

    def __len__(self) -> int:
        return len(self.smiles)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        return {
            "tokens": self.tokens[idx],
            "props": self.props[idx],
            "smiles": self.smiles[idx],
        }


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def mol_props(smiles: str) -> tuple[float, float, float, float] | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        qed = QED.qed(mol)
        logp = Descriptors.MolLogP(mol)
        mw = Descriptors.ExactMolWt(mol)
        sa = float(_calc_sa(mol)) if _calc_sa is not None else 4.0
        return qed, logp, mw, sa
    except Exception:
        return None


def canonical_smiles(smiles: str) -> str | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def load_potent_dpp4(csv_path: Path) -> tuple[list[str], np.ndarray, set[str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"DPP-4 CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if "smiles" not in df.columns or "ic50_nm" not in df.columns:
        raise ValueError("DPP-4 CSV must contain smiles and ic50_nm columns.")

    df["ic50_nm"] = pd.to_numeric(df["ic50_nm"], errors="coerce")
    potent = df[df["ic50_nm"] < 100].copy()
    potent["smiles"] = potent["smiles"].astype(str).str.strip()
    potent = potent[potent["smiles"].str.len() > 0]

    for col in PROP_COLS:
        if col not in potent.columns:
            potent[col] = np.nan

    smiles: list[str] = []
    props: list[tuple[float, float, float, float]] = []
    canon_set: set[str] = set()

    for row in potent.itertuples(index=False):
        row_dict = row._asdict()
        smi = str(row_dict["smiles"]).strip()
        canon = canonical_smiles(smi)
        if canon is None:
            continue

        raw_vals = [row_dict.get(col, np.nan) for col in PROP_COLS]
        vals = [float(v) if pd.notna(v) else np.nan for v in raw_vals]
        if any(np.isnan(vals)):
            computed = mol_props(smi)
            if computed is None:
                continue
            vals = list(computed)

        smiles.append(smi)
        props.append((vals[0], vals[1], vals[2], vals[3]))
        canon_set.add(canon)

    props_array = np.asarray(props, dtype=np.float32)
    return smiles, props_array, canon_set


def fingerprint(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)


def load_base_checkpoint(path: Path, attempts: int = 4, delay_s: int = 5) -> dict[str, Any]:
    for attempt in range(1, attempts + 1):
        try:
            return torch.load(path, weights_only=False, map_location="cpu")
        except Exception as exc:
            if attempt == attempts:
                raise
            log(f"[WARN] Could not read base checkpoint on attempt {attempt}: {exc}")
            log(f"       Retrying in {delay_s}s in case best.pt is being updated...")
            time.sleep(delay_s)
    raise RuntimeError("unreachable")


def update_arch_from_checkpoint(cfg: FineTuneConfig, ckpt: dict[str, Any]) -> None:
    ckpt_cfg = ckpt.get("config") or {}
    for field_name in ("max_seq_len", "latent_dim", "d_model", "num_heads", "num_layers"):
        if field_name in ckpt_cfg:
            setattr(cfg, field_name, int(ckpt_cfg[field_name]))
    if "lambda_prop" in ckpt_cfg:
        cfg.lambda_prop = float(ckpt_cfg["lambda_prop"])


def build_model_from_checkpoint(
    cfg: FineTuneConfig,
    tokenizer: CVAETokenizer,
    ckpt: dict[str, Any],
    device: torch.device,
) -> CVAE:
    cfg.vocab_size = tokenizer.vocab_size
    model = CVAE(
        vocab_size=cfg.vocab_size,
        d_model=cfg.d_model,
        latent_dim=cfg.latent_dim,
        num_heads=cfg.num_heads,
        num_layers=cfg.num_layers,
        max_len=cfg.max_seq_len,
    )

    state = ckpt.get("model_state_dict")
    state_key = "model_state_dict"
    if state is None:
        state = ckpt.get("model_state")
        state_key = "model_state"
    if state is None:
        raise KeyError("Checkpoint has neither model_state_dict nor model_state.")

    model.load_state_dict(state, strict=True)
    model.to(device)
    log(f"[CKPT] Loaded weights from {state_key}")
    return model


def checkpoint_prop_stats(ckpt: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    if "prop_mean" not in ckpt or "prop_std" not in ckpt:
        raise KeyError("Base checkpoint must contain prop_mean and prop_std.")
    prop_mean = np.asarray(ckpt["prop_mean"], dtype=np.float32)
    prop_std = np.asarray(ckpt["prop_std"], dtype=np.float32)
    prop_std = np.clip(prop_std, 1e-6, None)
    if prop_mean.shape != (NUM_PROPS,) or prop_std.shape != (NUM_PROPS,):
        raise ValueError("prop_mean and prop_std must both have shape (4,).")
    return prop_mean, prop_std


def split_loaders(
    smiles: list[str],
    props_norm: np.ndarray,
    tokenizer: CVAETokenizer,
    cfg: FineTuneConfig,
) -> tuple[DataLoader, DataLoader]:
    rng = np.random.default_rng(cfg.seed)
    indices = rng.permutation(len(smiles))
    n_val = max(1, int(len(indices) * cfg.val_fraction))
    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    train_ds = DPP4Dataset([smiles[i] for i in train_idx], props_norm[train_idx], tokenizer)
    val_ds = DPP4Dataset([smiles[i] for i in val_idx], props_norm[val_idx], tokenizer)

    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg.batch_size,
        shuffle=False,
        num_workers=cfg.num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    return train_loader, val_loader


def mean_dict(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {"loss": 0.0, "recon_loss": 0.0, "kl_loss": 0.0, "prop_loss": 0.0}
    keys = rows[0].keys()
    return {key: float(np.mean([r[key] for r in rows])) for key in keys}


def train_epoch(
    model: CVAE,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scaler: torch.amp.GradScaler,
    device: torch.device,
    cfg: FineTuneConfig,
    use_amp: bool,
) -> dict[str, float]:
    model.train()
    rows: list[dict[str, float]] = []

    for batch in loader:
        tokens = batch["tokens"].to(device, non_blocking=True)
        props = batch["props"].to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast("cuda", enabled=use_amp):
            out = model(tokens, props)
            loss_dict = cvae_loss(
                out["recon_logits"],
                tokens,
                out["mu"],
                out["log_var"],
                out["pred_props"],
                props,
                beta=cfg.beta,
                lambda_prop=cfg.lambda_prop,
            )

        scaler.scale(loss_dict["loss"]).backward()
        scaler.unscale_(optimizer)
        nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
        scaler.step(optimizer)
        scaler.update()

        rows.append(
            {
                "loss": float(loss_dict["loss"].detach().item()),
                "recon_loss": float(loss_dict["recon_loss"].item()),
                "kl_loss": float(loss_dict["kl_loss"].item()),
                "prop_loss": float(loss_dict["prop_loss"].item()),
            }
        )

    return mean_dict(rows)


@torch.no_grad()
def validate_epoch(
    model: CVAE,
    loader: DataLoader,
    device: torch.device,
    cfg: FineTuneConfig,
    use_amp: bool,
) -> dict[str, float]:
    model.eval()
    rows: list[dict[str, float]] = []

    for batch in loader:
        tokens = batch["tokens"].to(device, non_blocking=True)
        props = batch["props"].to(device, non_blocking=True)
        with torch.amp.autocast("cuda", enabled=use_amp):
            out = model(tokens, props)
            loss_dict = cvae_loss(
                out["recon_logits"],
                tokens,
                out["mu"],
                out["log_var"],
                out["pred_props"],
                props,
                beta=cfg.beta,
                lambda_prop=cfg.lambda_prop,
            )
        rows.append(
            {
                "loss": float(loss_dict["loss"].detach().item()),
                "recon_loss": float(loss_dict["recon_loss"].item()),
                "kl_loss": float(loss_dict["kl_loss"].item()),
                "prop_loss": float(loss_dict["prop_loss"].item()),
            }
        )

    return mean_dict(rows)


@torch.no_grad()
def generate_conditioned(
    model: CVAE,
    tokenizer: CVAETokenizer,
    props_norm_pool: np.ndarray,
    n: int,
    device: torch.device,
    cfg: FineTuneConfig,
    rng: np.random.Generator,
) -> list[str]:
    model.eval()
    generated: list[str] = []

    for start in range(0, n, cfg.batch_size):
        batch_n = min(cfg.batch_size, n - start)
        idx = rng.integers(0, len(props_norm_pool), size=batch_n)
        props = torch.from_numpy(props_norm_pool[idx].astype(np.float32)).to(device)
        seqs = model.generate(
            props,
            max_len=cfg.max_seq_len,
            beam_k=1,
            temperature=cfg.temperature,
        )
        generated.extend(tokenizer.ids_to_smiles(seq) for seq in seqs)

    return generated


def evaluate_generated(
    smiles_list: list[str],
    training_canon: set[str],
) -> dict[str, Any]:
    sita_fp = fingerprint(SITA_SMI)
    if sita_fp is None:
        raise RuntimeError("Could not fingerprint sitagliptin reference.")

    rows: list[dict[str, Any]] = []
    for smi in smiles_list:
        canon = canonical_smiles(smi)
        if canon is None:
            continue

        fp = fingerprint(canon)
        tanimoto = DataStructs.TanimotoSimilarity(fp, sita_fp) if fp is not None else None
        score = score_smiles(canon)

        rows.append(
            {
                "smiles": canon,
                "tanimoto": tanimoto,
                "admet": score.get("composite_score") if score.get("valid") else None,
                "qed": score.get("QED") if score.get("valid") else None,
                "lipinski_pass": score.get("lipinski_pass") if score.get("valid") else False,
                "grade": score.get("grade") if score.get("valid") else None,
            }
        )

    total = len(smiles_list)
    valid = len(rows)
    unique_canons = {row["smiles"] for row in rows}
    novel_canons = {s for s in unique_canons if s not in training_canon}

    def mean_present(key: str) -> float:
        values = [row[key] for row in rows if row.get(key) is not None]
        return float(np.mean(values)) if values else 0.0

    lipinski_pct = (
        100.0 * sum(1 for row in rows if row["lipinski_pass"]) / valid
        if valid
        else 0.0
    )
    grade_a_pct = (
        100.0 * sum(1 for row in rows if row["grade"] == "A") / valid
        if valid
        else 0.0
    )

    best_by_smiles: dict[str, dict[str, Any]] = {}
    for row in rows:
        score = row["admet"] if row["admet"] is not None else -1.0
        existing = best_by_smiles.get(row["smiles"])
        existing_score = existing["admet"] if existing and existing["admet"] is not None else -1.0
        if existing is None or score > existing_score:
            best_by_smiles[row["smiles"]] = row

    top5 = sorted(
        best_by_smiles.values(),
        key=lambda row: row["admet"] if row["admet"] is not None else -1.0,
        reverse=True,
    )[:5]

    return {
        "total": total,
        "valid": valid,
        "validity_pct": 100.0 * valid / max(total, 1),
        "unique": len(unique_canons),
        "novel": len(novel_canons),
        "mean_qed": mean_present("qed"),
        "mean_tanimoto": mean_present("tanimoto"),
        "mean_admet": mean_present("admet"),
        "lipinski_pct": lipinski_pct,
        "grade_a_pct": grade_a_pct,
        "top5": top5,
    }


def print_eval(epoch: int, metrics: dict[str, Any]) -> None:
    log(
        f"[EVAL epoch {epoch:02d}] "
        f"validity={metrics['validity_pct']:.1f}% "
        f"mean_tanimoto_sitagliptin={metrics['mean_tanimoto']:.4f} "
        f"mean_admet={metrics['mean_admet']:.2f} "
        f"lipinski_pass={metrics['lipinski_pct']:.1f}%"
    )


def print_final_report(metrics: dict[str, Any]) -> None:
    log("")
    log("=" * 78)
    log("FINAL DPP-4 CONDITIONED GENERATION REPORT")
    log("=" * 78)
    log("| Metric | Value |")
    log("|---|---:|")
    log(f"| Total generated | {metrics['total']} |")
    log(f"| Valid | {metrics['valid']} ({metrics['validity_pct']:.1f}%) |")
    log(f"| Unique | {metrics['unique']} |")
    log(f"| Novel | {metrics['novel']} |")
    log(f"| Mean QED | {metrics['mean_qed']:.4f} |")
    log(f"| Mean Tanimoto to sitagliptin | {metrics['mean_tanimoto']:.4f} |")
    log(f"| Mean ADMET composite | {metrics['mean_admet']:.2f} |")
    log(f"| % Grade A | {metrics['grade_a_pct']:.1f}% |")
    log("")
    log("Top 5 molecules by composite score:")
    if not metrics["top5"]:
        log("  No valid molecules generated.")
        return

    for rank, row in enumerate(metrics["top5"], start=1):
        admet = row["admet"] if row["admet"] is not None else 0.0
        qed = row["qed"] if row["qed"] is not None else 0.0
        tanimoto = row["tanimoto"] if row["tanimoto"] is not None else 0.0
        grade = row["grade"] or "?"
        log(
            f"{rank}. score={admet:.2f} grade={grade} "
            f"qed={qed:.4f} tanimoto={tanimoto:.4f} "
            f"smiles={row['smiles']}"
        )


def save_best_checkpoint(
    out_path: Path,
    model: CVAE,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    val_loss: float,
    prop_mean: np.ndarray,
    prop_std: np.ndarray,
    cfg: FineTuneConfig,
    base_ckpt: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    state = model.state_dict()
    torch.save(
        {
            "epoch": epoch,
            "val_loss": val_loss,
            "model_state_dict": state,
            "model_state": state,
            "optimizer_state_dict": optimizer.state_dict(),
            "prop_mean": prop_mean,
            "prop_std": prop_std,
            "config": asdict(cfg),
            "base_checkpoint": str(base_ckpt),
            "task": "dpp4_finetune",
        },
        out_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune Genorova CVAE on DPP-4 actives.")
    parser.add_argument("--base-ckpt", default=DEFAULT_BASE_CKPT)
    parser.add_argument("--dpp4-csv", default=DEFAULT_DPP4_CSV)
    parser.add_argument("--tokenizer", default=DEFAULT_TOKENIZER)
    parser.add_argument("--out-ckpt", default=DEFAULT_OUT_CKPT)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing out-ckpt (dpp4_finetuned.pt) instead of base best.pt")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = FineTuneConfig(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        seed=args.seed,
        resume=args.resume,
    )
    set_seed(cfg.seed)

    base_ckpt_path = resolve_path(args.base_ckpt)
    dpp4_csv_path = resolve_path(args.dpp4_csv)
    tokenizer_path = resolve_path(args.tokenizer)
    out_ckpt_path = resolve_path(args.out_ckpt)

    log("=" * 78)
    log("Genorova DPP-4 CVAE fine-tuning")
    log("=" * 78)
    log(f"[BASE] {base_ckpt_path}")
    log(f"[DATA] {dpp4_csv_path}")
    log(f"[OUT ] {out_ckpt_path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = torch.cuda.is_available()
    log(f"[DEVICE] {device} | AMP={'on' if use_amp else 'off'}")

    # With --resume: load weights from the existing dpp4_finetuned.pt so we continue
    # from the fine-tuned state rather than restarting from best.pt.
    # Architecture params (vocab, latent_dim, etc.) are still pulled from base_ckpt_path
    # because dpp4_finetuned.pt may store a dataclass config, not the raw int fields.
    _resume_best_val = float("inf")   # carried into best_val_loss below
    if cfg.resume and out_ckpt_path.exists():
        log(f"[RESUME] Loading fine-tuned weights from {out_ckpt_path}")
        resume_ckpt = load_base_checkpoint(out_ckpt_path)
        prev_epoch = resume_ckpt.get("epoch", "?")
        prev_loss  = resume_ckpt.get("val_loss", float("nan"))
        log(f"[RESUME] Resuming after epoch={prev_epoch}  best_val_loss={prev_loss:.4f}")
        import math
        if not math.isnan(prev_loss):
            _resume_best_val = prev_loss   # only save if we actually improve
        ckpt = load_base_checkpoint(base_ckpt_path)   # arch + prop stats
        update_arch_from_checkpoint(cfg, ckpt)
        prop_mean, prop_std = checkpoint_prop_stats(ckpt)
        log(f"[NORM] mean={np.round(prop_mean, 4).tolist()}")
        log(f"[NORM] std ={np.round(prop_std, 4).tolist()}")
        tokenizer = CVAETokenizer(tokenizer_path, max_len=cfg.max_seq_len)
        model = build_model_from_checkpoint(cfg, tokenizer, resume_ckpt, device)
    else:
        if cfg.resume:
            log(f"[RESUME] {out_ckpt_path} not found — starting from base checkpoint")
        ckpt = load_base_checkpoint(base_ckpt_path)
        log(f"[BASE] epoch={ckpt.get('epoch')} val_loss={ckpt.get('val_loss')}")
        update_arch_from_checkpoint(cfg, ckpt)
        prop_mean, prop_std = checkpoint_prop_stats(ckpt)
        log(f"[NORM] mean={np.round(prop_mean, 4).tolist()}")
        log(f"[NORM] std ={np.round(prop_std, 4).tolist()}")
        tokenizer = CVAETokenizer(tokenizer_path, max_len=cfg.max_seq_len)
        model = build_model_from_checkpoint(cfg, tokenizer, ckpt, device)

    smiles, props_raw, training_canon = load_potent_dpp4(dpp4_csv_path)
    props_norm = (props_raw - prop_mean) / prop_std
    log(f"[DATA] potent ic50_nm < 100: {len(smiles):,} valid molecules")

    found_anchors = sum(1 for smi in REFERENCE_ANCHORS if canonical_smiles(smi) in training_canon)
    log(f"[DATA] reference anchors found: {found_anchors}/{len(REFERENCE_ANCHORS)}")

    train_loader, val_loader = split_loaders(smiles, props_norm, tokenizer, cfg)
    log(f"[DATA] train={len(train_loader.dataset):,} val={len(val_loader.dataset):,}")
    log(
        "[CONFIG] "
        f"lr={cfg.lr:g} batch_size={cfg.batch_size} epochs={cfg.epochs} "
        f"beta={cfg.beta} weight_decay={cfg.weight_decay:g} grad_clip={cfg.grad_clip}"
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=cfg.lr,
        weight_decay=cfg.weight_decay,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    rng = np.random.default_rng(cfg.seed + 2026)

    best_val_loss = _resume_best_val   # float("inf") on fresh run; prev val_loss on resume
    start_time = time.time()

    for epoch in range(1, cfg.epochs + 1):
        epoch_start = time.time()
        train_metrics = train_epoch(model, train_loader, optimizer, scaler, device, cfg, use_amp)
        val_metrics = validate_epoch(model, val_loader, device, cfg, use_amp)
        elapsed = time.time() - epoch_start
        val_loss = val_metrics["loss"]

        log(
            f"[EPOCH {epoch:02d}/{cfg.epochs}] "
            f"train_loss={train_metrics['loss']:.4f} "
            f"val_loss={val_loss:.4f} "
            f"recon={val_metrics['recon_loss']:.4f} "
            f"kl={val_metrics['kl_loss']:.4f} "
            f"prop={val_metrics['prop_loss']:.4f} "
            f"elapsed={elapsed:.1f}s"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            save_best_checkpoint(
                out_ckpt_path,
                model,
                optimizer,
                epoch,
                val_loss,
                prop_mean,
                prop_std,
                cfg,
                base_ckpt_path,
            )
            log(f"[CKPT] New best fine-tuned checkpoint saved: {out_ckpt_path} (val={val_loss:.4f})")

        if epoch % cfg.eval_every == 0:
            eval_smiles = generate_conditioned(
                model,
                tokenizer,
                props_norm,
                cfg.eval_n,
                device,
                cfg,
                rng,
            )
            eval_metrics = evaluate_generated(eval_smiles, training_canon)
            print_eval(epoch, eval_metrics)

    final_smiles = generate_conditioned(
        model,
        tokenizer,
        props_norm,
        cfg.final_n,
        device,
        cfg,
        rng,
    )
    final_metrics = evaluate_generated(final_smiles, training_canon)
    print_final_report(final_metrics)

    total_elapsed = time.time() - start_time
    log("")
    log(f"[DONE] Best validation loss: {best_val_loss:.4f}")
    log(f"[DONE] Best checkpoint: {out_ckpt_path}")
    log(f"[DONE] Total elapsed: {total_elapsed / 60:.1f} min")


if __name__ == "__main__":
    main()
