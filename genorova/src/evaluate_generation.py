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
):
    with torch.no_grad():
        z = torch.randn(num_samples, LATENT_DIM, device=device)
        recon = model.decode(z)
        indices = select_token_ids_from_logits(
            recon,
            char2idx,
            temperature=1.0,
            strategy="greedy",
            repetition_penalty=0.75,
            min_tokens_before_stop=2,
        )
    decoded = _decode_with_debug(indices, idx2char, char2idx)
    return decoded, {"latent_source": "random", "latent_std": round(float(z.std().item()), 6)}


def _generate_guided(
    model: VAE,
    reference_smiles: list[str],
    char2idx: dict[str, int],
    idx2char: dict[int, str],
    max_length: int,
    num_samples: int,
    temperature: float,
    device: torch.device,
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
                top_k=5,
                repetition_penalty=0.75,
                min_tokens_before_stop=2,
            )
            generated.extend(_decode_with_debug(indices, idx2char, char2idx))

    return generated, {
        "latent_source": "guided",
        "anchor_count": len(reference_smiles),
        "anchor_mu_std": round(mu_std, 6),
        "anchor_mu_mean_abs": round(mu_mean_abs, 6),
        "temperature": temperature,
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
        "recommendation": report.get("recommendation"),
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
        )
    else:
        decoded_rows, latent_debug = _generate_random(
            model=model,
            idx2char=idx2char,
            char2idx=char2idx,
            num_samples=num_samples,
            device=device,
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
    empty_count = int((generated_df["raw_smiles"].fillna("") == "").sum()) if not generated_df.empty else 0
    non_empty_lengths = generated_df["raw_length"].dropna() if "raw_length" in generated_df.columns else pd.Series(dtype=float)

    metrics = {
        "generated_at": datetime.now().isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "vocab_path": str(vocab_path),
        "device": str(device),
        "generation_strategy": strategy,
        "temperature": temperature,
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
            "eos_terminated_count": int(sum(1 for row in decoded_rows if row["termination_reason"] == "eos")),
            "pad_terminated_count": int(sum(1 for row in decoded_rows if row["termination_reason"] == "pad")),
            "missing_bos_count": int(sum(1 for row in decoded_rows if row["first_bos_position"] is None and BOS_TOKEN in char2idx)),
            "missing_eos_count": int(sum(1 for row in decoded_rows if row["first_eos_position"] is None and EOS_TOKEN in char2idx)),
            "invalid_reason_counts": invalid_reason_counts,
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
    }

    top_candidates = (
        scored_df.head(top_n)[
            [
                "canonical_smiles",
                "clinical_score",
                "recommendation",
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
                "recommendation",
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

    generated_csv = output_dir / "generated_molecules.csv"
    metrics_json = output_dir / "evaluation_metrics.json"
    summary_md = output_dir / "evaluation_summary.md"
    debug_csv = output_dir / "debug_decoding_samples.csv"
    debug_json = output_dir / "debug_summary.json"

    generated_df.to_csv(generated_csv, index=False)
    pd.DataFrame(decoded_rows).head(50).assign(
        token_ids=lambda df: df["token_ids"].map(lambda values: " ".join(map(str, values))),
        raw_tokens=lambda df: df["raw_tokens"].map(lambda values: " ".join(values)),
        effective_token_ids=lambda df: df["effective_token_ids"].map(lambda values: " ".join(map(str, values))),
    ).to_csv(debug_csv, index=False)
    metrics_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    debug_json.write_text(json.dumps(metrics["debug_summary"], indent=2), encoding="utf-8")

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
            f"- Requested samples: `{num_samples}`",
            f"- Reference source for novelty: `{reference_source}`",
            f"- Checkpoint stage: `{checkpoint.get('stage_name')}`",
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
            "## Top Candidates",
            "",
            _markdown_table(
                top_candidates,
                [
                    "canonical_smiles",
                    "clinical_score",
                    "recommendation",
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
            f"- Top decoded tokens: `{metrics['debug_summary']['top_decoded_tokens']}`",
            "",
        ]
    )
    summary_md.write_text(summary_text, encoding="utf-8")

    return {
        "generated_csv": generated_csv,
        "metrics_json": metrics_json,
        "summary_md": summary_md,
        "debug_csv": debug_csv,
        "debug_json": debug_json,
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
            "average_clinical_score": metrics["scoring_summary_unique_valid"]["average_clinical_score"],
            "best_clinical_score": metrics["scoring_summary_unique_valid"]["best_clinical_score"],
            "output_dir": str(checkpoint_dir),
            "top_invalid_reasons": json.dumps(metrics["debug_summary"]["invalid_reason_counts"]),
            "top_decoded_tokens": json.dumps(metrics["debug_summary"]["top_decoded_tokens"]),
        }
        rows.append(row)
        metrics_payload.append(metrics)

    comparison_df = pd.DataFrame(rows)
    if not comparison_df.empty:
        comparison_df = comparison_df.sort_values(
            by=[
                "validity_pct",
                "unique_valid_count",
                "novelty_pct_of_unique_valid",
                "average_clinical_score",
                "best_clinical_score",
                "valid_count",
            ],
            ascending=[False, False, False, False, False, False],
            na_position="last",
        ).reset_index(drop=True)
        comparison_df.index = comparison_df.index + 1
        comparison_df.insert(0, "rank", comparison_df.index)

    comparison_csv = output_dir / "checkpoint_comparison.csv"
    metrics_json = output_dir / "checkpoint_metrics.json"
    ranking_md = output_dir / "checkpoint_ranking.md"
    comparison_df.to_csv(comparison_csv, index=False)
    metrics_json.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    best_line = "_No checkpoints evaluated._"
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

    ranking_md.write_text(
        "\n".join(
            [
                "# Checkpoint Ranking",
                "",
                f"- Strategy: `{strategy}`",
                f"- Temperature: `{temperature}`",
                f"- Samples per checkpoint: `{num_samples}`",
                f"- Reference source: `{reference_csv or reference_dataset}`",
                "",
                "## Best Current Checkpoint",
                "",
                best_line,
                "",
                "## Ranking Table",
                "",
                _markdown_table(
                    comparison_df,
                    [
                        "rank",
                        "checkpoint_name",
                        "validity_pct",
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
    return parser


def main():
    args = build_parser().parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else EVAL_OUTPUT_DIR / f"generation_eval_{timestamp}"
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
        )
        print("\n" + "=" * 72)
        print("MULTI-CHECKPOINT EVALUATION COMPLETE")
        print("=" * 72)
        if not results["comparison_df"].empty:
            best = results["comparison_df"].iloc[0]
            print(f"Best checkpoint:   {best['checkpoint_name']}")
            print(f"Validity:          {best['validity_pct']}%")
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
    )

    metrics = results["metrics"]
    print("\n" + "=" * 72)
    print("GENERATION EVALUATION COMPLETE")
    print("=" * 72)
    print(f"Requested samples: {metrics['requested_samples']}")
    print(f"Validity:          {metrics['rates']['validity_pct']}%")
    print(f"Uniqueness:        {metrics['rates']['uniqueness_pct_of_valid']}% of valid")
    print(f"Novelty:           {metrics['rates']['novelty_pct_of_valid']}% of valid")
    print(f"Avg score:         {metrics['scoring_summary_unique_valid']['average_clinical_score']}")
    print(f"Best score:        {metrics['scoring_summary_unique_valid']['best_clinical_score']}")
    print(f"Artifacts:         {results['generated_csv']}")
    print(f"                   {results['metrics_json']}")
    print(f"                   {results['summary_md']}")
    print(f"                   {results['debug_csv']}")
    print(f"                   {results['debug_json']}")


if __name__ == "__main__":
    main()
