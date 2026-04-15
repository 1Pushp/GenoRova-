"""
Genorova AI -- Generation Quality Evaluation
============================================

Evaluate a trained Genorova VAE checkpoint by generating a batch of model
candidates, validating them with RDKit, comparing them to a reference training
corpus, and summarizing the output quality.

Outputs:
    - generated_molecules.csv
    - evaluation_metrics.json
    - evaluation_summary.md

The saved summary is intentionally conservative: these are computationally
generated candidates for research support only, not experimentally validated
drug discoveries.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import torch

from data_loader import load_smiles_dataset, load_smiles_from_csv
from model import LATENT_DIM, VAE
from preprocessor import (
    PAD_TOKEN,
    BOS_TOKEN,
    EOS_TOKEN,
    load_vocab,
    preprocess_batch,
    decode_token_ids,
    get_special_token_ids,
    select_token_ids_from_logits,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "outputs"
MODEL_DIR = OUTPUT_DIR / "models"
EVAL_OUTPUT_DIR = OUTPUT_DIR / "evaluation"
WINNING_BASELINE_CHECKPOINT = MODEL_DIR / "diabetes" / "genorova_diabetes_finetune_best.pt"
WINNING_BASELINE_REFERENCE_CSV = ROOT_DIR / "data" / "raw" / "diabetes_molecules.csv"
DEFAULT_TOP_K = 5
DEFAULT_REPETITION_PENALTY = 0.75
DEFAULT_STRUCTURAL_GUARD_STRENGTH = 1.0

DEFAULT_FILTERS = {
    "qed_min": 0.50,
    "sa_max": 6.0,
    "mw_min": 150.0,
    "mw_max": 500.0,
    "logp_min": -1.0,
    "logp_max": 5.0,
    "require_lipinski": True,
}


def _set_seed(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _require_rdkit():
    try:
        from rdkit import Chem
        from rdkit import RDLogger
        from rdkit.Chem import Crippen, Descriptors

        RDLogger.DisableLog("rdApp.*")
        return Chem, Descriptors, Crippen
    except Exception as exc:
        raise RuntimeError(
            "RDKit is required for generation evaluation because validity and novelty "
            "depend on canonical RDKit parsing."
        ) from exc


def _pct(count: int, total: int) -> float:
    return round(100.0 * count / max(1, total), 2)


def _resolve_default_checkpoint() -> Path:
    candidates = [
        MODEL_DIR / "genorova_best.pt",
        MODEL_DIR / "diabetes" / "genorova_diabetes_finetune_best.pt",
        MODEL_DIR / "diabetes" / "genorova_diabetes_pretrain_best.pt",
        MODEL_DIR / "diabetes" / "genorova_diabetes_best.pt",
        MODEL_DIR / "infection" / "genorova_infection_best.pt",
    ]
    for path in candidates:
        if path.exists():
            return path

    best_files = sorted(MODEL_DIR.rglob("*best.pt"))
    if best_files:
        return best_files[0]
    raise FileNotFoundError("No checkpoint found under genorova/outputs/models/")


def _load_checkpoint_state(checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    state_dict = checkpoint.get("model_state") or checkpoint.get("model_state_dict")
    if state_dict is None:
        raise KeyError(f"Checkpoint {checkpoint_path} is missing model weights.")
    checkpoint["_resolved_model_state"] = state_dict
    return checkpoint


def _vocab_size_from_checkpoint(checkpoint: dict[str, Any]) -> int:
    if checkpoint.get("vocab_size") is not None:
        return int(checkpoint["vocab_size"])
    state = checkpoint["_resolved_model_state"]
    flattened_size = state["encoder.fc1.weight"].shape[1]
    max_length = int(checkpoint.get("max_length") or 120)
    return int(flattened_size // max_length)


def _candidate_vocab_paths() -> list[Path]:
    return [
        OUTPUT_DIR / "vocabulary_diabetes_pretrain.json",
        OUTPUT_DIR / "vocabulary_diabetes.json",
        OUTPUT_DIR / "vocabulary_infection.json",
        OUTPUT_DIR / "vocab.json",
        OUTPUT_DIR / "vocabulary.json",
    ]


def _resolve_default_vocab(checkpoint_path: Path) -> Path:
    checkpoint = _load_checkpoint_state(checkpoint_path)
    target_vocab_size = _vocab_size_from_checkpoint(checkpoint)
    disease = str(checkpoint.get("disease") or "").lower()
    stage_name = str(checkpoint.get("stage_name") or "").lower()
    candidates = [path for path in _candidate_vocab_paths() if path.exists()]

    matching: list[tuple[int, Path]] = []
    for path in candidates:
        try:
            char2idx, _ = load_vocab(str(path))
        except Exception:
            continue
        if len(char2idx) != target_vocab_size:
            continue

        score = 0
        path_name = path.stem.lower()
        if disease and disease in path_name:
            score += 3
        if stage_name and stage_name in path_name:
            score += 2
        if "pretrain" in path_name and stage_name == "pretrain":
            score += 2
        if path.name == "vocab.json":
            score += 1
        matching.append((score, path))

    if matching:
        matching.sort(key=lambda item: (-item[0], str(item[1])))
        return matching[0][1]

    raise FileNotFoundError(
        f"Could not find a vocabulary file matching checkpoint {checkpoint_path} (expected vocab size {target_vocab_size})."
    )


def _infer_model_max_length(checkpoint: dict[str, Any], vocab_size: int) -> int:
    if "max_length" in checkpoint:
        return int(checkpoint["max_length"])

    state = checkpoint.get("model_state") or checkpoint.get("model_state_dict")
    if not state:
        raise KeyError("Checkpoint does not contain model_state or model_state_dict.")

    encoder_weight = state["encoder.fc1.weight"]
    flattened_size = encoder_weight.shape[1]
    return int(flattened_size // vocab_size)


def _load_model(checkpoint_path: Path, vocab_path: Path, device: torch.device):
    checkpoint = _load_checkpoint_state(checkpoint_path)
    state_dict = checkpoint["_resolved_model_state"]

    char2idx, idx2char = load_vocab(str(vocab_path))
    vocab_size = len(char2idx)
    max_length = _infer_model_max_length(checkpoint, vocab_size)

    model = VAE(vocab_size=vocab_size, latent_dim=LATENT_DIM, max_length=max_length).to(device)
    model.load_state_dict(state_dict)
    model.eval()
    return model, checkpoint, char2idx, idx2char, max_length


def _decode_with_debug(
    indices: torch.Tensor,
    idx2char: dict[int, str],
    char2idx: dict[str, int],
) -> list[dict[str, Any]]:
    rows = []
    for seq in indices:
        rows.append(decode_token_ids(seq, idx2char, char2idx=char2idx))
    return rows


def _generate_random(
    model: VAE,
    idx2char: dict[int, str],
    char2idx: dict[str, int],
    num_samples: int,
    device: torch.device,
    *,
    top_k: int,
    repetition_penalty: float,
    structural_guard_strength: float,
    temperature: float,
):
    with torch.no_grad():
        z = torch.randn(num_samples, LATENT_DIM, device=device)
        recon = model.decode(z)
        indices = select_token_ids_from_logits(
            recon,
            char2idx,
            temperature=temperature,
            strategy="sample" if top_k else "greedy",
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            min_tokens_before_stop=2,
            structural_guard_strength=structural_guard_strength,
        )
    decoded = _decode_with_debug(indices, idx2char, char2idx)
    return decoded, {
        "latent_source": "random",
        "latent_std": round(float(z.std().item()), 6),
        "top_k": top_k,
        "repetition_penalty": repetition_penalty,
        "structural_guard_strength": structural_guard_strength,
    }


def _generate_guided(
    model: VAE,
    reference_smiles: list[str],
    char2idx: dict[str, int],
    idx2char: dict[int, str],
    max_length: int,
    num_samples: int,
    temperature: float,
    device: torch.device,
    *,
    top_k: int,
    repetition_penalty: float,
    structural_guard_strength: float,
):
    if not reference_smiles:
        raise ValueError("Guided generation requires at least one reference molecule.")

    encoded = preprocess_batch(reference_smiles, char2idx, max_length=max_length)
    tensor_data = torch.from_numpy(encoded).float().to(device)
    batch_size = 64
    generated: list[dict[str, Any]] = []

    with torch.no_grad():
        mu_batches = []
        for start in range(0, len(tensor_data), batch_size):
            batch = tensor_data[start : start + batch_size]
            mu, _ = model.encoder(batch)
            mu_batches.append(mu.cpu())
        all_mu = torch.cat(mu_batches, dim=0)
        mu_std = float(all_mu.std().item())
        mu_mean_abs = float(all_mu.abs().mean().item())

        for start in range(0, num_samples, batch_size):
            this_batch = min(batch_size, num_samples - start)
            index = torch.randint(0, len(all_mu), (this_batch,))
            z = all_mu[index].to(device)
            z = z + (torch.randn_like(z) * temperature)
            recon = model.decode(z)
            indices = select_token_ids_from_logits(
                recon,
                char2idx,
                temperature=max(temperature, 0.2),
                strategy="sample",
                top_k=top_k,
                repetition_penalty=repetition_penalty,
                min_tokens_before_stop=2,
                structural_guard_strength=structural_guard_strength,
            )
            generated.extend(_decode_with_debug(indices, idx2char, char2idx))

    return generated, {
        "latent_source": "guided",
        "anchor_count": len(reference_smiles),
        "anchor_mu_std": round(mu_std, 6),
        "anchor_mu_mean_abs": round(mu_mean_abs, 6),
        "temperature": temperature,
        "top_k": top_k,
        "repetition_penalty": repetition_penalty,
        "structural_guard_strength": structural_guard_strength,
    }


def _load_reference_smiles(dataset_name: str | None, csv_path: str | None, max_samples: int | None) -> tuple[list[str], str]:
    if csv_path:
        smiles = load_smiles_from_csv(csv_path)
        source = f"csv:{csv_path}"
    else:
        dataset = dataset_name or "moses"
        df = load_smiles_dataset(dataset, max_samples=max_samples)
        smiles = df["smiles"].astype(str).tolist()
        source = f"dataset:{dataset}"

    cleaned = []
    seen = set()
    for smiles_value in smiles:
        normalized = str(smiles_value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned, source


def _canonicalize_smiles(smiles: str, chem_module) -> str | None:
    if not smiles:
        return None
    try:
        mol = chem_module.MolFromSmiles(smiles)
        if mol is None or mol.GetNumAtoms() == 0:
            return None
        return chem_module.MolToSmiles(mol, canonical=True)
    except Exception:
        return None


def _score_smiles(smiles: str) -> dict[str, Any] | None:
    from scorer import generate_molecule_report

    with contextlib.redirect_stdout(io.StringIO()):
        report = generate_molecule_report(smiles)
    if report is None:
        return None

    return {
        "canonical_smiles": report["smiles"],
        "molecular_weight": report.get("molecular_weight"),
        "logp": report.get("logP"),
        "tpsa": report.get("tpsa"),
        "hbd": report.get("hbd"),
        "hba": report.get("hba"),
        "rotatable_bonds": report.get("rotatable_bonds"),
        "qed_score": report.get("qed_score"),
        "sa_score": report.get("sa_score"),
        "passes_lipinski": report.get("passes_lipinski"),
        "clinical_score": report.get("genorova_clinical_score"),
        "scorer_recommendation": report.get("recommendation"),
        "is_novel_scorer_flag": report.get("is_novel"),
    }


def _categorize_invalid_smiles(smiles: str) -> str:
    if not smiles:
        return "empty"
    if len(smiles) < 3:
        return "too_short"
    if smiles.count("(") != smiles.count(")"):
        return "unbalanced_parentheses"
    if smiles.count("[") != smiles.count("]"):
        return "unbalanced_brackets"
    ring_digits = re.findall(r"\d", smiles)
    if ring_digits:
        counts: dict[str, int] = {}
        for digit in ring_digits:
            counts[digit] = counts.get(digit, 0) + 1
        if any(count % 2 != 0 for count in counts.values()):
            return "ring_closure_mismatch"
    if len(set(smiles)) <= 2 and len(smiles) > 8:
        return "low_character_diversity"
    if re.fullmatch(r"[CcNnOoSs#=\-\(\)\[\]123456789]+", smiles or "") and len(smiles) > 20:
        return "long_repetitive_fragment"
    return "rdkit_parse_failure"


def _top_token_summary(decoded_rows: list[dict[str, Any]], idx2char: dict[int, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in decoded_rows:
        for token_id in row["effective_token_ids"]:
            token = idx2char.get(token_id, f"<{token_id}>")
            counts[token] = counts.get(token, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10])


def _safe_slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem)


def _common_value_counts(series: pd.Series, top_n: int = 10) -> dict[str, int]:
    clean = series.fillna("").astype(str).str.strip()
    clean = clean[clean != ""]
    if clean.empty:
        return {}
    return clean.value_counts().head(top_n).to_dict()


def _invalidity_breakdown(generated_df: pd.DataFrame) -> dict[str, Any]:
    invalid_df = generated_df[~generated_df["is_valid_rdkit"]].copy()
    invalid_total = int(invalid_df.shape[0])
    reason_counts = invalid_df["invalid_reason"].value_counts().to_dict() if invalid_total else {}
    reason_percentages = {
        reason: _pct(int(count), invalid_total)
        for reason, count in reason_counts.items()
    }

    invalid_lengths = pd.to_numeric(invalid_df.get("raw_length"), errors="coerce").dropna()
    breakdown = {
        "invalid_total": invalid_total,
        "invalid_reason_counts": reason_counts,
        "invalid_reason_percentages": reason_percentages,
        "average_invalid_length": round(float(invalid_lengths.mean()), 4) if not invalid_lengths.empty else None,
        "median_invalid_length": round(float(invalid_lengths.median()), 4) if not invalid_lengths.empty else None,
        "common_invalid_endings": _common_value_counts(invalid_df.get("ending_motif", pd.Series(dtype=str))),
        "common_invalid_last_tokens": _common_value_counts(invalid_df.get("last_non_special_token", pd.Series(dtype=str))),
        "mean_invalid_length_by_reason": {
            reason: round(float(group["raw_length"].mean()), 4)
            for reason, group in invalid_df.groupby("invalid_reason")
            if not group.empty
        } if invalid_total else {},
        "structural_residual_counts": {
            "nonzero_parenthesis_balance": int((pd.to_numeric(invalid_df.get("parenthesis_balance"), errors="coerce").fillna(0) != 0).sum()) if invalid_total else 0,
            "nonzero_bracket_balance": int((pd.to_numeric(invalid_df.get("bracket_balance"), errors="coerce").fillna(0) != 0).sum()) if invalid_total else 0,
            "nonzero_unmatched_ring_count": int((pd.to_numeric(invalid_df.get("unmatched_ring_count"), errors="coerce").fillna(0) != 0).sum()) if invalid_total else 0,
        },
    }
    return breakdown


def _ranking_tuple(row: pd.Series):
    avg_score = row["average_clinical_score"] if pd.notna(row["average_clinical_score"]) else -1.0
    best_score = row["best_clinical_score"] if pd.notna(row["best_clinical_score"]) else -1.0
    return (
        row["validity_pct"],
        row["unique_valid_count"],
        row["novelty_pct_of_unique_valid"],
        avg_score,
        best_score,
        row["valid_count"],
    )


def _summarize_numeric(df: pd.DataFrame, columns: list[str]) -> dict[str, dict[str, float] | None]:
    summary: dict[str, dict[str, float] | None] = {}
    for column in columns:
        series = pd.to_numeric(df[column], errors="coerce").dropna() if column in df.columns else pd.Series(dtype=float)
        if series.empty:
            summary[column] = None
            continue
        summary[column] = {
            "mean": round(float(series.mean()), 4),
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
        }
    return summary


def _markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "_No candidates available._"
    headers = columns
    rows = df.loc[:, columns].fillna("").astype(str).values.tolist()
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator, *body])


def _ratio_display(numerator: int, denominator: int) -> str:
    return f"{numerator} / {denominator}" if denominator else f"{numerator} / 0"


def _json_default(value: Any):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _as_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_filter_rules(
    *,
    qed_min: float,
    sa_max: float,
    mw_min: float,
    mw_max: float,
    logp_min: float,
    logp_max: float,
    require_lipinski: bool,
) -> dict[str, Any]:
    return {
        "qed_min": float(qed_min),
        "sa_max": float(sa_max),
        "mw_min": float(mw_min),
        "mw_max": float(mw_max),
        "logp_min": float(logp_min),
        "logp_max": float(logp_max),
        "require_lipinski": bool(require_lipinski),
    }


def _filter_reasons(row: pd.Series, filter_rules: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    qed_score = _as_float(row.get("qed_score"))
    sa_score = _as_float(row.get("sa_score"))
    molecular_weight = _as_float(row.get("molecular_weight"))
    logp = _as_float(row.get("logp"))
    lipinski = row.get("passes_lipinski")

    if filter_rules["require_lipinski"] and lipinski is not True:
        reasons.append("lipinski_fail")
    if qed_score is None:
        reasons.append("missing_qed")
    elif qed_score < filter_rules["qed_min"]:
        reasons.append("qed_below_threshold")
    if sa_score is None:
        reasons.append("missing_sa")
    elif sa_score > filter_rules["sa_max"]:
        reasons.append("sa_above_threshold")
    if molecular_weight is None:
        reasons.append("missing_molecular_weight")
    elif not (filter_rules["mw_min"] <= molecular_weight <= filter_rules["mw_max"]):
        reasons.append("mw_out_of_range")
    if logp is None:
        reasons.append("missing_logp")
    elif not (filter_rules["logp_min"] <= logp <= filter_rules["logp_max"]):
        reasons.append("logp_out_of_range")

    return reasons


def _apply_candidate_filters(
    unique_valid_df: pd.DataFrame,
    filter_rules: dict[str, Any],
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    candidate_df = unique_valid_df.copy()
    required_columns = [
        "canonical_smiles",
        "clinical_score",
        "qed_score",
        "sa_score",
        "molecular_weight",
        "logp",
        "tpsa",
        "passes_lipinski",
        "is_novel_vs_reference",
    ]
    for column in required_columns:
        if column not in candidate_df.columns:
            candidate_df[column] = None
    if candidate_df.empty:
        empty_df = pd.DataFrame(
            columns=required_columns + ["filter_status", "filter_reason"]
        )
        summary = {
            "thresholds": filter_rules,
            "unique_valid_candidates": 0,
            "filtered_candidate_count": 0,
            "filtered_candidate_pct_of_unique_valid": 0.0,
            "rejection_reason_counts": {},
            "top_filtered_candidates": [],
        }
        return empty_df, empty_df.copy(), summary

    candidate_df["filter_reasons"] = candidate_df.apply(
        lambda row: _filter_reasons(row, filter_rules),
        axis=1,
    )
    candidate_df["filter_status"] = candidate_df["filter_reasons"].map(
        lambda reasons: "filtered_in" if not reasons else "rejected"
    )
    candidate_df["filter_reason"] = candidate_df["filter_reasons"].map(
        lambda reasons: "passed_all_filters" if not reasons else ";".join(reasons)
    )
    candidate_df["research_status"] = candidate_df["filter_status"].map(
        lambda status: "filtered_computational_candidate"
        if status == "filtered_in"
        else "valid_generated_molecule_rejected_by_filters"
    )
    candidate_df["validation_status"] = "rdkit_valid_not_experimentally_validated"

    candidate_df = candidate_df.sort_values(
        by=["clinical_score", "qed_score", "is_novel_vs_reference"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)

    filtered_df = candidate_df[candidate_df["filter_status"] == "filtered_in"].copy()
    filtered_df = filtered_df.sort_values(
        by=["clinical_score", "qed_score", "is_novel_vs_reference"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)

    rejection_reason_counts: dict[str, int] = {}
    for reasons in candidate_df.loc[candidate_df["filter_status"] == "rejected", "filter_reasons"]:
        for reason in reasons:
            rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1

    top_filtered = filtered_df.head(top_n)[
        [
            "canonical_smiles",
            "clinical_score",
            "qed_score",
            "sa_score",
            "molecular_weight",
            "logp",
            "tpsa",
            "passes_lipinski",
            "is_novel_vs_reference",
            "filter_status",
            "filter_reason",
        ]
    ].copy()

    summary = {
        "thresholds": filter_rules,
        "unique_valid_candidates": int(candidate_df.shape[0]),
        "filtered_candidate_count": int(filtered_df.shape[0]),
        "filtered_candidate_pct_of_unique_valid": round(
            100.0 * filtered_df.shape[0] / max(1, candidate_df.shape[0]),
            2,
        ),
        "rejection_reason_counts": dict(sorted(rejection_reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "top_filtered_candidates": top_filtered.to_dict(orient="records"),
    }
    return candidate_df, filtered_df, summary


def evaluate_generation(
    checkpoint_path: Path,
    vocab_path: Path,
    num_samples: int,
    output_dir: Path,
    strategy: str,
    temperature: float,
    reference_dataset: str | None,
    reference_csv: str | None,
    reference_max_samples: int | None,
    top_n: int,
    seed: int,
    filter_rules: dict[str, Any],
    top_k: int,
    repetition_penalty: float,
    structural_guard_strength: float,
) -> dict[str, Any]:
    Chem, _, _ = _require_rdkit()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    output_dir.mkdir(parents=True, exist_ok=True)
    _set_seed(seed)

    reference_smiles, reference_source = _load_reference_smiles(
        dataset_name=reference_dataset,
        csv_path=reference_csv,
        max_samples=reference_max_samples,
    )
    reference_canonical = {
        canonical
        for canonical in (_canonicalize_smiles(smiles, Chem) for smiles in reference_smiles)
        if canonical is not None
    }

    model, checkpoint, char2idx, idx2char, max_length = _load_model(checkpoint_path, vocab_path, device)
    token_ids = get_special_token_ids(char2idx)

    if strategy == "guided":
        decoded_rows, latent_debug = _generate_guided(
            model=model,
            reference_smiles=reference_smiles,
            char2idx=char2idx,
            idx2char=idx2char,
            max_length=max_length,
            num_samples=num_samples,
            temperature=temperature,
            device=device,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            structural_guard_strength=structural_guard_strength,
        )
    else:
        decoded_rows, latent_debug = _generate_random(
            model=model,
            idx2char=idx2char,
            char2idx=char2idx,
            num_samples=num_samples,
            device=device,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            structural_guard_strength=structural_guard_strength,
            temperature=max(temperature, 0.2),
        )

    records: list[dict[str, Any]] = []
    canonical_counts: dict[str, int] = {}
    for index, row in enumerate(decoded_rows, start=1):
        smiles = row["raw_smiles"]
        canonical = _canonicalize_smiles(smiles, Chem)
        if canonical is not None:
            canonical_counts[canonical] = canonical_counts.get(canonical, 0) + 1
        records.append(
            {
                "sample_index": index,
                "raw_smiles": smiles,
                "raw_length": row["raw_length"],
                "first_bos_position": row["first_bos_position"],
                "first_eos_position": row["first_eos_position"],
                "first_pad_position": row["first_pad_position"],
                "termination_token": row["termination_token"],
                "termination_reason": row["termination_reason"],
                "raw_tokens": " ".join(row["raw_tokens"]),
                "effective_token_ids": " ".join(map(str, row["effective_token_ids"])),
                "last_non_special_token": row["last_non_special_token"],
                "ending_motif": row["ending_motif"],
                "parenthesis_balance": row["parenthesis_balance"],
                "bracket_balance": row["bracket_balance"],
                "unmatched_ring_digits": " ".join(row["unmatched_ring_digits"]),
                "unmatched_ring_count": row["unmatched_ring_count"],
                "max_parenthesis_depth": row["max_parenthesis_depth"],
                "max_bracket_depth": row["max_bracket_depth"],
                "canonical_smiles": canonical,
                "is_valid_rdkit": canonical is not None,
            }
        )

    generated_df = pd.DataFrame(records)
    if generated_df.empty:
        generated_df = pd.DataFrame(columns=["sample_index", "raw_smiles", "canonical_smiles", "is_valid_rdkit"])

    generated_df["is_unique_among_valid"] = generated_df["canonical_smiles"].map(
        lambda smiles: bool(smiles) and canonical_counts.get(smiles, 0) == 1
    )
    generated_df["valid_occurrences"] = generated_df["canonical_smiles"].map(lambda smiles: canonical_counts.get(smiles, 0) if smiles else 0)
    generated_df["is_novel_vs_reference"] = generated_df["canonical_smiles"].map(
        lambda smiles: bool(smiles) and smiles not in reference_canonical
    )
    generated_df["invalid_reason"] = generated_df.apply(
        lambda row: "" if row["is_valid_rdkit"] else _categorize_invalid_smiles(row["raw_smiles"]),
        axis=1,
    )

    valid_df = generated_df[generated_df["is_valid_rdkit"]].copy()
    unique_valid_df = valid_df.drop_duplicates(subset=["canonical_smiles"]).copy()

    scored_rows = []
    for smiles in unique_valid_df["canonical_smiles"].tolist():
        scored = _score_smiles(smiles)
        if scored is not None:
            scored_rows.append(scored)

    scored_df = pd.DataFrame(scored_rows)
    if not scored_df.empty:
        scored_df = scored_df.sort_values("clinical_score", ascending=False).reset_index(drop=True)
        generated_df = generated_df.merge(scored_df, on="canonical_smiles", how="left")
        valid_df = generated_df[generated_df["is_valid_rdkit"]].copy()
        unique_valid_df = valid_df.drop_duplicates(subset=["canonical_smiles"]).copy()

    all_valid_candidates_df, filtered_candidates_df, filtering_summary = _apply_candidate_filters(
        unique_valid_df=unique_valid_df,
        filter_rules=filter_rules,
        top_n=top_n,
    )

    valid_count = int(valid_df.shape[0])
    unique_valid_count = int(unique_valid_df.shape[0])
    novel_valid_count = int(valid_df["is_novel_vs_reference"].sum()) if valid_count else 0
    novel_unique_valid_count = int(unique_valid_df["is_novel_vs_reference"].sum()) if unique_valid_count else 0
    scored_unique_count = int(scored_df.shape[0])
    invalid_reason_counts = (
        generated_df.loc[~generated_df["is_valid_rdkit"], "invalid_reason"].value_counts().to_dict()
        if not generated_df.empty
        else {}
    )
    invalidity_breakdown = _invalidity_breakdown(generated_df)
    empty_count = int((generated_df["raw_smiles"].fillna("") == "").sum()) if not generated_df.empty else 0
    non_empty_lengths = generated_df["raw_length"].dropna() if "raw_length" in generated_df.columns else pd.Series(dtype=float)

    metrics = {
        "generated_at": datetime.now().isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "vocab_path": str(vocab_path),
        "device": str(device),
        "generation_strategy": strategy,
        "temperature": temperature,
        "top_k": int(top_k),
        "repetition_penalty": float(repetition_penalty),
        "structural_guard_strength": float(structural_guard_strength),
        "seed": seed,
        "requested_samples": int(num_samples),
        "reference_source": reference_source,
        "reference_canonical_size": int(len(reference_canonical)),
        "checkpoint_epoch": int(checkpoint.get("epoch", 0)),
        "checkpoint_best_val_loss": checkpoint.get("best_val_loss"),
        "checkpoint_stage_name": checkpoint.get("stage_name"),
        "checkpoint_source_label": checkpoint.get("source_label"),
        "checkpoint_mu_std": checkpoint.get("mu_std"),
        "model_max_length": int(max_length),
        "resolved_vocab_size": len(char2idx),
        "counts": {
            "total_generated": int(len(generated_df)),
            "valid_rdkit": valid_count,
            "invalid_rdkit": int(len(generated_df) - valid_count),
            "unique_valid": unique_valid_count,
            "novel_valid": novel_valid_count,
            "novel_unique_valid": novel_unique_valid_count,
            "scored_unique_valid": scored_unique_count,
        },
        "rates": {
            "validity_pct": round(100.0 * valid_count / max(1, len(generated_df)), 2),
            "uniqueness_pct_of_valid": round(100.0 * unique_valid_count / max(1, valid_count), 2),
            "novelty_pct_of_valid": round(100.0 * novel_valid_count / max(1, valid_count), 2),
            "novelty_pct_of_unique_valid": round(100.0 * novel_unique_valid_count / max(1, unique_valid_count), 2),
        },
        "length_summary_raw_strings": {
            "mean": round(float(non_empty_lengths.mean()), 4) if not non_empty_lengths.empty else None,
            "min": round(float(non_empty_lengths.min()), 4) if not non_empty_lengths.empty else None,
            "max": round(float(non_empty_lengths.max()), 4) if not non_empty_lengths.empty else None,
        },
        "debug_summary": {
            "empty_string_count": empty_count,
            "empty_string_pct": _pct(empty_count, int(len(generated_df))),
            "eos_terminated_count": int(sum(1 for row in decoded_rows if row["termination_reason"] == "eos")),
            "pad_terminated_count": int(sum(1 for row in decoded_rows if row["termination_reason"] == "pad")),
            "missing_bos_count": int(sum(1 for row in decoded_rows if row["first_bos_position"] is None and BOS_TOKEN in char2idx)),
            "missing_eos_count": int(sum(1 for row in decoded_rows if row["first_eos_position"] is None and EOS_TOKEN in char2idx)),
            "invalid_reason_counts": invalid_reason_counts,
            "invalidity_breakdown": invalidity_breakdown,
            "top_decoded_tokens": _top_token_summary(decoded_rows, idx2char),
            "latent_debug": latent_debug,
            "special_token_ids": token_ids,
        },
        "property_summary_valid_rows": _summarize_numeric(
            valid_df,
            ["molecular_weight", "logp", "tpsa", "hbd", "hba", "rotatable_bonds", "qed_score", "sa_score"],
        ),
        "scoring_summary_unique_valid": {
            "average_clinical_score": round(float(scored_df["clinical_score"].mean()), 4) if not scored_df.empty else None,
            "best_clinical_score": round(float(scored_df["clinical_score"].max()), 4) if not scored_df.empty else None,
            "top_n": top_n,
        },
        "filtering_summary": filtering_summary,
    }

    top_candidates = (
        scored_df.head(top_n)[
            [
                "canonical_smiles",
                "clinical_score",
                "scorer_recommendation",
                "qed_score",
                "sa_score",
                "molecular_weight",
                "logp",
                "tpsa",
                "passes_lipinski",
            ]
        ].copy()
        if not scored_df.empty
        else pd.DataFrame(
            columns=[
                "canonical_smiles",
                "clinical_score",
                "scorer_recommendation",
                "qed_score",
                "sa_score",
                "molecular_weight",
                "logp",
                "tpsa",
                "passes_lipinski",
            ]
        )
    )
    metrics["top_candidates"] = top_candidates.to_dict(orient="records")
    metrics["top_filtered_candidates"] = filtering_summary["top_filtered_candidates"]

    generated_csv = output_dir / "generated_molecules.csv"
    all_valid_csv = output_dir / "all_valid_candidates.csv"
    filtered_csv = output_dir / "filtered_candidates.csv"
    top_candidates_csv = output_dir / "top_candidates_report.csv"
    metrics_json = output_dir / "evaluation_metrics.json"
    summary_md = output_dir / "evaluation_summary.md"
    debug_csv = output_dir / "debug_decoding_samples.csv"
    debug_json = output_dir / "debug_summary.json"
    invalidity_json = output_dir / "invalidity_breakdown.json"
    filter_json = output_dir / "candidate_filtering_summary.json"
    filter_md = output_dir / "candidate_filtering_summary.md"

    generated_df.to_csv(generated_csv, index=False)
    all_valid_candidates_df.drop(columns=["filter_reasons"], errors="ignore").to_csv(all_valid_csv, index=False)
    filtered_candidates_df.drop(columns=["filter_reasons"], errors="ignore").to_csv(filtered_csv, index=False)
    top_report_df = (
        filtered_candidates_df.head(top_n).copy()
        if not filtered_candidates_df.empty
        else all_valid_candidates_df.head(top_n).copy()
    )
    top_report_df.drop(columns=["filter_reasons"], errors="ignore").to_csv(top_candidates_csv, index=False)
    pd.DataFrame(decoded_rows).head(50).assign(
        token_ids=lambda df: df["token_ids"].map(lambda values: " ".join(map(str, values))),
        raw_tokens=lambda df: df["raw_tokens"].map(lambda values: " ".join(values)),
        effective_token_ids=lambda df: df["effective_token_ids"].map(lambda values: " ".join(map(str, values))),
        unmatched_ring_digits=lambda df: df["unmatched_ring_digits"].map(lambda values: " ".join(values)),
    ).to_csv(debug_csv, index=False)
    metrics_json.write_text(json.dumps(metrics, indent=2, default=_json_default), encoding="utf-8")
    debug_json.write_text(json.dumps(metrics["debug_summary"], indent=2, default=_json_default), encoding="utf-8")
    invalidity_json.write_text(json.dumps(invalidity_breakdown, indent=2, default=_json_default), encoding="utf-8")
    filter_json.write_text(json.dumps(filtering_summary, indent=2, default=_json_default), encoding="utf-8")

    caveats = [
        "These are computationally generated candidates, not experimentally validated molecules.",
        "Validity here means RDKit-parsable SMILES, not biological activity or synthetic feasibility in the lab.",
        "Clinical scores are heuristic outputs from the current Genorova scorer and should be treated as research-support signals.",
    ]
    avg_score_display = metrics["scoring_summary_unique_valid"]["average_clinical_score"]
    best_score_display = metrics["scoring_summary_unique_valid"]["best_clinical_score"]
    summary_text = "\n".join(
        [
            "# Generation Evaluation Summary",
            "",
            "## Run Metadata",
            "",
            f"- Checkpoint: `{checkpoint_path}`",
            f"- Vocabulary: `{vocab_path}`",
            f"- Strategy: `{strategy}`",
            f"- Temperature: `{temperature}`",
            f"- Top-k: `{top_k}`",
            f"- Repetition penalty: `{repetition_penalty}`",
            f"- Structural guard strength: `{structural_guard_strength}`",
            f"- Requested samples: `{num_samples}`",
            f"- Reference source for novelty: `{reference_source}`",
            f"- Checkpoint stage: `{checkpoint.get('stage_name')}`",
            f"- Candidate filter thresholds: `{json.dumps(filter_rules, sort_keys=True)}`",
            "",
            "## Core Metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Valid RDKit SMILES | {_ratio_display(valid_count, len(generated_df))} |",
            f"| Validity | {metrics['rates']['validity_pct']}% |",
            f"| Unique valid molecules | {_ratio_display(unique_valid_count, valid_count)} |",
            f"| Uniqueness among valid | {metrics['rates']['uniqueness_pct_of_valid']}% |",
            f"| Novel valid molecules | {_ratio_display(novel_valid_count, valid_count)} |",
            f"| Novelty among valid | {metrics['rates']['novelty_pct_of_valid']}% |",
            f"| Novel unique molecules | {_ratio_display(novel_unique_valid_count, unique_valid_count)} |",
            f"| Novelty among unique valid | {metrics['rates']['novelty_pct_of_unique_valid']}% |",
            f"| Average clinical score (unique valid) | {avg_score_display if avg_score_display is not None else 'N/A'} |",
            f"| Best clinical score (unique valid) | {best_score_display if best_score_display is not None else 'N/A'} |",
            "",
            "## Filtering Summary",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Unique valid candidate pool | {filtering_summary['unique_valid_candidates']} |",
            f"| Filtered computational candidates | {filtering_summary['filtered_candidate_count']} |",
            f"| Filter pass rate | {filtering_summary['filtered_candidate_pct_of_unique_valid']}% |",
            f"| Rejection reasons | `{filtering_summary['rejection_reason_counts']}` |",
            "",
            "## Top Filtered Computational Candidates",
            "",
            _markdown_table(
                filtered_candidates_df.head(top_n),
                [
                    "canonical_smiles",
                    "clinical_score",
                    "qed_score",
                    "sa_score",
                    "molecular_weight",
                    "logp",
                    "passes_lipinski",
                    "filter_reason",
                ],
            ),
            "",
            "## Top Scored Valid Molecules",
            "",
            _markdown_table(
                top_candidates,
                [
                    "canonical_smiles",
                    "clinical_score",
                    "scorer_recommendation",
                    "qed_score",
                    "sa_score",
                    "molecular_weight",
                    "logp",
                ],
            ),
            "",
            "## Caveats",
            "",
            *(f"- {line}" for line in caveats),
            "",
            "## Debug Snapshot",
            "",
            f"- Empty decoded strings: `{metrics['debug_summary']['empty_string_count']}`",
            f"- Top invalid reasons: `{metrics['debug_summary']['invalid_reason_counts']}`",
            f"- Invalid reason percentages: `{invalidity_breakdown['invalid_reason_percentages']}`",
            f"- Avg invalid length: `{invalidity_breakdown['average_invalid_length']}`",
            f"- Common invalid endings: `{invalidity_breakdown['common_invalid_endings']}`",
            f"- Top decoded tokens: `{metrics['debug_summary']['top_decoded_tokens']}`",
            "",
        ]
    )
    summary_md.write_text(summary_text, encoding="utf-8")
    filter_md.write_text(
        "\n".join(
            [
                "# Candidate Filtering Summary",
                "",
                "These are filtered computational candidates for research support only, not experimentally validated drug leads.",
                "",
                "## Thresholds",
                "",
                f"- QED minimum: `{filter_rules['qed_min']}`",
                f"- SA maximum: `{filter_rules['sa_max']}`",
                f"- Molecular weight range: `{filter_rules['mw_min']} - {filter_rules['mw_max']}` Da",
                f"- LogP range: `{filter_rules['logp_min']} - {filter_rules['logp_max']}`",
                f"- Require Lipinski pass: `{filter_rules['require_lipinski']}`",
                "",
                "## Summary",
                "",
                f"- Unique valid generated molecules: `{filtering_summary['unique_valid_candidates']}`",
                f"- Filtered computational candidates: `{filtering_summary['filtered_candidate_count']}`",
                f"- Filter pass rate: `{filtering_summary['filtered_candidate_pct_of_unique_valid']}%`",
                f"- Rejection reason counts: `{filtering_summary['rejection_reason_counts']}`",
                "",
                "## Top Filtered Candidates",
                "",
                _markdown_table(
                    filtered_candidates_df.head(top_n),
                    [
                        "canonical_smiles",
                        "clinical_score",
                        "qed_score",
                        "sa_score",
                        "molecular_weight",
                        "logp",
                        "passes_lipinski",
                    ],
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "generated_csv": generated_csv,
        "all_valid_csv": all_valid_csv,
        "filtered_csv": filtered_csv,
        "top_candidates_csv": top_candidates_csv,
        "metrics_json": metrics_json,
        "summary_md": summary_md,
        "debug_csv": debug_csv,
        "debug_json": debug_json,
        "invalidity_json": invalidity_json,
        "filter_json": filter_json,
        "filter_md": filter_md,
        "metrics": metrics,
    }


def compare_checkpoints(
    checkpoint_paths: list[Path],
    output_dir: Path,
    num_samples: int,
    strategy: str,
    temperature: float,
    reference_dataset: str | None,
    reference_csv: str | None,
    reference_max_samples: int | None,
    top_n: int,
    seed: int,
    filter_rules: dict[str, Any],
    top_k: int,
    repetition_penalty: float,
    structural_guard_strength: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    metrics_payload = []

    for checkpoint_path in checkpoint_paths:
        vocab_path = _resolve_default_vocab(checkpoint_path)
        checkpoint_dir = output_dir / _safe_slug(checkpoint_path)
        result = evaluate_generation(
            checkpoint_path=checkpoint_path,
            vocab_path=vocab_path,
            num_samples=num_samples,
            output_dir=checkpoint_dir,
            strategy=strategy,
            temperature=temperature,
            reference_dataset=reference_dataset,
            reference_csv=reference_csv,
            reference_max_samples=reference_max_samples,
            top_n=top_n,
            seed=seed,
            filter_rules=filter_rules,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            structural_guard_strength=structural_guard_strength,
        )
        metrics = result["metrics"]
        row = {
            "checkpoint_name": checkpoint_path.name,
            "checkpoint_path": str(checkpoint_path),
            "vocab_path": str(vocab_path),
            "stage_name": metrics.get("checkpoint_stage_name"),
            "epoch": metrics.get("checkpoint_epoch"),
            "best_val_loss": metrics.get("checkpoint_best_val_loss"),
            "validity_pct": metrics["rates"]["validity_pct"],
            "uniqueness_pct_of_valid": metrics["rates"]["uniqueness_pct_of_valid"],
            "novelty_pct_of_valid": metrics["rates"]["novelty_pct_of_valid"],
            "novelty_pct_of_unique_valid": metrics["rates"]["novelty_pct_of_unique_valid"],
            "valid_count": metrics["counts"]["valid_rdkit"],
            "unique_valid_count": metrics["counts"]["unique_valid"],
            "filtered_candidate_count": metrics["filtering_summary"]["filtered_candidate_count"],
            "filtered_candidate_pct_of_unique_valid": metrics["filtering_summary"]["filtered_candidate_pct_of_unique_valid"],
            "average_clinical_score": metrics["scoring_summary_unique_valid"]["average_clinical_score"],
            "best_clinical_score": metrics["scoring_summary_unique_valid"]["best_clinical_score"],
            "output_dir": str(checkpoint_dir),
            "top_invalid_reasons": json.dumps(metrics["debug_summary"]["invalid_reason_counts"]),
            "common_invalid_endings": json.dumps(metrics["debug_summary"]["invalidity_breakdown"]["common_invalid_endings"]),
            "top_decoded_tokens": json.dumps(metrics["debug_summary"]["top_decoded_tokens"]),
        }
        rows.append(row)
        metrics_payload.append(metrics)

    comparison_df = pd.DataFrame(rows)
    if not comparison_df.empty:
        comparison_df = comparison_df.sort_values(
            by=[
                "validity_pct",
                "filtered_candidate_count",
                "unique_valid_count",
                "novelty_pct_of_unique_valid",
                "average_clinical_score",
                "best_clinical_score",
                "valid_count",
            ],
            ascending=[False, False, False, False, False, False, False],
            na_position="last",
        ).reset_index(drop=True)
        comparison_df.index = comparison_df.index + 1
        comparison_df.insert(0, "rank", comparison_df.index)

    comparison_csv = output_dir / "checkpoint_comparison.csv"
    metrics_json = output_dir / "checkpoint_metrics.json"
    ranking_md = output_dir / "checkpoint_ranking.md"
    comparison_df.to_csv(comparison_csv, index=False)
    best_line = "_No checkpoints evaluated._"
    best_validity_line = "_No checkpoints evaluated._"
    best_score_line = "_No scored valid molecules were produced._"
    stage_line = "_Stage comparison unavailable._"
    stage_summary_rows: list[dict[str, Any]] = []

    if not comparison_df.empty:
        best = comparison_df.iloc[0]
        if float(best["validity_pct"]) == 0.0 and int(best["unique_valid_count"]) == 0:
            best_line = (
                "All evaluated checkpoints were tied at 0% validity in this run. "
                f"`{best['checkpoint_name']}` is listed first only by the ranking sort order, not because it produced usable molecules."
            )
        else:
            best_line = (
                f"`{best['checkpoint_name']}` ranked first because it led on validity "
                f"({best['validity_pct']}%), then unique valid molecule count ({best['unique_valid_count']}), "
                f"with average score `{best['average_clinical_score']}`."
            )

        best_validity = comparison_df.sort_values(
            by=["validity_pct", "unique_valid_count", "valid_count"],
            ascending=[False, False, False],
            na_position="last",
        ).iloc[0]
        best_validity_line = (
            f"`{best_validity['checkpoint_name']}` had the strongest validity result "
            f"at `{best_validity['validity_pct']}%` "
            f"({best_validity['valid_count']} valid / {num_samples} requested)."
        )

        score_df = comparison_df.dropna(subset=["average_clinical_score", "best_clinical_score"]).copy()
        if not score_df.empty:
            best_score = score_df.sort_values(
                by=["average_clinical_score", "best_clinical_score", "filtered_candidate_count"],
                ascending=[False, False, False],
                na_position="last",
            ).iloc[0]
            best_score_line = (
                f"`{best_score['checkpoint_name']}` had the strongest score profile "
                f"with average score `{best_score['average_clinical_score']}` and best score "
                f"`{best_score['best_clinical_score']}`."
            )

        for stage_name in ["pretrain", "finetune"]:
            stage_df = comparison_df[comparison_df["stage_name"] == stage_name].copy()
            if stage_df.empty:
                continue
            stage_best = stage_df.sort_values(
                by=[
                    "validity_pct",
                    "filtered_candidate_count",
                    "unique_valid_count",
                    "novelty_pct_of_unique_valid",
                    "average_clinical_score",
                    "best_clinical_score",
                ],
                ascending=[False, False, False, False, False, False],
                na_position="last",
            ).iloc[0]
            stage_summary_rows.append(
                {
                    "stage_name": stage_name,
                    "best_checkpoint": stage_best["checkpoint_name"],
                    "best_validity_pct": stage_best["validity_pct"],
                    "best_filtered_candidate_count": stage_best["filtered_candidate_count"],
                    "best_average_clinical_score": stage_best["average_clinical_score"],
                }
            )

        if len(stage_summary_rows) == 2:
            stage_lookup = {row["stage_name"]: row for row in stage_summary_rows}
            pretrain = stage_lookup["pretrain"]
            finetune = stage_lookup["finetune"]
            if comparison_df.iloc[0]["stage_name"] == "finetune":
                stage_line = (
                    "Fine-tuning is currently stronger under this controlled setting because the highest-ranked checkpoint "
                    f"is `{comparison_df.iloc[0]['checkpoint_name']}`."
                )
            elif comparison_df.iloc[0]["stage_name"] == "pretrain":
                stage_line = (
                    "Pretraining is currently stronger under this controlled setting because the highest-ranked checkpoint "
                    f"is `{comparison_df.iloc[0]['checkpoint_name']}`."
                )
            else:
                stage_line = (
                    "Pretrain versus fine-tune is inconclusive under this run because the best checkpoint did not carry stage metadata."
                )
            stage_line += (
                f" Best pretrain validity: `{pretrain['best_validity_pct']}%`; "
                f"best fine-tune validity: `{finetune['best_validity_pct']}%`."
            )

    metrics_payload_obj = {
        "comparison_settings": {
            "strategy": strategy,
            "temperature": temperature,
            "top_k": top_k,
            "repetition_penalty": repetition_penalty,
            "structural_guard_strength": structural_guard_strength,
            "num_samples": num_samples,
            "reference_source": reference_csv or reference_dataset,
            "seed": seed,
            "filter_rules": filter_rules,
        },
        "stage_summary": stage_summary_rows,
        "checkpoints": metrics_payload,
    }
    metrics_json.write_text(json.dumps(metrics_payload_obj, indent=2, default=_json_default), encoding="utf-8")

    ranking_md.write_text(
        "\n".join(
            [
                "# Checkpoint Ranking",
                "",
                f"- Strategy: `{strategy}`",
                f"- Temperature: `{temperature}`",
                f"- Top-k: `{top_k}`",
                f"- Repetition penalty: `{repetition_penalty}`",
                f"- Structural guard strength: `{structural_guard_strength}`",
                f"- Samples per checkpoint: `{num_samples}`",
                f"- Reference source: `{reference_csv or reference_dataset}`",
                f"- Candidate filters: `{json.dumps(filter_rules, sort_keys=True)}`",
                "",
                "## Best Current Checkpoint",
                "",
                best_line,
                "",
                "## Best For Validity",
                "",
                best_validity_line,
                "",
                "## Best For Score Quality",
                "",
                best_score_line,
                "",
                "## Pretrain vs Fine-tune",
                "",
                stage_line,
                "",
                "## Ranking Table",
                "",
                _markdown_table(
                    comparison_df,
                    [
                        "rank",
                        "checkpoint_name",
                        "validity_pct",
                        "filtered_candidate_count",
                        "unique_valid_count",
                        "novelty_pct_of_unique_valid",
                        "average_clinical_score",
                        "best_clinical_score",
                    ],
                ) if not comparison_df.empty else "_No checkpoints evaluated._",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "comparison_csv": comparison_csv,
        "metrics_json": metrics_json,
        "ranking_md": ranking_md,
        "comparison_df": comparison_df,
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Evaluate the quality of molecules generated by a trained Genorova VAE.")
    parser.add_argument("--use-winning-baseline", action="store_true", help="Use the current best known repaired baseline: diabetes finetune best + guided + temperature 0.3 + diabetes reference CSV.")
    parser.add_argument("--checkpoint", default=None, help="Path to a trained checkpoint. Defaults to the best available model.")
    parser.add_argument("--checkpoints", nargs="+", default=None, help="Evaluate multiple checkpoint paths in one run.")
    parser.add_argument("--vocab", default=None, help="Path to the vocabulary JSON. Defaults to the best match for the checkpoint.")
    parser.add_argument("--num-samples", type=int, default=100, help="How many molecules to generate for evaluation.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for generated evaluation artifacts. Defaults to genorova/outputs/evaluation/<timestamp>/",
    )
    parser.add_argument(
        "--strategy",
        choices=["guided", "random"],
        default="guided",
        help="Use guided latent sampling from a reference set or pure random latent sampling.",
    )
    parser.add_argument("--temperature", type=float, default=0.3, help="Noise scale used for guided generation.")
    parser.add_argument(
        "--reference-dataset",
        default="moses",
        choices=["moses", "chembl_subset"],
        help="Shared dataset used for novelty checking and guided generation when --reference-csv is not supplied.",
    )
    parser.add_argument("--reference-csv", default=None, help="Optional CSV of reference/training SMILES for novelty checking.")
    parser.add_argument("--reference-max-samples", type=int, default=50000, help="Cap for shared reference dataset loading.")
    parser.add_argument("--top-n", type=int, default=10, help="How many top scored candidates to include in the summary.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible latent sampling.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Top-k token filtering for decode-time sampling.")
    parser.add_argument("--repetition-penalty", type=float, default=DEFAULT_REPETITION_PENALTY, help="Penalty applied to repeating the previous token during decoding.")
    parser.add_argument("--structural-guard-strength", type=float, default=DEFAULT_STRUCTURAL_GUARD_STRENGTH, help="Decode-time structural guard strength. Set to 0 to disable the new guard logic.")
    parser.add_argument("--filter-qed-min", type=float, default=DEFAULT_FILTERS["qed_min"], help="Minimum QED for filtered computational candidates.")
    parser.add_argument("--filter-sa-max", type=float, default=DEFAULT_FILTERS["sa_max"], help="Maximum SA score for filtered computational candidates.")
    parser.add_argument("--filter-mw-min", type=float, default=DEFAULT_FILTERS["mw_min"], help="Minimum molecular weight for filtered computational candidates.")
    parser.add_argument("--filter-mw-max", type=float, default=DEFAULT_FILTERS["mw_max"], help="Maximum molecular weight for filtered computational candidates.")
    parser.add_argument("--filter-logp-min", type=float, default=DEFAULT_FILTERS["logp_min"], help="Minimum LogP for filtered computational candidates.")
    parser.add_argument("--filter-logp-max", type=float, default=DEFAULT_FILTERS["logp_max"], help="Maximum LogP for filtered computational candidates.")
    return parser


def main():
    args = build_parser().parse_args()
    if args.use_winning_baseline:
        if args.checkpoints is None and args.checkpoint is None:
            args.checkpoint = str(WINNING_BASELINE_CHECKPOINT)
        args.strategy = "guided"
        args.temperature = 0.3
        if args.reference_csv is None:
            args.reference_csv = str(WINNING_BASELINE_REFERENCE_CSV)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else EVAL_OUTPUT_DIR / f"generation_eval_{timestamp}"
    filter_rules = _build_filter_rules(
        qed_min=args.filter_qed_min,
        sa_max=args.filter_sa_max,
        mw_min=args.filter_mw_min,
        mw_max=args.filter_mw_max,
        logp_min=args.filter_logp_min,
        logp_max=args.filter_logp_max,
        require_lipinski=DEFAULT_FILTERS["require_lipinski"],
    )
    if args.checkpoints:
        checkpoint_paths = [Path(path) for path in args.checkpoints]
        results = compare_checkpoints(
            checkpoint_paths=checkpoint_paths,
            output_dir=output_dir,
            num_samples=args.num_samples,
            strategy=args.strategy,
            temperature=args.temperature,
            reference_dataset=args.reference_dataset,
            reference_csv=args.reference_csv,
            reference_max_samples=args.reference_max_samples,
            top_n=args.top_n,
            seed=args.seed,
            filter_rules=filter_rules,
            top_k=args.top_k,
            repetition_penalty=args.repetition_penalty,
            structural_guard_strength=args.structural_guard_strength,
        )
        print("\n" + "=" * 72)
        print("MULTI-CHECKPOINT EVALUATION COMPLETE")
        print("=" * 72)
        if not results["comparison_df"].empty:
            best = results["comparison_df"].iloc[0]
            print(f"Best checkpoint:   {best['checkpoint_name']}")
            print(f"Validity:          {best['validity_pct']}%")
            print(f"Filtered count:    {best['filtered_candidate_count']}")
            print(f"Unique valid:      {best['unique_valid_count']}")
            print(f"Avg score:         {best['average_clinical_score']}")
        print(f"Artifacts:         {results['comparison_csv']}")
        print(f"                   {results['metrics_json']}")
        print(f"                   {results['ranking_md']}")
        return

    checkpoint_path = Path(args.checkpoint) if args.checkpoint else _resolve_default_checkpoint()
    vocab_path = Path(args.vocab) if args.vocab else _resolve_default_vocab(checkpoint_path)

    results = evaluate_generation(
        checkpoint_path=checkpoint_path,
        vocab_path=vocab_path,
        num_samples=args.num_samples,
        output_dir=output_dir,
        strategy=args.strategy,
        temperature=args.temperature,
        reference_dataset=args.reference_dataset,
        reference_csv=args.reference_csv,
        reference_max_samples=args.reference_max_samples,
        top_n=args.top_n,
        seed=args.seed,
        filter_rules=filter_rules,
        top_k=args.top_k,
        repetition_penalty=args.repetition_penalty,
        structural_guard_strength=args.structural_guard_strength,
    )

    metrics = results["metrics"]
    print("\n" + "=" * 72)
    print("GENERATION EVALUATION COMPLETE")
    print("=" * 72)
    print(f"Requested samples: {metrics['requested_samples']}")
    print(f"Validity:          {metrics['rates']['validity_pct']}%")
    print(f"Top-k:             {metrics['top_k']}")
    print(f"Rep penalty:       {metrics['repetition_penalty']}")
    print(f"Guard strength:    {metrics['structural_guard_strength']}")
    print(f"Uniqueness:        {metrics['rates']['uniqueness_pct_of_valid']}% of valid")
    print(f"Novelty:           {metrics['rates']['novelty_pct_of_valid']}% of valid")
    print(f"Filtered pass:     {metrics['filtering_summary']['filtered_candidate_pct_of_unique_valid']}% of unique valid")
    print(f"Avg score:         {metrics['scoring_summary_unique_valid']['average_clinical_score']}")
    print(f"Best score:        {metrics['scoring_summary_unique_valid']['best_clinical_score']}")
    print(f"Artifacts:         {results['generated_csv']}")
    print(f"                   {results['all_valid_csv']}")
    print(f"                   {results['filtered_csv']}")
    print(f"                   {results['top_candidates_csv']}")
    print(f"                   {results['metrics_json']}")
    print(f"                   {results['summary_md']}")
    print(f"                   {results['debug_csv']}")
    print(f"                   {results['debug_json']}")
    print(f"                   {results['invalidity_json']}")
    print(f"                   {results['filter_json']}")
    print(f"                   {results['filter_md']}")


if __name__ == "__main__":
    main()
