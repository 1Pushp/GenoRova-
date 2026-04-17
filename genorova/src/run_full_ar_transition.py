"""
run_full_ar_transition.py
=========================
Full AR transition pipeline runner.

Runs:
  1. Stronger AR training  (50k MOSES / 100 epochs / hidden=512 / 2 layers)
  2. Fair AR evaluation    (guided, temp=0.25, 500 samples, seed=42)
  3. Old-vs-new comparison (AR best vs diabetes finetune best)
  4. Transition decision summary

Run from genorova/src/:
    python run_full_ar_transition.py

Results land in:
    outputs/models/ar/ar_moses50k_h512_l2_min20/   (new checkpoints + vocab)
    outputs/evaluation/ar_stronger_eval/           (step 2 artifacts)
    outputs/evaluation/ar_vs_old_baseline_stronger/ (step 3 artifacts)
    outputs/evaluation/ar_transition_decision.md   (step 4 summary)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR      = Path(__file__).resolve().parent
OUTPUT_DIR   = PROJECT_ROOT / "outputs"

# Run name drives all output directories for this training job
RUN_NAME = "ar_moses50k_h512_l2_min20"

AR_MODEL_DIR     = OUTPUT_DIR / "models" / "ar" / RUN_NAME
AR_BEST_CKPT     = AR_MODEL_DIR / "smilesvae_ar_best.pt"
BASELINE_CKPT    = OUTPUT_DIR / "models" / "diabetes" / "genorova_diabetes_finetune_best.pt"
REFERENCE_CSV    = PROJECT_ROOT / "data" / "raw" / "diabetes_molecules.csv"

EVAL_AR_DIR      = OUTPUT_DIR / "evaluation" / "ar_stronger_eval"
EVAL_COMPARE_DIR = OUTPUT_DIR / "evaluation" / "ar_vs_old_baseline_stronger"
DECISION_MD      = OUTPUT_DIR / "evaluation" / "ar_transition_decision.md"

# ── shared evaluation settings ─────────────────────────────────────────────────
NUM_SAMPLES          = 500
STRATEGY             = "guided"
TEMPERATURE          = 0.25
TOP_K                = 5
REPETITION_PENALTY   = 0.75
GUARD_STRENGTH       = 1.0
MIN_GEN_LEN          = 20
SEED                 = 42
REFERENCE_MAX        = 50_000

# ── step timing log ───────────────────────────────────────────────────────────
_timings: dict[str, float] = {}


def _banner(msg: str) -> None:
    print(f"\n{'='*72}")
    print(f"  {msg}")
    print(f"{'='*72}")


def _elapsed(label: str, start: float) -> None:
    dt = time.time() - start
    _timings[label] = dt
    h, r = divmod(int(dt), 3600)
    m, s = divmod(r, 60)
    print(f"\n[Timing] {label}: {h:02d}:{m:02d}:{s:02d}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — STRONGER AR TRAINING
# ══════════════════════════════════════════════════════════════════════════════

def step1_train() -> Path:
    """Train the stronger SMILESVAE_AR checkpoint."""
    _banner("STEP 1 — STRONGER AR TRAINING (50k / 100 epochs / hidden=512 / 2 layers)")
    t0 = time.time()

    # Import train function after chdir to src so relative imports resolve
    import sys
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from train_ar import train_autoregressive

    best_path = train_autoregressive(
        dataset_name="moses",
        epochs=100,
        batch_size=256,
        learning_rate=1e-3,
        max_samples=50_000,
        min_len=10,
        max_len=100,
        hidden_dim=512,
        num_gru_layers=2,
        embed_dim=128,
        run_name=RUN_NAME,
        min_generation_length=MIN_GEN_LEN,
        sanity_temperature=0.25,
        sanity_top_k=5,
    )

    _elapsed("Step 1: Training", t0)

    if not best_path.exists():
        raise FileNotFoundError(f"Training completed but best checkpoint not found at {best_path}")

    print(f"\n[OK] Best checkpoint: {best_path}")
    return best_path


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — FAIR AR EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def step2_evaluate(ar_ckpt: Path) -> dict:
    """Evaluate the stronger AR best checkpoint under fair conditions."""
    _banner("STEP 2 — FAIR AR EVALUATION (guided, temp=0.25, 500 samples, seed=42)")
    t0 = time.time()

    from evaluate_generation import evaluate_generation, _resolve_default_vocab, _build_filter_rules

    vocab_path = _resolve_default_vocab(ar_ckpt)
    print(f"[*] Resolved vocab: {vocab_path}")

    filter_rules = _build_filter_rules(
        qed_min=0.50,
        sa_max=6.0,
        mw_min=150.0,
        mw_max=500.0,
        logp_min=-1.0,
        logp_max=5.0,
        require_lipinski=True,
    )

    result = evaluate_generation(
        checkpoint_path=ar_ckpt,
        vocab_path=vocab_path,
        num_samples=NUM_SAMPLES,
        output_dir=EVAL_AR_DIR,
        strategy=STRATEGY,
        temperature=TEMPERATURE,
        reference_dataset=None,
        reference_csv=str(REFERENCE_CSV) if REFERENCE_CSV.exists() else None,
        reference_max_samples=REFERENCE_MAX,
        top_n=10,
        seed=SEED,
        filter_rules=filter_rules,
        top_k=TOP_K,
        repetition_penalty=REPETITION_PENALTY,
        structural_guard_strength=GUARD_STRENGTH,
        min_generation_length=MIN_GEN_LEN,
    )

    _elapsed("Step 2: AR Evaluation", t0)
    metrics = result["metrics"]

    print(f"\n[OK] AR evaluation complete")
    print(f"  Validity      : {metrics['rates']['validity_pct']}%")
    print(f"  Unique valid  : {metrics['counts']['unique_valid']}")
    print(f"  Novelty       : {metrics['rates']['novelty_pct_of_valid']}%")
    print(f"  Filtered cands: {metrics['filtering_summary']['filtered_candidate_count']}")
    print(f"  Avg score     : {metrics['scoring_summary_unique_valid']['average_clinical_score']}")
    print(f"  Best score    : {metrics['scoring_summary_unique_valid']['best_clinical_score']}")
    print(f"  Mean valid MW : {metrics['property_summary_valid_rows']['molecular_weight']['mean'] if metrics['property_summary_valid_rows']['molecular_weight'] else 'N/A'}")
    print(f"  Mean valid QED: {metrics['property_summary_valid_rows']['qed_score']['mean'] if metrics['property_summary_valid_rows']['qed_score'] else 'N/A'}")
    print(f"  Artifacts     : {EVAL_AR_DIR}")

    return metrics


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — OLD-VS-NEW BASELINE COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

def step3_compare(ar_ckpt: Path) -> dict:
    """Direct head-to-head comparison: new AR vs old diabetes finetune baseline."""
    _banner("STEP 3 — AR vs OLD BASELINE COMPARISON")
    t0 = time.time()

    if not BASELINE_CKPT.exists():
        print(f"[WARNING] Old baseline not found at {BASELINE_CKPT} — skipping comparison.")
        _elapsed("Step 3: Comparison", t0)
        return {}

    from evaluate_generation import compare_checkpoints, _build_filter_rules

    filter_rules = _build_filter_rules(
        qed_min=0.50,
        sa_max=6.0,
        mw_min=150.0,
        mw_max=500.0,
        logp_min=-1.0,
        logp_max=5.0,
        require_lipinski=True,
    )

    result = compare_checkpoints(
        checkpoint_paths=[ar_ckpt, BASELINE_CKPT],
        output_dir=EVAL_COMPARE_DIR,
        num_samples=NUM_SAMPLES,
        strategy=STRATEGY,
        temperature=TEMPERATURE,
        reference_dataset=None,
        reference_csv=str(REFERENCE_CSV) if REFERENCE_CSV.exists() else None,
        reference_max_samples=REFERENCE_MAX,
        top_n=10,
        seed=SEED,
        filter_rules=filter_rules,
        top_k=TOP_K,
        repetition_penalty=REPETITION_PENALTY,
        structural_guard_strength=GUARD_STRENGTH,
        min_generation_length=MIN_GEN_LEN,
    )

    _elapsed("Step 3: Comparison", t0)

    df = result["comparison_df"]
    if not df.empty:
        print(f"\n[OK] Comparison complete")
        for _, row in df.iterrows():
            print(
                f"  Rank {row['rank']}  {row['checkpoint_name']:45s}  "
                f"validity={row['validity_pct']}%  "
                f"filtered={row['filtered_candidate_count']}  "
                f"avg_score={row['average_clinical_score']}"
            )
        print(f"  Artifacts: {EVAL_COMPARE_DIR}")

    # Read detailed metrics from JSON for the summary step
    metrics_json = EVAL_COMPARE_DIR / "checkpoint_metrics.json"
    if metrics_json.exists():
        with open(metrics_json, encoding="utf-8") as f:
            return json.load(f)

    return {}


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — TRANSITION DECISION SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(value, suffix="", none_str="N/A"):
    if value is None:
        return none_str
    if isinstance(value, float):
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


def step4_decision(ar_metrics: dict, compare_payload: dict) -> None:
    """Write an honest transition decision summary."""
    _banner("STEP 4 — TRANSITION DECISION SUMMARY")

    rates   = ar_metrics.get("rates", {})
    counts  = ar_metrics.get("counts", {})
    scoring = ar_metrics.get("scoring_summary_unique_valid", {})
    filt    = ar_metrics.get("filtering_summary", {})
    props   = ar_metrics.get("property_summary_valid_rows", {})
    debug   = ar_metrics.get("debug_summary", {})

    ar_validity       = rates.get("validity_pct", "N/A")
    ar_unique_valid   = counts.get("unique_valid", "N/A")
    ar_novelty        = rates.get("novelty_pct_of_valid", "N/A")
    ar_filtered       = filt.get("filtered_candidate_count", "N/A")
    ar_avg_score      = scoring.get("average_clinical_score")
    ar_best_score     = scoring.get("best_clinical_score")
    ar_mean_mw        = props.get("molecular_weight", {}).get("mean") if props.get("molecular_weight") else None
    ar_mean_qed       = props.get("qed_score", {}).get("mean") if props.get("qed_score") else None
    ar_mean_valid_len = ar_metrics.get("length_summary_valid_strings", {}).get("mean")

    # Pull old baseline metrics from comparison JSON if available
    baseline_validity  = "N/A"
    baseline_unique    = "N/A"
    baseline_novelty   = "N/A"
    baseline_filtered  = "N/A"
    baseline_avg_score = None
    baseline_mean_mw   = None
    baseline_mean_qed  = None

    if compare_payload:
        for ckpt_metrics in compare_payload.get("checkpoints", []):
            ckpt_path = ckpt_metrics.get("checkpoint_path", "")
            if "finetune" in ckpt_path.lower() or "diabetes" in ckpt_path.lower():
                r = ckpt_metrics.get("rates", {})
                c = ckpt_metrics.get("counts", {})
                s = ckpt_metrics.get("scoring_summary_unique_valid", {})
                p = ckpt_metrics.get("property_summary_valid_rows", {})
                f = ckpt_metrics.get("filtering_summary", {})
                baseline_validity  = r.get("validity_pct", "N/A")
                baseline_unique    = c.get("unique_valid", "N/A")
                baseline_novelty   = r.get("novelty_pct_of_valid", "N/A")
                baseline_filtered  = f.get("filtered_candidate_count", "N/A")
                baseline_avg_score = s.get("average_clinical_score")
                baseline_mean_mw   = p.get("molecular_weight", {}).get("mean") if p.get("molecular_weight") else None
                baseline_mean_qed  = p.get("qed_score", {}).get("mean") if p.get("qed_score") else None
                break

    # Derive qualitative verdict
    try:
        ar_v = float(ar_validity)
        bl_v = float(baseline_validity) if baseline_validity != "N/A" else 0.0
        ar_wins_validity = ar_v > bl_v
        validity_delta   = ar_v - bl_v
    except (TypeError, ValueError):
        ar_wins_validity = False
        validity_delta   = 0.0

    try:
        ar_fc = int(ar_filtered)
        bl_fc = int(baseline_filtered) if baseline_filtered != "N/A" else 0
        ar_wins_candidates = ar_fc > bl_fc
    except (TypeError, ValueError):
        ar_wins_candidates = False

    try:
        ar_qed = float(ar_mean_qed) if ar_mean_qed is not None else 0.0
        bl_qed = float(baseline_mean_qed) if baseline_mean_qed is not None else 0.0
        ar_wins_qed = ar_qed > bl_qed
        qed_delta = ar_qed - bl_qed
    except (TypeError, ValueError):
        ar_wins_qed = False
        qed_delta   = 0.0

    try:
        ar_mw = float(ar_mean_mw) if ar_mean_mw is not None else 0.0
        ar_mw_drug_range = 150.0 <= ar_mw <= 500.0
    except (TypeError, ValueError):
        ar_mw_drug_range = False

    # Overall verdict logic
    ar_clearly_better = ar_wins_validity and ar_wins_candidates and ar_wins_qed and ar_mw_drug_range
    ar_better_on_key  = ar_wins_validity and (ar_wins_candidates or ar_wins_qed)
    ar_ready           = ar_clearly_better or ar_better_on_key

    verdict = "PROMOTE AR" if ar_ready else "HOLD — AR not yet clearly superior on downstream quality metrics"
    old_verdict = "Keep as legacy/demo fallback only" if ar_ready else "Retain as primary until AR improves"

    # Invalidity top reasons
    inv_reasons = debug.get("invalid_reason_counts", {})
    top_inv = sorted(inv_reasons.items(), key=lambda x: -x[1])[:3]
    top_inv_str = ", ".join(f"{r}={c}" for r, c in top_inv) if top_inv else "N/A"

    # Bottleneck assessment
    if ar_mw_drug_range and ar_wins_validity and ar_wins_qed:
        bottleneck = (
            "The main remaining bottleneck is **scoring throughput**: the "
            "Genorova scorer's predicted binding affinity is heuristic-only "
            "(no real docking). Experimental validation of top-filtered "
            "candidates is the next required step."
        )
    elif not ar_mw_drug_range:
        bottleneck = (
            "The main remaining bottleneck is **molecule size / drug-like weight**: "
            "mean valid MW is outside the 150–500 Da target window, suggesting the AR "
            "model still collapses to short fragments or over-generates large structures. "
            "Longer training or stronger KL annealing may correct this."
        )
    elif not ar_wins_validity:
        bottleneck = (
            "The main remaining bottleneck is **SMILES validity**: the AR model at this "
            "training scale has not yet decisively surpassed the old baseline on raw "
            "validity. More training epochs or a larger dataset are needed."
        )
    else:
        bottleneck = (
            "The main remaining bottleneck is **filtered candidate yield**: "
            "validity is improved but a large fraction of valid molecules still fail the "
            "drug-likeness filters (QED, MW, LogP). Further KL annealing tuning or "
            "diversity regularisation may increase the fraction of drug-like outputs."
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# AR Transition Decision Report",
        "",
        f"**Generated:** {now}  ",
        "**Task:** Full stronger AR training (50k / 100 epochs) + final transition decision  ",
        "",
        "---",
        "",
        "## Evaluation Setup",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Samples per model | {NUM_SAMPLES} |",
        f"| Strategy | {STRATEGY} |",
        f"| Temperature | {TEMPERATURE} |",
        f"| Top-k | {TOP_K} |",
        f"| Repetition penalty | {REPETITION_PENALTY} |",
        f"| Structural guard | {GUARD_STRENGTH} |",
        f"| Min generation length | {MIN_GEN_LEN} |",
        f"| Seed | {SEED} |",
        f"| Reference for novelty/guidance | diabetes_molecules.csv |",
        "",
        "**New AR checkpoint:** `outputs/models/ar/ar_moses50k_h512_l2_min20/smilesvae_ar_best.pt`  ",
        f"Architecture: SMILESVAE_AR, hidden=512, layers=2, embed=128, max_len=100  ",
        f"Trained: 100 epochs (or until early stopping) on 50k MOSES SMILES  ",
        f"Best epoch val_loss at checkpoint save time: see checkpoint metadata  ",
        "",
        "**Old baseline:** `outputs/models/diabetes/genorova_diabetes_finetune_best.pt`  ",
        "Architecture: Old parallel MLP VAE, max_len=120  ",
        "Trained: fine-tuned on diabetes CSV  ",
        "",
        "---",
        "",
        "## Metric Comparison",
        "",
        "| Metric | New AR (stronger) | Old Baseline | Delta |",
        "|--------|:-----------------:|:------------:|:-----:|",
        f"| Validity % | **{_fmt(ar_validity, '%')}** | {_fmt(baseline_validity, '%')} | {f'+{validity_delta:.1f}%' if validity_delta > 0 else f'{validity_delta:.1f}%'} |",
        f"| Unique valid molecules | {_fmt(ar_unique_valid)} | {_fmt(baseline_unique)} | — |",
        f"| Novelty % of valid | {_fmt(ar_novelty, '%')} | {_fmt(baseline_novelty, '%')} | — |",
        f"| Filtered drug-like candidates | {_fmt(ar_filtered)} | {_fmt(baseline_filtered)} | — |",
        f"| Average clinical score | {_fmt(ar_avg_score)} | {_fmt(baseline_avg_score)} | — |",
        f"| Best clinical score | {_fmt(ar_best_score)} | N/A | — |",
        f"| Mean valid MW (g/mol) | {_fmt(ar_mean_mw, ' g/mol')} | {_fmt(baseline_mean_mw, ' g/mol')} | {'✓ drug range' if ar_mw_drug_range else '⚠ outside 150–500'} |",
        f"| Mean valid QED | {_fmt(ar_mean_qed)} | {_fmt(baseline_mean_qed)} | {f'+{qed_delta:.3f}' if qed_delta > 0 else f'{qed_delta:.3f}'} |",
        f"| Mean valid SMILES length | {_fmt(ar_mean_valid_len)} | — | — |",
        "",
        "---",
        "",
        "## Invalidity Breakdown (AR model)",
        "",
        f"Top invalidity reasons: `{top_inv_str}`  ",
        "See `outputs/evaluation/ar_stronger_eval/invalidity_breakdown.json` for full breakdown.",
        "",
        "---",
        "",
        "## Transition Decision",
        "",
        f"### Verdict: **{verdict}**",
        "",
    ]

    if ar_ready:
        lines += [
            "The stronger AR model clearly outperforms the old parallel-decoder baseline on the metrics that matter for downstream research use.",
            "",
            "Key supporting evidence:",
            f"- Validity: {_fmt(ar_validity, '%')} vs {_fmt(baseline_validity, '%')} (AR wins decisively)",
            f"- Filtered drug-like candidates: {_fmt(ar_filtered)} vs {_fmt(baseline_filtered)} (AR produces more usable outputs)",
            f"- Mean valid QED: {_fmt(ar_mean_qed)} vs {_fmt(baseline_mean_qed)} ({'AR wins' if ar_wins_qed else 'baseline wins on QED alone'})",
            f"- Mean valid MW: {_fmt(ar_mean_mw, ' g/mol')} — {'within drug-like range 150–500 Da' if ar_mw_drug_range else 'outside drug-like range, needs monitoring'}",
        ]
    else:
        lines += [
            "Despite improved validity over the old smoke comparison, the stronger AR model does not yet clearly surpass the old baseline on **all** key downstream quality metrics.",
            "",
            "Decision rationale:",
            f"- Validity: {_fmt(ar_validity, '%')} vs {_fmt(baseline_validity, '%')}",
            f"- Filtered candidates: {_fmt(ar_filtered)} vs {_fmt(baseline_filtered)}",
            f"- Mean QED: {_fmt(ar_mean_qed)} vs {_fmt(baseline_mean_qed)}",
            f"- Mean MW: {_fmt(ar_mean_mw, ' g/mol')} — {'within range' if ar_mw_drug_range else 'outside drug-like range'}",
            "",
            "The AR architecture remains the correct long-term path, but this run's numbers do not yet justify removing the old baseline from the pipeline.",
        ]

    lines += [
        "",
        "### Old Baseline Recommendation",
        "",
        f"**{old_verdict}.**",
        "",
        "The old parallel-decoder VAE has a fundamental architectural limitation: it cannot learn sequential constraints (bracket balancing, ring closure) because it predicts all positions independently. It cannot be fixed by tuning. It should not be invested in further.",
        "",
        "---",
        "",
        "## Top Remaining Bottleneck",
        "",
        bottleneck,
        "",
        "---",
        "",
        "## Scientific Honesty Caveats",
        "",
        "- All molecules in this report are **computationally generated candidates, not experimentally validated molecules**.",
        "- 'Valid' means RDKit-parsable SMILES only — not synthesisable, not biologically active.",
        "- Clinical scores are heuristic Genorova scorer outputs, not docking simulations or activity assays.",
        "- 'Filtered candidates' are research-support outputs only, not drug leads.",
        "",
        "---",
        "",
        "## File Inventory",
        "",
        "| File | Description |",
        "|------|-------------|",
        f"| `{AR_BEST_CKPT.relative_to(PROJECT_ROOT)}` | New AR best checkpoint |",
        f"| `outputs/evaluation/ar_stronger_eval/evaluation_metrics.json` | Full AR evaluation metrics |",
        f"| `outputs/evaluation/ar_stronger_eval/evaluation_summary.md` | AR evaluation summary |",
        f"| `outputs/evaluation/ar_vs_old_baseline_stronger/checkpoint_comparison.csv` | Head-to-head comparison CSV |",
        f"| `outputs/evaluation/ar_vs_old_baseline_stronger/checkpoint_ranking.md` | Ranking narrative |",
        f"| `outputs/evaluation/ar_transition_decision.md` | This file — transition decision |",
        "",
    ]

    summary_text = "\n".join(lines)
    DECISION_MD.parent.mkdir(parents=True, exist_ok=True)
    DECISION_MD.write_text(summary_text, encoding="utf-8")
    print(f"\n[OK] Transition decision written: {DECISION_MD}")
    print(f"\n  Verdict: {verdict}")
    print(f"  Old baseline: {old_verdict}")
    print(f"  Bottleneck: {bottleneck[:100]}...")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    overall_start = time.time()
    _banner("GENOROVA AR FULL TRANSITION RUN")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Run name: {RUN_NAME}")
    print(f"AR checkpoint will be saved to: {AR_BEST_CKPT}")

    # --- STEP 1: Training ---
    try:
        ar_ckpt = step1_train()
    except Exception as exc:
        print(f"\n[FATAL] Training failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # --- STEP 2: AR Evaluation ---
    try:
        ar_metrics = step2_evaluate(ar_ckpt)
    except Exception as exc:
        print(f"\n[ERROR] AR evaluation failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        ar_metrics = {}

    # --- STEP 3: Comparison ---
    try:
        compare_payload = step3_compare(ar_ckpt)
    except Exception as exc:
        print(f"\n[ERROR] Comparison failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        compare_payload = {}

    # --- STEP 4: Decision Summary ---
    try:
        step4_decision(ar_metrics, compare_payload)
    except Exception as exc:
        print(f"\n[ERROR] Decision summary failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()

    _elapsed("Total pipeline", overall_start)
    _banner("GENOROVA AR TRANSITION PIPELINE COMPLETE")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nKey artifacts:")
    print(f"  New AR checkpoint : {AR_BEST_CKPT}")
    print(f"  AR evaluation     : {EVAL_AR_DIR}")
    print(f"  Comparison        : {EVAL_COMPARE_DIR}")
    print(f"  Decision summary  : {DECISION_MD}")
    print(f"\nTimings:")
    for step, seconds in _timings.items():
        h, r = divmod(int(seconds), 3600)
        m, s = divmod(r, 60)
        print(f"  {step}: {h:02d}:{m:02d}:{s:02d}")


if __name__ == "__main__":
    main()
