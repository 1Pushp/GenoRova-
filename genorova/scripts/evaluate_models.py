"""
genorova/scripts/evaluate_models.py

Full evaluation of both trained Genorova models:
  Part 1 — Base CVAE (best.pt):   500 molecules, validity/uniqueness/novelty + ADMET
  Part 2 — DPP-4 specialist (dpp4_finetuned.pt): 200 molecules, Tanimoto vs sitagliptin
  Part 3 — Investor summary printed and saved to outputs/MODEL_PERFORMANCE_REPORT.txt
"""

import sys
import os
import time
from pathlib import Path

# Fix Windows cp1252 terminal — must happen before any print
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import torch

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve()
_GENOROVA = _SCRIPT.parent.parent          # genorova/
_SRC      = _GENOROVA / "src"
_MODELS   = _GENOROVA / "models"

sys.path.insert(0, str(_GENOROVA))
sys.path.insert(0, str(_SRC))

# RDKit
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, DataStructs
RDLogger.DisableLog("rdApp.*")

# CVAE + tokenizer
from models.cvae import CVAE, PAD_ID, BOS_ID, EOS_ID, MAX_SEQ_LEN, NUM_PROPS
from train_cvae import CVAETokenizer, TrainConfig

# ADMET scorer
from admet.scorer import score_batch

TOKENIZER_PATH = _GENOROVA / "tokenizer" / "genorova_bpe.json"
CKPT_DIR       = _GENOROVA / "outputs" / "checkpoints"
OUTPUTS_DIR    = _GENOROVA / "outputs"
GENERATED_DIR  = OUTPUTS_DIR / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

DATA_CSV       = _GENOROVA / "data" / "processed" / "cleaned_molecules_v2.csv"

SITAGLIPTIN    = "O=C(N1CCC[C@@H]1C(=O)N1CCn2c(nnc2-c2ccc(F)cc2)C1)CC(F)(F)F"


# ===========================================================================
# Helpers
# ===========================================================================

def load_model(ckpt_path: Path, state_key: str = "model_state") -> tuple:
    """Load CVAE, tokenizer, prop normalisation params from a checkpoint."""
    print(f"  Loading checkpoint: {ckpt_path.name}")
    ckpt = torch.load(str(ckpt_path), weights_only=False, map_location="cpu")

    cfg_dict   = ckpt["config"]
    vocab_size = cfg_dict["vocab_size"]
    latent_dim = cfg_dict["latent_dim"]
    d_model    = cfg_dict["d_model"]
    num_heads  = cfg_dict["num_heads"]
    num_layers = cfg_dict["num_layers"]

    tokenizer = CVAETokenizer(TOKENIZER_PATH, max_len=MAX_SEQ_LEN)

    model = CVAE(
        vocab_size=vocab_size,
        latent_dim=latent_dim,
        d_model=d_model,
        num_heads=num_heads,
        num_layers=num_layers,
    )
    model.load_state_dict(ckpt[state_key])
    model.eval()

    prop_mean = np.array(ckpt["prop_mean"], dtype=np.float32)
    prop_std  = np.array(ckpt["prop_std"],  dtype=np.float32)

    epoch    = ckpt.get("epoch", "?")
    val_loss = ckpt.get("val_loss", float("nan"))
    print(f"  epoch={epoch}  val_loss={val_loss:.4f}")
    return model, tokenizer, prop_mean, prop_std


def make_prop_tensor(qed: float, logp: float, mw: float, sa: float,
                     prop_mean: np.ndarray, prop_std: np.ndarray,
                     n: int = 1) -> torch.Tensor:
    """Build a normalised property conditioning tensor [n, 4]."""
    raw = np.array([[qed, logp, mw, sa]], dtype=np.float32)
    norm = (raw - prop_mean) / (prop_std + 1e-8)
    return torch.tensor(norm, dtype=torch.float32).expand(n, -1)


def generate_smiles(model: CVAE, tokenizer: CVAETokenizer,
                    prop_mean: np.ndarray, prop_std: np.ndarray,
                    n_total: int,
                    qed: float = 0.75, logp: float = 2.5,
                    mw: float = 300.0, sa: float = 2.3,
                    batch_size: int = 50,
                    beam_k: int = 1, temperature: float = 1.1) -> list[str]:
    """
    Generate n_total SMILES strings using the model prior (no encoder input).
    Uses batched generation to balance speed and memory.
    """
    results: list[str] = []
    generated = 0
    t0 = time.perf_counter()

    while generated < n_total:
        this_batch = min(batch_size, n_total - generated)
        props = make_prop_tensor(qed, logp, mw, sa, prop_mean, prop_std, this_batch)

        with torch.no_grad():
            seq_list = model.generate(
                props,
                max_len=MAX_SEQ_LEN,
                beam_k=beam_k,
                temperature=temperature,
            )

        for seq in seq_list:
            smi = tokenizer.ids_to_smiles(seq)
            results.append(smi)

        generated += this_batch
        elapsed = time.perf_counter() - t0
        speed   = generated / elapsed if elapsed > 0 else 0
        print(f"\r  Generated {generated}/{n_total}  ({speed:.1f} mol/s)  ", end="", flush=True)

    print()
    return results


def load_train_smiles() -> set[str]:
    """Load training SMILES set for novelty check."""
    if not DATA_CSV.exists():
        return set()
    df = pd.read_csv(DATA_CSV, usecols=["smiles"])
    return set(df["smiles"].dropna().str.strip().tolist())


def tanimoto_vs(query_smi: str, smiles_list: list[str]) -> list[float]:
    """Compute Tanimoto similarity of each SMILES in smiles_list vs query_smi."""
    q_mol = Chem.MolFromSmiles(query_smi)
    if q_mol is None:
        return [0.0] * len(smiles_list)
    q_fp = AllChem.GetMorganFingerprintAsBitVect(q_mol, 2, 2048)
    sims = []
    for smi in smiles_list:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            sims.append(0.0)
        else:
            fp  = AllChem.GetMorganFingerprintAsBitVect(mol, 2, 2048)
            sims.append(DataStructs.TanimotoSimilarity(q_fp, fp))
    return sims


# ===========================================================================
# Part 1 — Base CVAE
# ===========================================================================

print("\n" + "="*60)
print("PART 1 — Base CVAE evaluation (best.pt)")
print("="*60)

model_base, tok_base, pmean_base, pstd_base = load_model(
    CKPT_DIR / "best.pt", state_key="model_state"
)

print(f"\n  Generating 1000 molecules (temperature=1.1, multinomial sampling)...")
raw_base = generate_smiles(
    model_base, tok_base, pmean_base, pstd_base,
    n_total=1000, batch_size=50, beam_k=1, temperature=1.1,
)

# Validity
valid_base = [s for s in raw_base if s and Chem.MolFromSmiles(s) is not None]
# Uniqueness
unique_base = list(dict.fromkeys(valid_base))   # preserve order, remove dupes
# Novelty
train_set = load_train_smiles()
novel_base = [s for s in unique_base if s.strip() not in train_set]

n_gen    = len(raw_base)
n_valid  = len(valid_base)
n_unique = len(unique_base)
n_novel  = len(novel_base)

pct_valid  = 100.0 * n_valid  / n_gen    if n_gen    else 0
pct_unique = 100.0 * n_unique / n_valid  if n_valid  else 0
pct_novel  = 100.0 * n_novel  / n_unique if n_unique else 0

print(f"\n  Generated:  {n_gen}")
print(f"  Valid:      {n_valid} ({pct_valid:.1f}%)")
print(f"  Unique:     {n_unique} ({pct_unique:.1f}% of valid)")
print(f"  Novel:      {n_novel} ({pct_novel:.1f}% of unique)")

# ADMET on up to 200 valid molecules
admet_sample = unique_base[:200]
print(f"\n  Running ADMET on {len(admet_sample)} molecules...")
df_admet = score_batch(admet_sample)
df_valid_admet = df_admet[df_admet["valid"] == True]

mean_qed       = float(df_valid_admet["QED"].mean())  if len(df_valid_admet) else 0.0
mean_composite = float(df_valid_admet["composite_score"].mean()) if len(df_valid_admet) else 0.0
n_grade_a      = int((df_valid_admet["grade"] == "A").sum()) if len(df_valid_admet) else 0
n_lipo_pass    = int(df_valid_admet["lipinski_pass"].sum()) if len(df_valid_admet) else 0
pct_grade_a    = 100.0 * n_grade_a / len(df_valid_admet) if len(df_valid_admet) else 0.0

print(f"  Mean QED:          {mean_qed:.3f}")
print(f"  Mean composite:    {mean_composite:.1f}")
print(f"  Grade A:           {n_grade_a}/{len(df_valid_admet)} ({pct_grade_a:.0f}%)")
print(f"  Lipinski pass:     {n_lipo_pass}/{len(df_valid_admet)}")

# Save base model output
df_save_base = pd.DataFrame({"smiles": valid_base})
save_path_base = GENERATED_DIR / "base_model_1000.csv"
df_save_base.to_csv(save_path_base, index=False)
print(f"\n  Saved {len(valid_base)} valid molecules to {save_path_base.name}")


# ===========================================================================
# Part 2 — DPP-4 specialist
# ===========================================================================

print("\n" + "="*60)
print("PART 2 — DPP-4 specialist evaluation (dpp4_finetuned.pt)")
print("="*60)

# Try model_state first, fall back to model_state_dict
try:
    model_dpp4, tok_dpp4, pmean_dpp4, pstd_dpp4 = load_model(
        CKPT_DIR / "dpp4_finetuned.pt", state_key="model_state"
    )
except Exception:
    model_dpp4, tok_dpp4, pmean_dpp4, pstd_dpp4 = load_model(
        CKPT_DIR / "dpp4_finetuned.pt", state_key="model_state_dict"
    )

# DPP-4 drug-like conditioning (sitagliptin profile: MW~408, QED~0.71, LogP~1.5, SA~3.1)
# T=0.8 selected by dpp4_temp_sweep.py: best valid%*unique% tradeoff across T=0.7/0.8/0.9/1.0.
# (T=0.7→42% valid/71% unique, T=0.8→47% valid/96% unique, T≥0.9 valid drops to <30%)
print(f"\n  Generating 500 DPP-4 conditioned molecules (QED=0.72, LogP=1.5, MW=380, SA=3.0)...")
raw_dpp4 = generate_smiles(
    model_dpp4, tok_dpp4, pmean_dpp4, pstd_dpp4,
    n_total=500,
    qed=0.72, logp=1.5, mw=380.0, sa=3.0,
    batch_size=50, beam_k=1, temperature=0.8,
)

valid_dpp4  = [s for s in raw_dpp4 if s and Chem.MolFromSmiles(s) is not None]
unique_dpp4 = list(dict.fromkeys(valid_dpp4))

pct_valid_dpp4 = 100.0 * len(valid_dpp4) / len(raw_dpp4) if raw_dpp4 else 0.0

print(f"\n  Generated:  {len(raw_dpp4)}")
print(f"  Valid:      {len(valid_dpp4)} ({pct_valid_dpp4:.1f}%)")

# Tanimoto vs sitagliptin
print(f"\n  Computing Tanimoto vs sitagliptin for {len(unique_dpp4)} molecules...")
sims_dpp4 = tanimoto_vs(SITAGLIPTIN, unique_dpp4)
mean_tan  = float(np.mean(sims_dpp4)) if sims_dpp4 else 0.0
max_tan   = float(np.max(sims_dpp4))  if sims_dpp4 else 0.0
n_tan_03  = sum(s > 0.3 for s in sims_dpp4)

print(f"  Mean Tanimoto:   {mean_tan:.3f}")
print(f"  Max Tanimoto:    {max_tan:.3f}")
print(f"  Tanimoto > 0.3:  {n_tan_03}")

# ADMET on DPP4 valid molecules
print(f"\n  Running ADMET on {len(unique_dpp4)} DPP-4 molecules...")
df_admet_dpp4 = score_batch(unique_dpp4)
df_valid_dpp4 = df_admet_dpp4[df_admet_dpp4["valid"] == True]

mean_comp_dpp4 = float(df_valid_dpp4["composite_score"].mean()) if len(df_valid_dpp4) else 0.0
n_grade_a_dpp4 = int((df_valid_dpp4["grade"] == "A").sum()) if len(df_valid_dpp4) else 0
pct_grade_a_dpp4 = 100.0 * n_grade_a_dpp4 / len(df_valid_dpp4) if len(df_valid_dpp4) else 0.0

print(f"  Mean ADMET composite:  {mean_comp_dpp4:.1f}")
print(f"  Grade A:               {n_grade_a_dpp4}/{len(df_valid_dpp4)} ({pct_grade_a_dpp4:.0f}%)")


# ===========================================================================
# Part 3 — Investor summary
# ===========================================================================

report = f"""
╔══════════════════════════════════════════════════════╗
║         GENOROVA AI — MODEL PERFORMANCE REPORT       ║
╠══════════════════════════════════════════════════════╣
║  Base CVAE (epoch 9, ~10K molecules, CPU only)       ║
║    Validity:    {pct_valid:.0f}%   (JT-VAE benchmark: 100%)        ║
║    Uniqueness:  {pct_unique:.0f}%                                   ║
║    Novelty:     {pct_novel:.0f}%                                   ║
║    Mean QED:    {mean_qed:.2f} (drug-like threshold: 0.5)      ║
║    Grade A:     {pct_grade_a:.0f}%  of scored molecules          ║
╠══════════════════════════════════════════════════════╣
║  DPP-4 Specialist (fine-tuned on 2,273 actives)     ║
║    Valid molecules:  {len(valid_dpp4)}/500                           ║
║    Mean Tanimoto:    {mean_tan:.2f} vs sitagliptin             ║
║    Grade A ADMET:    {pct_grade_a_dpp4:.0f}%                             ║
╚══════════════════════════════════════════════════════╝
"""

print("\n" + "="*60)
print("PART 3 — Investor Summary")
print("="*60)
print(report)

# Save report
report_path = OUTPUTS_DIR / "MODEL_PERFORMANCE_REPORT.txt"
with open(report_path, "w", encoding="utf-8") as f:
    f.write("GENOROVA AI — MODEL PERFORMANCE REPORT\n")
    f.write("Generated: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    f.write("="*60 + "\n\n")

    f.write("PART 1 — BASE CVAE (best.pt, epoch 9)\n")
    f.write(f"  Generated:         {n_gen}\n")
    f.write(f"  Valid:             {n_valid} ({pct_valid:.1f}%)\n")
    f.write(f"  Unique:            {n_unique} ({pct_unique:.1f}%)\n")
    f.write(f"  Novel:             {n_novel} ({pct_novel:.1f}%)\n")
    f.write(f"  Mean QED:          {mean_qed:.3f}\n")
    f.write(f"  Mean composite:    {mean_composite:.1f}\n")
    f.write(f"  Grade A:           {pct_grade_a:.0f}%\n")
    f.write(f"  Lipinski pass:     {n_lipo_pass}/{len(df_valid_admet)}\n\n")

    f.write("PART 2 — DPP-4 SPECIALIST (dpp4_finetuned.pt, epoch 18)\n")
    f.write(f"  Generated:         500\n")
    f.write(f"  Valid:             {len(valid_dpp4)} ({pct_valid_dpp4:.1f}%)\n")
    f.write(f"  Mean Tanimoto:     {mean_tan:.3f} vs sitagliptin\n")
    f.write(f"  Max Tanimoto:      {max_tan:.3f}\n")
    f.write(f"  Tanimoto > 0.3:    {n_tan_03}\n")
    f.write(f"  Mean composite:    {mean_comp_dpp4:.1f}\n")
    f.write(f"  Grade A:           {pct_grade_a_dpp4:.0f}%\n\n")

    f.write(report)

print(f"Full report saved to: {report_path}")
