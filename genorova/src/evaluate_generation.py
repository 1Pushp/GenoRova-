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
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import torch

from data_loader import load_smiles_dataset, load_smiles_from_csv
from model import LATENT_DIM, VAE
from preprocessor import PAD_TOKEN, load_vocab, preprocess_batch


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "outputs"
MODEL_DIR = OUTPUT_DIR / "models"
EVAL_OUTPUT_DIR = OUTPUT_DIR / "evaluation"


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


def _resolve_default_vocab(checkpoint_path: Path) -> Path:
    stem = checkpoint_path.stem.lower()
    candidates = []
    if "diabetes" in stem and "pretrain" in stem:
        candidates.append(OUTPUT_DIR / "vocabulary_diabetes_pretrain.json")
    if "diabetes" in stem:
        candidates.extend(
            [
                OUTPUT_DIR / "vocabulary_diabetes_pretrain.json",
                OUTPUT_DIR / "vocabulary_diabetes.json",
            ]
        )
    if "infection" in stem:
        candidates.append(OUTPUT_DIR / "vocabulary_infection.json")

    candidates.extend(
        [
            OUTPUT_DIR / "vocab.json",
            OUTPUT_DIR / "vocabulary.json",
            OUTPUT_DIR / "vocabulary_diabetes.json",
            OUTPUT_DIR / "vocabulary_diabetes_pretrain.json",
            OUTPUT_DIR / "vocabulary_infection.json",
        ]
    )

    seen = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            return path
    raise FileNotFoundError(f"Could not find a vocabulary file for checkpoint {checkpoint_path}")


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
    checkpoint = torch.load(checkpoint_path, map_location=device)
    state_dict = checkpoint.get("model_state") or checkpoint.get("model_state_dict")
    if state_dict is None:
        raise KeyError(f"Checkpoint {checkpoint_path} is missing model weights.")

    char2idx, idx2char = load_vocab(str(vocab_path))
    vocab_size = len(char2idx)
    max_length = _infer_model_max_length(checkpoint, vocab_size)

    model = VAE(vocab_size=vocab_size, latent_dim=LATENT_DIM, max_length=max_length).to(device)
    model.load_state_dict(state_dict)
    model.eval()
    return model, checkpoint, char2idx, idx2char, max_length


def _decode_indices(indices: torch.Tensor, idx2char: dict[int, str], pad_idx: int) -> list[str]:
    decoded = []
    for seq in indices:
        chars = []
        for token in seq:
            token_int = int(token.item())
            if token_int == pad_idx:
                break
            chars.append(idx2char.get(token_int, ""))
        decoded.append("".join(chars).strip())
    return decoded


def _generate_random(model: VAE, idx2char: dict[int, str], pad_idx: int, num_samples: int, device: torch.device):
    with torch.no_grad():
        z = torch.randn(num_samples, LATENT_DIM, device=device)
        recon = model.decode(z)
        indices = torch.argmax(recon, dim=2)
    return _decode_indices(indices, idx2char, pad_idx)


def _generate_guided(
    model: VAE,
    reference_smiles: list[str],
    char2idx: dict[str, int],
    idx2char: dict[int, str],
    max_length: int,
    pad_idx: int,
    num_samples: int,
    temperature: float,
    device: torch.device,
):
    if not reference_smiles:
        raise ValueError("Guided generation requires at least one reference molecule.")

    encoded = preprocess_batch(reference_smiles, char2idx, max_length=max_length)
    tensor_data = torch.from_numpy(encoded).float().to(device)
    batch_size = 64
    generated: list[str] = []

    with torch.no_grad():
        mu_batches = []
        for start in range(0, len(tensor_data), batch_size):
            batch = tensor_data[start : start + batch_size]
            mu, _ = model.encoder(batch)
            mu_batches.append(mu.cpu())
        all_mu = torch.cat(mu_batches, dim=0)

        for start in range(0, num_samples, batch_size):
            this_batch = min(batch_size, num_samples - start)
            index = torch.randint(0, len(all_mu), (this_batch,))
            z = all_mu[index].to(device)
            z = z + (torch.randn_like(z) * temperature)
            recon = model.decode(z)
            indices = torch.argmax(recon, dim=2)
            generated.extend(_decode_indices(indices, idx2char, pad_idx))

    return generated


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
) -> dict[str, Any]:
    Chem, _, _ = _require_rdkit()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    output_dir.mkdir(parents=True, exist_ok=True)

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
    pad_idx = char2idx.get(PAD_TOKEN, 0)

    if strategy == "guided":
        raw_smiles = _generate_guided(
            model=model,
            reference_smiles=reference_smiles,
            char2idx=char2idx,
            idx2char=idx2char,
            max_length=max_length,
            pad_idx=pad_idx,
            num_samples=num_samples,
            temperature=temperature,
            device=device,
        )
    else:
        raw_smiles = _generate_random(
            model=model,
            idx2char=idx2char,
            pad_idx=pad_idx,
            num_samples=num_samples,
            device=device,
        )

    records: list[dict[str, Any]] = []
    canonical_counts: dict[str, int] = {}
    for index, smiles in enumerate(raw_smiles, start=1):
        canonical = _canonicalize_smiles(smiles, Chem)
        if canonical is not None:
            canonical_counts[canonical] = canonical_counts.get(canonical, 0) + 1
        records.append(
            {
                "sample_index": index,
                "raw_smiles": smiles,
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

    metrics = {
        "generated_at": datetime.now().isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "vocab_path": str(vocab_path),
        "device": str(device),
        "generation_strategy": strategy,
        "temperature": temperature,
        "requested_samples": int(num_samples),
        "reference_source": reference_source,
        "reference_canonical_size": int(len(reference_canonical)),
        "checkpoint_epoch": int(checkpoint.get("epoch", 0)),
        "checkpoint_best_val_loss": checkpoint.get("best_val_loss"),
        "model_max_length": int(max_length),
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

    generated_df.to_csv(generated_csv, index=False)
    metrics_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

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
        ]
    )
    summary_md.write_text(summary_text, encoding="utf-8")

    return {
        "generated_csv": generated_csv,
        "metrics_json": metrics_json,
        "summary_md": summary_md,
        "metrics": metrics,
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Evaluate the quality of molecules generated by a trained Genorova VAE.")
    parser.add_argument("--checkpoint", default=None, help="Path to a trained checkpoint. Defaults to the best available model.")
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
    return parser


def main():
    args = build_parser().parse_args()

    checkpoint_path = Path(args.checkpoint) if args.checkpoint else _resolve_default_checkpoint()
    vocab_path = Path(args.vocab) if args.vocab else _resolve_default_vocab(checkpoint_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else EVAL_OUTPUT_DIR / f"generation_eval_{timestamp}"

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


if __name__ == "__main__":
    main()
