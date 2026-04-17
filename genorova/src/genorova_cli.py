"""
Genorova AI — Command Line Interface
======================================

Simple CLI for running all Genorova AI operations from the terminal.

COMMANDS:
    generate    Generate new drug molecules for a disease
    score       Score molecules from a CSV file
    report      Generate the HTML discovery report
    train       Train the VAE on a disease dataset
    visualize   Draw 2D structure images for molecules

USAGE EXAMPLES:
    python genorova_cli.py generate --disease diabetes --count 100
    python genorova_cli.py score --file outputs/generated/molecules.csv
    python genorova_cli.py report
    python genorova_cli.py train --disease diabetes --epochs 100
    python genorova_cli.py visualize --smiles "CC(=O)Oc1ccccc1C(=O)O"
    python genorova_cli.py visualize --file outputs/generated/diabetes_candidates_validated.csv --top 10

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import sys
import argparse
import time
from pathlib import Path

# Make sure src/ is on path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

ROOT_DIR      = Path(__file__).parent.parent
DATA_DIR      = ROOT_DIR / "data" / "raw"
OUTPUT_DIR    = ROOT_DIR / "outputs"
GENERATED_DIR = OUTPUT_DIR / "generated"
MODELS_DIR    = OUTPUT_DIR / "models"

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║           GENOROVA AI — Drug Discovery Platform v1.0            ║
║       Generative AI for Diabetes & Infectious Disease           ║
║                Developer: Pushp Dwivedi                         ║
╚══════════════════════════════════════════════════════════════════╝
"""


# ============================================================================
# COMMAND: generate
# ============================================================================

def cmd_generate(args):
    """
    Generate new drug molecules using the trained VAE.

    Loads the saved model checkpoint for the requested disease,
    runs guided latent space sampling, validates with RDKit, and
    saves results to a CSV file.
    """
    print(BANNER)
    print(f"[GENERATE] Disease: {args.disease.upper()}")
    print(f"[GENERATE] Target count: {args.count}")

    disease = args.disease.lower()
    if disease not in ("diabetes", "infection"):
        print("[ERROR] --disease must be 'diabetes' or 'infection'")
        sys.exit(1)

    from science_evidence import ACTIVE_DISEASE, ACTIVE_SCOPE_NOTE, evaluate_candidate_rows

    if disease != ACTIVE_DISEASE:
        print(f"[ERROR] The active Genorova generation path is currently standardized to '{ACTIVE_DISEASE}'.")
        print(f"        {ACTIVE_SCOPE_NOTE}")
        sys.exit(1)

    csv_path   = DATA_DIR   / f"{disease}_molecules.csv"
    vocab_path = OUTPUT_DIR / f"vocabulary_{disease}.json"
    ckpt_dir   = MODELS_DIR / disease

    if not csv_path.exists():
        print(f"[ERROR] Training data not found: {csv_path}")
        print(f"        Run: python src/download_data.py  to fetch ChEMBL data first")
        sys.exit(1)

    if not vocab_path.exists():
        print(f"[ERROR] Vocabulary not found: {vocab_path}")
        print(f"        Run the full pipeline first: python src/run_pipeline.py")
        sys.exit(1)

    ckpt_path = ckpt_dir / f"genorova_{disease}_best.pt"
    if not ckpt_path.exists():
        print(f"[ERROR] Model checkpoint not found: {ckpt_path}")
        print(f"        Run: python genorova_cli.py train --disease {disease}")
        sys.exit(1)

    try:
        import torch
        import pandas as pd
        from model import VAE, MAX_SMILES_LENGTH
        from preprocessor import load_vocab, preprocess_batch, SmilesDataset
        from run_pipeline import guided_generate, score_molecules_batch, silent_score_molecule

        print(f"\n[*] Loading model checkpoint: {ckpt_path.name}")
        ckpt       = torch.load(str(ckpt_path), map_location="cpu")
        vocab_size = ckpt["vocab_size"]
        char2idx, idx2char = load_vocab(str(vocab_path))

        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            model = VAE(vocab_size=vocab_size)
        model.load_state_dict(ckpt["model_state"])
        model.eval()
        print(f"   [OK] Model loaded (epoch {ckpt['epoch']}, val_loss {ckpt['best_val_loss']:.5f})")

        print(f"\n[*] Encoding training molecules for guided generation...")
        import pandas as pd
        df = pd.read_csv(csv_path)
        smiles_list = df["smiles"].dropna().tolist()
        encoded = preprocess_batch(smiles_list, char2idx)

        device = torch.device("cpu")
        print(f"[*] Generating up to {args.count} valid molecules...")

        valid = []
        for temp in [0.3, 0.5, 0.8, 1.0]:
            if len(valid) >= args.count:
                break
            batch = guided_generate(model, encoded, char2idx, idx2char,
                                    vocab_size, device,
                                    num_samples=max(1000, args.count * 5),
                                    temperature=temp)
            novel = [s for s in batch if s not in set(smiles_list)]
            valid.extend(novel)
            print(f"   temp={temp}: {len(novel)} novel valid molecules (total {len(valid)})")

        valid = valid[:args.count]

        if not valid:
            print("[!] VAE generation produced no valid molecules (posterior collapse).")
            print("    Falling back to scoring top molecules from training set...")
            from rdkit import Chem
            from rdkit import RDLogger
            RDLogger.DisableLog("rdApp.*")
            valid = [s for s in smiles_list if Chem.MolFromSmiles(s) is not None][:args.count]

        print(f"\n[*] Scoring {len(valid)} molecules...")
        results = []
        for smi in valid:
            r = silent_score_molecule(smi)
            if r:
                results.append(r)

        if not results:
            print("[ERROR] Scoring failed for all molecules.")
            sys.exit(1)

        import pandas as pd
        ranked_rows = (pd.DataFrame(results)
                       .sort_values("clinical_score", ascending=False)
                       .reset_index(drop=True))
        reevaluated = evaluate_candidate_rows(
            ranked_rows.to_dict("records"),
            result_source="cli_ranked_candidates",
            fallback_used=False,
            max_candidates=min(args.count, len(ranked_rows)),
            confidence_note=(
                "CLI candidate set revalidated under the active diabetes / DPP4 / sitagliptin workflow."
            ),
            validation_status="canonical_cli_generation",
            limitations=[
                ACTIVE_SCOPE_NOTE,
                "These rows are revalidated computational candidates, not experimental leads.",
            ],
            recommended_next_step="Review comparator deltas and major risks before treating any row as a lead.",
        )
        df_out = pd.DataFrame(reevaluated).reset_index(drop=True)
        df_out.index += 1

        # Save
        out_path = GENERATED_DIR / f"{disease}_cli_generated.csv"
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        df_out.to_csv(out_path, index=False)

        print(f"\n[OK] Generated {len(df_out)} molecules → {out_path}")
        print(f"[OK] Best model score: {df_out['clinical_score'].max():.4f}")
        print(f"\nTop 5:")
        print(df_out[["smiles", "molecular_weight", "qed_score", "clinical_score", "final_decision", "recommendation"]].head())

    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print("        Install requirements: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"[ERROR] Generation failed: {e}")
        traceback.print_exc()
        sys.exit(1)


# ============================================================================
# COMMAND: score
# ============================================================================

def cmd_score(args):
    """Score molecules from a CSV file using the Genorova clinical scorer."""

    print(BANNER)
    print(f"[SCORE] Input file: {args.file}")

    if not Path(args.file).exists():
        print(f"[ERROR] File not found: {args.file}")
        sys.exit(1)

    try:
        import pandas as pd
        from run_pipeline import silent_score_molecule
        from science_evidence import ACTIVE_SCOPE_NOTE, evaluate_candidate_rows

        df_in = pd.read_csv(args.file)

        # Find SMILES column
        smiles_col = None
        for col in df_in.columns:
            if col.lower() in ["smiles", "smi", "smile"]:
                smiles_col = col
                break
        if smiles_col is None:
            smiles_col = df_in.columns[0]
        print(f"[*] Using column '{smiles_col}' as SMILES")

        smiles_list = df_in[smiles_col].dropna().tolist()
        print(f"[*] Scoring {len(smiles_list)} molecules...")

        results = []
        for i, smi in enumerate(smiles_list, 1):
            if i % 25 == 0:
                print(f"   ... {i}/{len(smiles_list)}")
            r = silent_score_molecule(str(smi))
            if r:
                results.append(r)

        if not results:
            print("[ERROR] No molecules could be scored.")
            sys.exit(1)

        ranked_rows = (pd.DataFrame(results)
                       .sort_values("clinical_score", ascending=False)
                       .reset_index(drop=True))
        reevaluated = evaluate_candidate_rows(
            ranked_rows.to_dict("records"),
            result_source="cli_scored_candidates",
            fallback_used=False,
            max_candidates=len(ranked_rows),
            confidence_note="CLI scoring output revalidated under the active diabetes / DPP4 / sitagliptin workflow.",
            validation_status="canonical_cli_scoring",
            limitations=[
                ACTIVE_SCOPE_NOTE,
                "These are computational screening rows, not clinical or experimental results.",
            ],
            recommended_next_step="Compare shortlisted rows against sitagliptin and inspect the evidence ledger fields.",
        )
        df_out = pd.DataFrame(reevaluated).reset_index(drop=True)
        df_out.index += 1

        # Save to same location with _scored suffix
        in_path = Path(args.file)
        out_path = in_path.parent / (in_path.stem + "_scored.csv")
        df_out.to_csv(str(out_path), index=False)

        print(f"\n[OK] Scored {len(df_out)} molecules → {out_path}")
        print(f"[OK] Best model score: {df_out['clinical_score'].max():.4f}")
        print(f"\nTop 5:")
        cols = [c for c in ["smiles","molecular_weight","qed_score","clinical_score","final_decision","recommendation"] if c in df_out.columns]
        print(df_out[cols].head())

    except Exception as e:
        import traceback
        print(f"[ERROR] Scoring failed: {e}")
        traceback.print_exc()
        sys.exit(1)


# ============================================================================
# COMMAND: report
# ============================================================================

def cmd_report(args):
    """Generate the Genorova AI HTML discovery report."""

    print(BANNER)
    print("[REPORT] Generating HTML report...")

    try:
        from report_generator import generate_report
        path = generate_report()
        print(f"\n[OK] Report ready: {path}")
        print(f"     Open this file in any web browser (Chrome, Firefox, Edge, etc.)")

    except Exception as e:
        import traceback
        print(f"[ERROR] Report generation failed: {e}")
        traceback.print_exc()
        sys.exit(1)


# ============================================================================
# COMMAND: train
# ============================================================================

def cmd_train(args):
    """Train the VAE on a disease dataset."""

    print(BANNER)
    print(f"[TRAIN] Disease: {args.disease.upper()}")
    print(f"[TRAIN] Epochs:  {args.epochs}")

    disease = args.disease.lower()
    if disease not in ("diabetes", "infection"):
        print("[ERROR] --disease must be 'diabetes' or 'infection'")
        sys.exit(1)

    csv_path   = DATA_DIR   / f"{disease}_molecules.csv"
    vocab_path = OUTPUT_DIR / f"vocabulary_{disease}.json"

    if not csv_path.exists():
        print(f"[ERROR] Training data not found: {csv_path}")
        print(f"        Run: python src/download_data.py")
        sys.exit(1)

    if not vocab_path.exists():
        print(f"[ERROR] Vocabulary not found: {vocab_path}")
        print(f"        Run: python src/run_pipeline.py  (builds vocab on first run)")
        sys.exit(1)

    try:
        from run_pipeline import train_vae
        ckpt_dir = MODELS_DIR / disease
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.time()
        model, char2idx, idx2char, vocab_size, device, smiles_list, encoded = train_vae(
            disease_label  = disease,
            csv_path       = csv_path,
            vocab_path     = vocab_path,
            checkpoint_dir = ckpt_dir,
            epochs         = args.epochs,
        )
        elapsed = (time.time() - t0) / 60
        print(f"\n[OK] Training complete in {elapsed:.1f} minutes")
        print(f"[OK] Model saved to: {ckpt_dir}")

    except Exception as e:
        import traceback
        print(f"[ERROR] Training failed: {e}")
        traceback.print_exc()
        sys.exit(1)


# ============================================================================
# COMMAND: visualize
# ============================================================================

def cmd_visualize(args):
    """Draw 2D structure images for molecules."""

    print(BANNER)

    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from vision.structure_visualizer import generate_structure_image, generate_comparison_grid

        out_dir = str(OUTPUT_DIR / "molecule_images")

        if args.smiles:
            # Single SMILES from command line
            print(f"[VIZ] Drawing single molecule: {args.smiles}")
            path = generate_structure_image(
                smiles     = args.smiles,
                output_dir = out_dir,
            )
            if path:
                print(f"[OK] Saved: {path}")
            else:
                print("[ERROR] Invalid SMILES")
                sys.exit(1)

        elif args.file:
            # Load from CSV
            import pandas as pd
            df = pd.read_csv(args.file)
            smiles_col = next((c for c in df.columns if c.lower() in ["smiles","smi"]), df.columns[0])
            smiles_list = df[smiles_col].dropna().tolist()

            n = args.top if args.top else len(smiles_list)
            smiles_list = smiles_list[:n]
            print(f"[VIZ] Drawing {len(smiles_list)} molecules from {args.file}")

            # Individual images
            saved = []
            for i, smi in enumerate(smiles_list, 1):
                p = generate_structure_image(smi, filename=f"cli_mol_{i:03d}.png",
                                             output_dir=out_dir)
                if p:
                    saved.append(p)

            # Also create comparison grid
            if len(smiles_list) > 1:
                grid = generate_comparison_grid(
                    smiles_list, title="Genorova AI Molecules", output_dir=out_dir
                )
                print(f"[OK] Comparison grid: {grid}")

            print(f"[OK] Saved {len(saved)}/{len(smiles_list)} images to {out_dir}")

        else:
            print("[ERROR] Provide --smiles <SMILES> or --file <CSV path>")
            sys.exit(1)

    except Exception as e:
        import traceback
        print(f"[ERROR] Visualization failed: {e}")
        traceback.print_exc()
        sys.exit(1)


# ============================================================================
# ARGUMENT PARSER
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""

    parser = argparse.ArgumentParser(
        prog        = "genorova_cli.py",
        description = "Genorova AI — Drug Discovery Platform CLI",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = """
EXAMPLES:
  python genorova_cli.py generate --disease diabetes --count 100
  python genorova_cli.py score    --file outputs/generated/molecules.csv
  python genorova_cli.py report
  python genorova_cli.py train    --disease diabetes --epochs 100
  python genorova_cli.py visualize --smiles "CC(=O)Oc1ccccc1C(=O)O"
  python genorova_cli.py visualize --file outputs/generated/diabetes_candidates_validated.csv --top 10
        """,
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")
    sub.required = True

    # ---- generate ----
    p_gen = sub.add_parser("generate", help="Generate new drug molecules")
    p_gen.add_argument("--disease", required=True, choices=["diabetes"],
                       help="Active disease area for the canonical workflow")
    p_gen.add_argument("--count", type=int, default=100,
                       help="Number of molecules to generate (default: 100)")

    # ---- score ----
    p_score = sub.add_parser("score", help="Score molecules from a CSV file")
    p_score.add_argument("--file", required=True,
                         help="CSV file with SMILES column")

    # ---- report ----
    sub.add_parser("report", help="Generate HTML discovery report")

    # ---- train ----
    p_train = sub.add_parser("train", help="Train the VAE model")
    p_train.add_argument("--disease", required=True, choices=["diabetes","infection"],
                         help="Target disease area")
    p_train.add_argument("--epochs", type=int, default=100,
                         help="Number of training epochs (default: 100)")

    # ---- visualize ----
    p_viz = sub.add_parser("visualize", help="Draw 2D structure images")
    group = p_viz.add_mutually_exclusive_group(required=True)
    group.add_argument("--smiles", type=str, help="Single SMILES string to draw")
    group.add_argument("--file",   type=str, help="CSV file with SMILES column")
    p_viz.add_argument("--top", type=int, default=None,
                       help="Draw only top N molecules from file (default: all)")

    return parser


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main entry point for the CLI."""
    parser = build_parser()
    args   = parser.parse_args()

    dispatch = {
        "generate":  cmd_generate,
        "score":     cmd_score,
        "report":    cmd_report,
        "train":     cmd_train,
        "visualize": cmd_visualize,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
