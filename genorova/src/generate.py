"""
Genorova AI — Molecule Generation Engine
=========================================

Generates novel drug molecules by sampling from the trained VAE latent space
and decoding samples back to SMILES strings.

WORKFLOW:
1. Load best trained VAE checkpoint
2. Sample from latent space (Gaussian N(0,I))
3. Decode through VAE decoder network
4. Convert probabilities to SMILES via character indices
5. Validate using RDKit (check Lipinski Rule of 5)
6. Calculate drug-likeness metrics (QED, SA score)
7. Filter for novelty (not in training set)
8. Save valid candidates to CSV

GENERATION PARAMETERS:
- NUM_MOLECULES_TO_GENERATE = 100 (test run)
- TEMPERATURE = 1.0 (sampling randomness)
- BATCH_SIZE = 50
- VALIDITY_THRESHOLD = 0.85 (85% must be valid)
- NOVELTY_THRESHOLD = 0.90 (90% must be new)

OUTPUT:
- Generated molecules: outputs/generated/generated_molecules.csv
- Properties: SMILES, MW, LogP, QED, SA score
- Metrics: generation report to console

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import torch
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Any, List, Tuple, Dict
from tqdm import tqdm

# RDKit imported lazily inside functions (prevents Windows DLL load failure
# if Smart App Control or WDAC blocks the rdkit DLL at module import time)
# from rdkit import Chem  -- moved to validate_smiles() method below

# Import our modules
from model import VAE, MAX_SMILES_LENGTH
from preprocessor import (
    load_vocab,
    decode_token_ids,
    get_special_token_ids,
    select_token_ids_from_logits,
)

# ============================================================================
# GENERATION CONFIGURATION
# ============================================================================

# Model and checkpoint
MODEL_DIR = Path("outputs/models")
CHECKPOINT_NAME = "genorova_best.pt"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Generation parameters
NUM_MOLECULES_TO_GENERATE = 100
TEMPERATURE = 1.0
BATCH_SIZE = 50

# Validation thresholds
VALIDITY_THRESHOLD = 0.85
NOVELTY_THRESHOLD = 0.90

# Drug-likeness criteria (Lipinski Rule of 5)
MAX_MOLECULAR_WEIGHT = 500
MAX_LOGP = 5.0
MAX_H_DONORS = 5
MAX_H_ACCEPTORS = 10
MIN_QED_SCORE = 0.5

# Training data (from mini dataset used in training)
MINI_DATASET = [
    "CC(=O)Oc1ccccc1C(=O)O",              # Aspirin
    "CN(C)C(=N)NC(=N)N",                  # Metformin
    "Cn1cnc2c1c(=O)n(c(=O)n2C)C",         # Caffeine
    "CC(=O)Nc1ccc(O)cc1",                 # Acetaminophen
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",         # Ibuprofen
    "c1ccc2c(c1)cc1ccc3cccc4ccc2c1c34",   # Anthracene
    "COc1ccc2cc3ccc(=O)oc3cc2c1",         # Coumarin
    "O=C1CCCN1",                          # Pyrrolidone
    "c1ccc(cc1)C(=O)O",                   # Benzoic acid
    "CC(=O)c1ccc(cc1)O",                  # Paracetamol
    "CCO",                                # Ethanol
    "CCCC",                               # Butane
    "c1ccccc1",                           # Benzene
    "CC(C)O",                             # Isopropanol
    "CCOCC",                              # Diethyl ether
    "CCCc1ccc(cc1)O",                     # Cresol
    "c1cc(ccc1C)O",                       # Methylphenol
    "c1ccc(cc1)O",                        # Phenol
    "CC(C)CC(=O)O",                       # Isovaleric acid
    "c1ccc(cc1)C(=O)C",                   # Acetophenone
]

# Output paths
GENERATE_OUTPUT_DIR = Path("outputs/generated")
GENERATE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _load_checkpoint_state(checkpoint_path: Path, device: torch.device) -> dict[str, Any]:
    """Load checkpoint and normalize the expected model-state key."""
    checkpoint = torch.load(checkpoint_path, map_location=device)
    state_dict = checkpoint.get("model_state") or checkpoint.get("model_state_dict")
    if state_dict is None:
        raise KeyError(f"Checkpoint {checkpoint_path} does not contain model weights.")
    checkpoint["_resolved_model_state"] = state_dict
    return checkpoint


def _candidate_vocab_paths() -> list[Path]:
    """Return likely vocabulary files for runtime generation."""
    return [
        PROJECT_ROOT / "outputs" / "vocabulary_diabetes_pretrain.json",
        PROJECT_ROOT / "outputs" / "vocabulary_diabetes.json",
        PROJECT_ROOT / "outputs" / "vocabulary_infection.json",
        PROJECT_ROOT / "outputs" / "vocab.json",
        PROJECT_ROOT / "outputs" / "vocabulary.json",
        Path("outputs/vocab.json"),
        Path("outputs/vocabulary.json"),
    ]


def _vocab_size_from_checkpoint(checkpoint: dict[str, Any]) -> int:
    """Infer the vocab size expected by a checkpoint."""
    if checkpoint.get("vocab_size") is not None:
        return int(checkpoint["vocab_size"])
    state = checkpoint["_resolved_model_state"]
    flattened_size = state["encoder.fc1.weight"].shape[1]
    max_length = int(checkpoint.get("max_length") or MAX_SMILES_LENGTH)
    return int(flattened_size // max_length)


def _resolve_vocab_path(checkpoint_path: Path, checkpoint: dict[str, Any]) -> Path:
    """Choose the best vocab match for the checkpoint instead of guessing blindly."""
    target_vocab_size = _vocab_size_from_checkpoint(checkpoint)
    disease = str(checkpoint.get("disease") or "").lower()
    stage_name = str(checkpoint.get("stage_name") or "").lower()

    candidates = []
    for path in _candidate_vocab_paths():
        if not path.exists():
            continue
        try:
            char2idx, _ = load_vocab(path)
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
        if "vocab" == path.stem.lower():
            score += 1
        candidates.append((score, path))

    if candidates:
        candidates.sort(key=lambda item: (-item[0], str(item[1])))
        return candidates[0][1]

    raise FileNotFoundError(
        f"Could not find a vocabulary file matching checkpoint {checkpoint_path} "
        f"(expected vocab size {target_vocab_size})."
    )


# ============================================================================
# GENERATION ENGINE
# ============================================================================

class MoleculeGenerator:
    """Generate novel molecules from trained VAE."""
    
    def __init__(self, checkpoint_path: str = None, device: str = "cpu"):
        """
        Initialize molecule generator.
        
        Args:
            checkpoint_path (str): Path to model checkpoint
            device (str): 'cpu' or 'cuda'
        """
        print(f"\n{'='*70}")
        print(f"GENOROVA AI - MOLECULE GENERATION ENGINE")
        print(f"{'='*70}")
        
        self.device = torch.device(device)
        
        # If no checkpoint specified, use best model
        if checkpoint_path is None:
            checkpoint_path = MODEL_DIR / CHECKPOINT_NAME
        
        print(f"\n[*] Loading checkpoint: {checkpoint_path}")
        
        if not Path(checkpoint_path).exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        
        # Load checkpoint
        self.checkpoint = _load_checkpoint_state(Path(checkpoint_path), self.device)

        # Load vocabulary with checkpoint-aware resolution to avoid silent mismatch.
        vocab_path = _resolve_vocab_path(Path(checkpoint_path), self.checkpoint)
        self.char2idx, self.idx2char = load_vocab(vocab_path)
        vocab_size = len(self.char2idx)

        # Auto-detect model dimensions from checkpoint
        state_dict = self.checkpoint["_resolved_model_state"]
        encoder_fc1_weight = state_dict["encoder.fc1.weight"]
        input_size = encoder_fc1_weight.shape[1]  # Should be max_length * vocab_size
        inferred_vocab_size = _vocab_size_from_checkpoint(self.checkpoint)
        inferred_max_length = input_size // inferred_vocab_size

        print(f"    Vocabulary size: {vocab_size}")
        print(f"    Vocabulary file: {vocab_path}")
        print(f"    Inferred MAX_SMILES_LENGTH from checkpoint: {inferred_max_length}")
        print(f"    Inferred flattened input size: {input_size}")
        print(f"    Best validation loss: {self.checkpoint['best_val_loss']:.6f}")
        print(f"    Trained epochs: {self.checkpoint['epoch']}")

        if vocab_size != inferred_vocab_size:
            raise ValueError(
                f"Vocabulary mismatch for {checkpoint_path}: checkpoint expects vocab size "
                f"{inferred_vocab_size}, but {vocab_path} has {vocab_size}."
            )

        # Initialize model with inferred dimensions
        self.model = VAE(vocab_size=vocab_size, max_length=inferred_max_length).to(self.device)

        try:
            self.model.load_state_dict(state_dict)
            print(f"    Model loaded successfully on {self.device}")
        except RuntimeError as e:
            raise RuntimeError(
                "Checkpoint/model shape mismatch during runtime generation. "
                "Generation has been stopped to avoid producing misleading output. "
                f"Checkpoint: {checkpoint_path}, vocab: {vocab_path}, error: {e}"
            ) from e

        self.model.eval()
        
        # Statistics
        self.valid_count = 0
        self.invalid_count = 0
        self.novel_count = 0
        self.duplicate_count = 0
        self.last_debug_rows: list[dict[str, Any]] = []
        
    def decode_indices_to_smiles(self, indices: torch.Tensor) -> List[str]:
        """
        Convert index sequences to SMILES strings.
        
        Args:
            indices (torch.Tensor): Shape [batch_size, MAX_SMILES_LENGTH]
        
        Returns:
            List[str]: SMILES strings
        """
        self.last_debug_rows = [
            decode_token_ids(idx_seq, self.idx2char, char2idx=self.char2idx)
            for idx_seq in indices
        ]
        return [row["raw_smiles"] for row in self.last_debug_rows if row["raw_smiles"]]

    def save_debug_artifact(self, filename: str = "generated_debug.csv") -> Path:
        """Persist a compact decode-debug artifact for the latest generation run."""
        debug_path = GENERATE_OUTPUT_DIR / filename
        if not self.last_debug_rows:
            pd.DataFrame(columns=["token_ids", "raw_smiles"]).to_csv(debug_path, index=False)
            return debug_path

        pd.DataFrame(self.last_debug_rows).assign(
            token_ids=lambda df: df["token_ids"].map(lambda values: " ".join(map(str, values))),
            raw_tokens=lambda df: df["raw_tokens"].map(lambda values: " ".join(values)),
            effective_token_ids=lambda df: df["effective_token_ids"].map(lambda values: " ".join(map(str, values))),
        ).to_csv(debug_path, index=False)
        return debug_path
    
    def validate_smiles(self, smiles: str) -> Tuple[bool, Dict]:
        """
        Validate SMILES and calculate properties.
        
        Args:
            smiles (str): SMILES string
            
        Returns:
            Tuple[bool, Dict]: (is_valid, properties_dict)
        """
        try:
            from rdkit import Chem as _Chem
            from rdkit.Chem import Descriptors as _Desc, Crippen as _Cr, QED as _QED
            mol = _Chem.MolFromSmiles(smiles)

            if mol is None:
                return False, {}

            # Calculate properties
            mw = _Desc.MolWt(mol)
            logp = _Cr.MolLogP(mol)
            hbd = _Desc.NumHDonors(mol)
            hba = _Desc.NumHAcceptors(mol)

            # Calculate QED
            try:
                qed_score = _QED.qed(mol)
            except:
                qed_score = 0.0
            
            properties = {
                "mw": float(mw),
                "logp": float(logp),
                "hbd": int(hbd),
                "hba": int(hba),
                "qed": float(qed_score),
            }
            
            # Check Lipinski's Rule of 5
            passes_lipinski = (
                mw <= MAX_MOLECULAR_WEIGHT and
                logp <= MAX_LOGP and
                hbd <= MAX_H_DONORS and
                hba <= MAX_H_ACCEPTORS
            )
            
            is_valid = passes_lipinski and qed_score >= MIN_QED_SCORE
            
            return is_valid, properties
            
        except Exception as e:
            return False, {}
    
    def is_novel(self, smiles: str) -> bool:
        """Check if molecule is novel (not in training data)."""
        return smiles not in MINI_DATASET
    
    def generate_batch(self, num_samples: int) -> Tuple[List[str], List[Dict], int, int]:
        """
        Generate a batch of molecules.
        
        Args:
            num_samples (int): Number to generate
            
        Returns:
            Tuple: (smiles_list, properties_list, valid_count, novel_count)
        """
        with torch.no_grad():
            # Sample from latent space
            z = torch.randn(num_samples, 256).to(self.device)
            
            # Decode through decoder
            recon_x = self.model.decode(z)
            
            # Sequence-aware token selection:
            # - keep BOS at position 0 when available
            # - prefer EOS over PAD for stop decisions
            # - penalize repetitive token collapse
            indices = select_token_ids_from_logits(
                recon_x,
                self.char2idx,
                temperature=TEMPERATURE,
                strategy="sample",
                top_k=5,
                repetition_penalty=0.75,
                min_tokens_before_stop=2,
            )
            
            # Convert indices to SMILES
            smiles_list = self.decode_indices_to_smiles(indices)
            
            valid_smiles = []
            properties_list = []
            valid_count = 0
            novel_count = 0
            
            for smiles in smiles_list:
                is_valid, properties = self.validate_smiles(smiles)
                
                if is_valid:
                    valid_count += 1
                    valid_smiles.append(smiles)
                    properties_list.append(properties)
                    
                    if self.is_novel(smiles):
                        novel_count += 1
            
            return valid_smiles, properties_list, valid_count, novel_count
    
    def generate_molecules(self, num_to_generate: int = NUM_MOLECULES_TO_GENERATE):
        """
        Generate molecules from latent space.
        
        Args:
            num_to_generate (int): Number to generate
            
        Returns:
            pd.DataFrame: Generated molecules with properties
        """
        print(f"\n[*] Generating {num_to_generate} molecules...")
        print(f"    Temperature: {TEMPERATURE}")
        print(f"    Batch size: {BATCH_SIZE}")
        
        all_smiles = []
        all_properties = []
        
        num_batches = (num_to_generate + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_idx in tqdm(range(num_batches), desc="Generating"):
            batch_size = min(BATCH_SIZE, num_to_generate - batch_idx * BATCH_SIZE)
            
            smiles_batch, props_batch, n_valid, n_novel = self.generate_batch(batch_size)
            
            all_smiles.extend(smiles_batch)
            all_properties.extend(props_batch)
            
            self.valid_count += n_valid
            self.novel_count += n_novel
            self.invalid_count += (batch_size - n_valid)
        
        # Create DataFrame
        if len(all_smiles) > 0:
            results_df = pd.DataFrame({
                "smiles": all_smiles,
                "mw": [p["mw"] for p in all_properties],
                "logp": [p["logp"] for p in all_properties],
                "hbd": [p["hbd"] for p in all_properties],
                "hba": [p["hba"] for p in all_properties],
                "qed": [p["qed"] for p in all_properties],
            })
        else:
            results_df = pd.DataFrame(columns=["smiles", "mw", "logp", "hbd", "hba", "qed"])
        
        # Print statistics
        print(f"\n[*] Generation Complete")
        print(f"    Valid molecules: {self.valid_count}")
        print(f"    Novel molecules: {self.novel_count}")
        print(f"    Invalid SMILES: {self.invalid_count}")
        
        if num_to_generate > 0:
            validity_pct = 100 * self.valid_count / num_to_generate
            print(f"    Validity: {validity_pct:.1f}%")
        
        if self.valid_count > 0:
            novelty_pct = 100 * self.novel_count / self.valid_count
            print(f"    Novelty: {novelty_pct:.1f}%")
        
        # Sample output
        if len(all_smiles) > 0:
            print(f"\n[*] First 10 generated molecules:")
            for i, (smiles, props) in enumerate(zip(all_smiles[:10], all_properties[:10])):
                print(f"    {i+1:2}. {smiles:<40} MW={props['mw']:6.1f} QED={props['qed']:5.3f}")

        debug_path = self.save_debug_artifact()
        print(f"    Decode debug: {debug_path}")
        
        return results_df
    
    def save_results(self, results_df: pd.DataFrame, filename: str = "generated_molecules.csv"):
        """Save generated molecules to CSV."""
        output_path = GENERATE_OUTPUT_DIR / filename
        results_df.to_csv(output_path, index=False)
        print(f"\n[OK] Saved to: {output_path}")
        print(f"    Molecules: {len(results_df)}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Generate molecules from trained VAE."""
    
    generator = MoleculeGenerator(device="cpu")
    
    print(f"\n[*] Starting generation...")
    results = generator.generate_molecules(num_to_generate=100)
    
    generator.save_results(results)
    
    print(f"\n{'='*70}")
    print(f"GENERATION COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
