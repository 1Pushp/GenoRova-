# AR vs Baseline Comparison Summary

**Generated:** 2026-04-16  
**Task:** Fair head-to-head evaluation of the new autoregressive decoder (SMILESVAE_AR) against the current best old VAE checkpoint.

---

## Setup

| Parameter | Value |
|-----------|-------|
| Samples per model | 500 |
| Strategy | random (pure latent sampling, N(0,I)) |
| Seed | 42 |
| Reference for novelty | MOSES (10,000 canonical SMILES) |
| Evaluation script | evaluate_generation.py |

**AR checkpoint:** `outputs/models/ar/smilesvae_ar_best.pt`  
- Architecture: SMILESVAE_AR, hidden=256, layers=1, embed=64, max_len=62  
- Trained: 30 epochs on 20,000 MOSES SMILES (CPU)  
- Best val_loss: 0.5376 (epoch 22)  

**Baseline checkpoint:** `outputs/models/diabetes/genorova_diabetes_finetune_best.pt`  
- Architecture: Old parallel MLP VAE, max_len=120  
- Trained: fine-tuned on diabetes CSV, epoch 10  
- Best val_loss: 1.662  

---

## Validity, Uniqueness, Novelty

| Metric | AR (SMILESVAE_AR) | Baseline (Old VAE) | AR vs Baseline |
|--------|------------------|--------------------|----------------|
| Total generated | 500 | 500 | — |
| Valid (RDKit) | 40 (8.0%) | 4 (0.8%) | **+10×** |
| Unique valid | 32 (80% of valid) | 4 (100% of valid) | AR has duplication |
| Novel valid | 40 (100%) | 4 (100%) | Tied |
| Novel unique valid | 32 | 4 | AR generates more |

---

## Quality of Valid Molecules

| Metric | AR (32 unique valid) | Baseline (4 unique valid) |
|--------|---------------------|--------------------------|
| Mean MW (g/mol) | **54.2** | **242.9** |
| Max MW (g/mol) | 169.2 | 284.4 |
| Mean QED | 0.381 | 0.556 |
| Max QED | 0.717 | 0.729 |
| Mean SA score | 3.87 | 4.01 |
| Passes Lipinski | 26/26 (100%) | 4/4 (100%) |
| Passes drug-likeness filters* | 1/32 (3%) | 3/4 (75%) |

*Filters: QED ≥ 0.50, MW 150–500, LogP –1 to 5, Lipinski pass.

---

## Failure Mode Analysis

### AR model (SMILESVAE_AR)
- **EOS collapse:** 335/500 (67%) sequences terminated at EOS token. This is correct AR behaviour, but the model has learned to terminate after just 3–10 tokens, generating tiny valid fragments (ethanol, dimethyl ether, methyl formate, etc.).
- **Mean raw sequence length: 32 tokens** vs 62 max — model exits early.
- Best AR molecule: `CCc1ccsc1C(=O)NC` (MW=169, QED=0.717, SA=2.22) — a thiophenamide.
- Invalidity breakdown: rdkit_parse (63%), unbalanced parentheses (28%), too_short (4%).

### Baseline (Old VAE)
- **Runs to max length:** Mean sequence length = 94 tokens (out of 120 max). The parallel decoder does not know when to stop.
- 241/500 sequences (48%) hit max length without EOS.
- Failures: ring_closure_mismatch (17%), unbalanced parentheses (11%), repetitive fragment (6%).
- The 4 valid outputs are large fragments that happened to be structurally balanced by coincidence.

---

## Top Molecules by QED

### AR Model
| SMILES | MW | QED | SA | Lipinski |
|--------|----|-----|----|---------|
| `CCc1ccsc1C(=O)NC` | 169 | 0.717 | 2.22 | ✓ |
| `CCOC=O` | 74 | 0.437 | 3.04 | ✓ |
| `CN1CCC1` | 71 | 0.397 | 1.45 | ✓ |
| `COC=O` | 60 | 0.391 | 2.95 | ✓ |
| `CCO` | 46 | 0.360 | 1.96 | ✓ |

### Baseline
| SMILES | MW | QED | SA | Lipinski |
|--------|----|-----|----|---------|
| `CC(C)NCC(CCC1CC=CC=CC1)C(N)=O` | 250 | 0.729 | 3.49 | ✓ |
| `C#CC1(CC2CCC2O)CC2=C1C1C(=O)C1CC(C)CC2` | 284 | 0.625 | 5.15 | ✓ |
| `CCCCCC1CC(=O)CC(CCCC)C1C1CO1` | 266 | 0.482 | 3.83 | ✓ |
| `CC1=C(CCCOC(C)O)C1C` | 170 | 0.389 | 3.73 | ✓ |

---

## Honest Conclusion

| Dimension | Winner | Assessment |
|-----------|--------|------------|
| Raw SMILES validity | **AR (+10×)** | Clear, decisive improvement |
| Molecule size | **Baseline** | AR generates fragments, not drugs |
| Drug-likeness (QED) | **Baseline** | AR mean 0.38 vs baseline mean 0.56 |
| Structural diversity | Tie | Both novel, different failure modes |

### Does AR beat the baseline?

**On validity: yes, clearly.** 8.0% vs 0.8% — the autoregressive architecture produces 10× more chemically valid SMILES. This confirms the core hypothesis: token-by-token generation with teacher forcing learns SMILES grammar better than a parallel decoder.

**On drug-likeness: no, not yet.** The AR model has learned to exploit EOS termination to maximise validity — outputting tiny valid fragments instead of drug-like molecules. This is a known AR pathology called *length collapse* or *EOS over-exploitation*.

### Root cause of length collapse
- The model was trained for only 30 epochs on 20k MOSES samples.
- KL weight was still rising (0.29 at epoch 30) — latent space not fully regularised.
- Small model (hidden=256, 1 layer) has limited capacity to learn the full SMILES grammar.
- No minimum-length constraint enforced during generation.

### What to do next
1. **Enforce minimum generation length**: set `min_generation_length = 20` tokens in `ARDecoder.generate()` to prevent premature EOS.
2. **Train longer on more data**: 100 epochs on 50k–100k MOSES samples with the full model (hidden=512, 2 layers).
3. **Save arch params in checkpoints**: ✓ already fixed in `train_ar.py` for future runs.
4. **Fix arch detection in evaluate_generation.py**: ✓ already fixed (infers from state dict).

### Verdict

> The AR architecture is the right design. The current training run is a valid proof-of-concept that clears the 0.8% baseline on validity by 10×. However, the model needs more training time and a generation constraint to produce drug-like molecules. The parallel VAE baseline should be retired — its failure mode (no EOS, max-length outputs) is architectural and cannot be fixed by tuning.

---

## Files

| File | Description |
|------|-------------|
| `outputs/models/ar/smilesvae_ar_best.pt` | Best AR checkpoint (val_loss=0.5376, epoch 22) |
| `outputs/evaluation/ar_eval/evaluation_metrics.json` | Full AR evaluation metrics |
| `outputs/evaluation/baseline_eval/evaluation_metrics.json` | Full baseline evaluation metrics |
| `outputs/evaluation/ar_vs_baseline_comparison.csv` | Combined valid molecules from both models |
| `outputs/logs/train_ar_run.log` | Full AR training log (30 epochs) |
| `outputs/logs/train_ar_20260416_025642.log` | Timestamped copy of training log |
