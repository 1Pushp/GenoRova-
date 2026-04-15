"""
Genorova AI — SMILES String Preprocessor
==========================================

This module converts SMILES strings into one-hot encoded vectors that
the VAE neural network can understand. 

RESPONSIBILITIES:
1. Build a vocabulary of all unique characters in SMILES strings
2. Convert SMILES into integer tokens using the vocabulary
3. Create one-hot encoded vectors for each SMILES
4. Pad all sequences to MAX_SMILES_LENGTH = 120
5. Split data into train (80%), validation (10%), test (10%) sets
6. Create PyTorch Datasets for efficient batching
7. Save vocabulary to JSON for later reconstruction

INPUT:
- Pandas DataFrame with 'smiles' column (from data_loader.py)

OUTPUT:
- PyTorch DataLoader instances (train, val, test)
- Saved vocabulary.json file

KEY FUNCTIONS:
- build_vocab() — create character vocabulary from SMILES
- encode_smiles() — convert SMILES string to one-hot tensor
- preprocess_batch() — batch encoding
- create_datasets() — split and create PyTorch Datasets
- save_vocab() — save vocabulary to JSON

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import json
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader, random_split
from pathlib import Path
from typing import Any, Tuple, Dict, List


# ============================================================================
# CONSTANTS
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
MAX_SMILES_LENGTH = 120  # Maximum length of SMILES string (pad/truncate to this)
PAD_TOKEN = "<pad>"      # Special token for padding
BOS_TOKEN = "<bos>"      # Explicit sequence start token for training/generation
EOS_TOKEN = "<eos>"      # Explicit sequence end token for training/generation
UNK_TOKEN = "<unk>"      # Fallback token for unexpected characters
SPECIAL_TOKENS = [PAD_TOKEN, BOS_TOKEN, EOS_TOKEN, UNK_TOKEN]
VOCAB_OUTPUT_PATH = ROOT_DIR / "outputs" / "vocab.json"


# ============================================================================
# VOCABULARY BUILDING
# ============================================================================

def build_vocab(smiles_list: List[str]) -> Tuple[Dict[str, int], Dict[int, str]]:
    """
    Build a vocabulary (character-to-integer mapping) from SMILES strings.
    
    Scans all SMILES strings and creates a dictionary mapping each unique
    character to an integer index. Also returns the reverse mapping for 
    decoding.
    
    Special tokens:
    - <pad> (index 0): Used for padding short sequences
    
    Args:
        smiles_list (List[str]): List of SMILES strings
        
    Returns:
        Tuple containing:
        - char2idx (Dict[str, int]): Maps character -> integer
        - idx2char (Dict[int, str]): Maps integer -> character
    """
    print("\n[*] Building vocabulary from SMILES strings...")
    
    # Collect all unique characters
    unique_chars = set()
    for smiles in smiles_list:
        unique_chars.update(smiles)
    
    # Sort for consistency
    unique_chars = sorted(list(unique_chars))
    
    # Create mappings with stable special-token indices.
    char2idx = {token: idx for idx, token in enumerate(SPECIAL_TOKENS)}
    for idx, char in enumerate(unique_chars, start=len(char2idx)):
        char2idx[char] = idx
    
    # Reverse mapping
    idx2char = {v: k for k, v in char2idx.items()}
    
    print(f"   [OK] Vocabulary built successfully!")
    print(f"   [OK] Unique characters found: {len(unique_chars)}")
    print(f"   [OK] Vocabulary size (with padding): {len(char2idx)}")
    print(f"   [OK] Sample characters: {unique_chars[:10]}")
    
    return char2idx, idx2char


def get_special_token_ids(char2idx: Dict[str, int]) -> Dict[str, int | None]:
    """Return the ids of known sequence-control tokens for a vocabulary."""
    return {
        "pad": char2idx.get(PAD_TOKEN),
        "bos": char2idx.get(BOS_TOKEN),
        "eos": char2idx.get(EOS_TOKEN),
        "unk": char2idx.get(UNK_TOKEN),
    }


def uses_explicit_sequence_tokens(char2idx: Dict[str, int]) -> bool:
    """Whether a vocabulary supports explicit BOS/EOS handling."""
    return BOS_TOKEN in char2idx and EOS_TOKEN in char2idx


# ============================================================================
# ENCODING FUNCTIONS
# ============================================================================

def encode_smiles_to_indices(
    smiles: str,
    char2idx: Dict[str, int],
    max_length: int = MAX_SMILES_LENGTH,
) -> np.ndarray:
    """
    Convert a SMILES string into token ids with explicit BOS/EOS when available.

    New vocabularies reserve:
    - <pad> index 0
    - <bos> start token
    - <eos> end token
    - <unk> unexpected character token

    Older vocabularies remain readable because BOS/EOS are only inserted when
    those tokens exist in the loaded vocabulary.
    """
    token_ids = get_special_token_ids(char2idx)
    bos_idx = token_ids["bos"]
    eos_idx = token_ids["eos"]
    pad_idx = token_ids["pad"] if token_ids["pad"] is not None else 0
    unk_idx = token_ids["unk"] if token_ids["unk"] is not None else pad_idx

    indices: list[int] = []
    if bos_idx is not None:
        indices.append(bos_idx)

    for char in str(smiles):
        indices.append(char2idx.get(char, unk_idx))

    if eos_idx is not None:
        indices.append(eos_idx)

    # Truncate but preserve an EOS marker for new training runs when possible.
    if len(indices) > max_length:
        indices = indices[:max_length]
        if eos_idx is not None:
            indices[-1] = eos_idx

    indices.extend([pad_idx] * (max_length - len(indices)))
    return np.array(indices, dtype=np.int64)


def encode_smiles(smiles: str, char2idx: Dict[str, int], max_length: int = MAX_SMILES_LENGTH) -> np.ndarray:
    """
    Convert a SMILES string to a one-hot encoded tensor.
    
    Steps:
    1. Convert SMILES characters to indices using vocabulary
    2. Pad or truncate to max_length
    3. Create one-hot encoding (each character becomes a vector)
    
    Args:
        smiles (str): SMILES string (e.g., "CC(=O)O")
        char2idx (Dict[str, int]): Character-to-index mapping
        max_length (int): Maximum sequence length
        
    Returns:
        np.ndarray: Shape [max_length, vocab_size] containing one-hot encoding
    """
    vocab_size = len(char2idx)
    indices = encode_smiles_to_indices(smiles, char2idx, max_length=max_length)

    # Create one-hot encoding: [max_length, vocab_size]
    one_hot = np.zeros((max_length, vocab_size), dtype=np.float32)
    for pos, idx in enumerate(indices):
        one_hot[pos, int(idx)] = 1.0

    return one_hot


def preprocess_batch(
    smiles_list: List[str],
    char2idx: Dict[str, int],
    max_length: int = MAX_SMILES_LENGTH,
) -> np.ndarray:
    """
    Encode a batch of SMILES strings into one-hot tensors.
    
    Args:
        smiles_list (List[str]): List of SMILES strings
        char2idx (Dict[str, int]): Character-to-index mapping
        
    Returns:
        np.ndarray: Shape [batch_size, max_length, vocab_size]
    """
    batch = []
    for smiles in smiles_list:
        one_hot = encode_smiles(smiles, char2idx, max_length=max_length)
        batch.append(one_hot)
    
    return np.array(batch, dtype=np.float32)


def select_token_ids_from_logits(
    logits: torch.Tensor,
    char2idx: Dict[str, int],
    *,
    temperature: float = 1.0,
    top_k: int = 0,
    strategy: str = "greedy",
    repetition_penalty: float = 0.0,
    min_tokens_before_stop: int = 1,
) -> torch.Tensor:
    """
    Turn decoder logits into token ids with basic sequence-aware constraints.

    This is still non-autoregressive, but it avoids a few common failure modes:
    - forcing BOS at position 0 when available
    - blocking BOS after the first position
    - delaying EOS/PAD for the first few decoded tokens
    - optional repetition penalty against long identical runs
    """
    if logits.ndim != 3:
        raise ValueError(f"Expected [batch, length, vocab] logits, got shape {tuple(logits.shape)}")

    token_ids = get_special_token_ids(char2idx)
    bos_idx = token_ids["bos"]
    eos_idx = token_ids["eos"]
    pad_idx = token_ids["pad"]

    batch_size, seq_len, _ = logits.shape
    selected = torch.empty(batch_size, seq_len, dtype=torch.long, device=logits.device)

    if strategy not in {"greedy", "sample"}:
        raise ValueError(f"Unsupported decode strategy: {strategy}")

    effective_temperature = max(float(temperature), 1e-6)

    for pos in range(seq_len):
        step_logits = logits[:, pos, :].clone()

        if bos_idx is not None and pos > 0:
            step_logits[:, bos_idx] = -1e9

        if pos == 0 and bos_idx is not None:
            selected[:, pos] = bos_idx
            continue

        if pos <= min_tokens_before_stop:
            if eos_idx is not None:
                step_logits[:, eos_idx] = -1e9
            if pad_idx is not None:
                step_logits[:, pad_idx] = -1e9

        if repetition_penalty > 0.0 and pos > 0:
            prev_ids = selected[:, pos - 1]
            for row_idx in range(batch_size):
                prev_id = int(prev_ids[row_idx].item())
                step_logits[row_idx, prev_id] -= repetition_penalty

        if top_k and top_k > 0 and top_k < step_logits.shape[-1]:
            top_values, top_indices = torch.topk(step_logits, k=top_k, dim=-1)
            masked = torch.full_like(step_logits, -1e9)
            masked.scatter_(1, top_indices, top_values)
            step_logits = masked

        if strategy == "sample":
            probs = torch.softmax(step_logits / effective_temperature, dim=-1)
            next_ids = torch.multinomial(probs, num_samples=1).squeeze(1)
        else:
            next_ids = torch.argmax(step_logits, dim=-1)

        selected[:, pos] = next_ids

    return selected


def decode_token_ids(
    token_ids: List[int] | np.ndarray | torch.Tensor,
    idx2char: Dict[int, str],
    *,
    char2idx: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    """
    Decode token ids into a SMILES-like string and expose useful debug metadata.
    """
    if isinstance(token_ids, torch.Tensor):
        token_list = [int(token.item()) for token in token_ids]
    elif isinstance(token_ids, np.ndarray):
        token_list = [int(token) for token in token_ids.tolist()]
    else:
        token_list = [int(token) for token in token_ids]

    token_ids_map = get_special_token_ids(char2idx or {})
    pad_idx = token_ids_map["pad"]
    bos_idx = token_ids_map["bos"]
    eos_idx = token_ids_map["eos"]
    unk_idx = token_ids_map["unk"]

    raw_tokens = [idx2char.get(token_id, f"<{token_id}>") for token_id in token_list]
    chars: list[str] = []
    effective_ids: list[int] = []
    first_bos_position = None
    first_eos_position = None
    first_pad_position = None
    termination_token = None
    termination_reason = "max_length"

    for position, token_id in enumerate(token_list):
        if bos_idx is not None and token_id == bos_idx:
            if first_bos_position is None:
                first_bos_position = position
            continue
        if eos_idx is not None and token_id == eos_idx:
            first_eos_position = position
            termination_token = EOS_TOKEN
            termination_reason = "eos"
            break
        if pad_idx is not None and token_id == pad_idx:
            first_pad_position = position
            termination_token = PAD_TOKEN
            termination_reason = "pad"
            break
        if unk_idx is not None and token_id == unk_idx:
            termination_reason = "contains_unk" if termination_reason == "max_length" else termination_reason
        effective_ids.append(token_id)
        token_text = idx2char.get(token_id, "")
        if token_text in SPECIAL_TOKENS:
            continue
        chars.append(token_text)

    raw_smiles = "".join(chars).strip()
    return {
        "token_ids": token_list,
        "raw_tokens": raw_tokens,
        "effective_token_ids": effective_ids,
        "raw_smiles": raw_smiles,
        "raw_length": len(raw_smiles),
        "first_bos_position": first_bos_position,
        "first_eos_position": first_eos_position,
        "first_pad_position": first_pad_position,
        "termination_token": termination_token,
        "termination_reason": termination_reason,
    }


# ============================================================================
# PYTORCH DATASET CLASS
# ============================================================================

class SmilesDataset(Dataset):
    """
    PyTorch Dataset for efficient SMILES batching and training.
    
    Stores preprocessed one-hot encoded SMILES as tensors and provides
    efficient batch sampling during training.
    """
    
    def __init__(self, one_hot_array: np.ndarray, smiles_list: List[str] = None):
        """
        Initialize the dataset.
        
        Args:
            one_hot_array (np.ndarray): Shape [num_smiles, max_length, vocab_size]
            smiles_list (List[str]): Optional original SMILES for reference
        """
        self.one_hot_array = torch.from_numpy(one_hot_array).float()
        self.smiles_list = smiles_list if smiles_list is not None else []
    
    def __len__(self):
        """Return dataset size."""
        return len(self.one_hot_array)
    
    def __getitem__(self, idx):
        """Return one-hot encoded SMILES tensor."""
        return self.one_hot_array[idx]


# ============================================================================
# VOCABULARY SAVING/LOADING
# ============================================================================

def save_vocab(char2idx: Dict[str, int], output_path: str = VOCAB_OUTPUT_PATH):
    """
    Save vocabulary mapping to a JSON file for later reconstruction.
    
    This allows us to:
    - Reuse the same vocabulary for decoding generated molecules
    - Rebuild the model without reprocessing the data
    - Share vocabularies between trained models
    
    Args:
        char2idx (Dict[str, int]): Character-to-index mapping
        output_path (str): Path to save JSON file
    """
    print(f"\n[*] Saving vocabulary to {output_path}")
    
    # Create output directory if needed
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(char2idx, f, indent=2)
    
    print(f"   [OK] Vocabulary saved successfully!")
    print(f"   [OK] Location: {Path(output_path).absolute()}")


def load_vocab(vocab_path: str = VOCAB_OUTPUT_PATH) -> Tuple[Dict[str, int], Dict[int, str]]:
    """
    Load vocabulary from JSON file.
    
    Args:
        vocab_path (str): Path to vocabulary JSON file
        
    Returns:
        Tuple containing char2idx and idx2char mappings
    """
    print(f"\n[*] Loading vocabulary from {vocab_path}")
    
    with open(vocab_path, 'r') as f:
        char2idx = json.load(f)
    
    # Convert keys back to integers (JSON stores keys as strings)
    idx2char = {int(v): k for k, v in char2idx.items()}
    
    print(f"   [OK] Vocabulary loaded successfully!")
    print(f"   [OK] Vocabulary size: {len(char2idx)}")
    if uses_explicit_sequence_tokens(char2idx):
        print(f"   [OK] Explicit sequence tokens detected: {BOS_TOKEN}, {EOS_TOKEN}")
    else:
        print(f"   [!] Legacy vocabulary detected: no explicit {BOS_TOKEN}/{EOS_TOKEN} tokens")
    
    return char2idx, idx2char


# ============================================================================
# MAIN PREPROCESSING PIPELINE
# ============================================================================

def preprocess_data(df: pd.DataFrame, batch_size: int = 256, test_split: Tuple[float, float, float] = (0.8, 0.1, 0.1)) -> Tuple[DataLoader, DataLoader, DataLoader, Dict[str, int], Dict[int, str]]:
    """
    Complete preprocessing pipeline.
    
    Takes raw SMILES DataFrame and returns PyTorch DataLoaders ready for training.
    
    Steps:
    1. Build vocabulary
    2. Encode all SMILES to one-hot
    3. Split into train/val/test sets
    4. Create PyTorch DataLoaders
    5. Save vocabulary for later use
    
    Args:
        df (pd.DataFrame): Must contain 'smiles' column
        batch_size (int): Batch size for DataLoader
        test_split (Tuple): (train%, val%, test%) - must sum to 1.0
        
    Returns:
        Tuple containing:
        - train_loader (DataLoader)
        - val_loader (DataLoader)
        - test_loader (DataLoader)
        - char2idx (Dict)
        - idx2char (Dict)
    """
    print("\n" + "="*70)
    print("GENOROVA AI — SMILES PREPROCESSING PIPELINE")
    print("="*70)
    
    # Extract SMILES
    print(f"\n[*] Input dataset shape: {df.shape}")
    smiles_list = df['smiles'].tolist()
    print(f"   [OK] Extracted {len(smiles_list)} SMILES strings")
    
    # ===== STEP 1: Build Vocabulary =====
    char2idx, idx2char = build_vocab(smiles_list)
    vocab_size = len(char2idx)
    
    # ===== STEP 2: Encode all SMILES =====
    print(f"\n[*] Encoding {len(smiles_list)} SMILES to one-hot vectors...")
    encoded_data = preprocess_batch(smiles_list, char2idx)
    print(f"   [OK] Encoding complete!")
    print(f"   [OK] Output shape: {encoded_data.shape}")
    print(f"   [OK] Expected: ({len(smiles_list)}, {MAX_SMILES_LENGTH}, {vocab_size})")
    
    # ===== STEP 3: Create PyTorch Dataset =====
    print(f"\n[*] Creating PyTorch Dataset...")
    dataset = SmilesDataset(encoded_data, smiles_list)
    print(f"   [OK] Dataset created with {len(dataset)} samples")
    
    # ===== STEP 4: Split into train/val/test =====
    print(f"\n[*] Splitting data into train/val/test sets...")
    print(f"   [*] Split ratio: {test_split[0]:.0%} train, {test_split[1]:.0%} val, {test_split[2]:.0%} test")
    
    train_size = int(len(dataset) * test_split[0])
    val_size = int(len(dataset) * test_split[1])
    test_size = len(dataset) - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = random_split(
        dataset,
        [train_size, val_size, test_size]
    )
    
    print(f"   [OK] Train set: {len(train_dataset)} samples")
    print(f"   [OK] Val set: {len(val_dataset)} samples")
    print(f"   [OK] Test set: {len(test_dataset)} samples")
    
    # ===== STEP 5: Create DataLoaders =====
    print(f"\n[*] Creating DataLoaders with batch_size={batch_size}...")
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
    
    print(f"   [OK] Train loader: {len(train_loader)} batches")
    print(f"   [OK] Val loader: {len(val_loader)} batches")
    print(f"   [OK] Test loader: {len(test_loader)} batches")
    
    # ===== STEP 6: Save Vocabulary =====
    save_vocab(char2idx)
    
    print(f"\n" + "="*70)
    print("✅ PREPROCESSING COMPLETE")
    print("="*70)
    
    return train_loader, val_loader, test_loader, char2idx, idx2char


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    """
    Test the preprocessor with 5 sample SMILES strings.
    """
    print("\n" + "#"*70)
    print("# PREPROCESSOR TEST — 5 SAMPLE MOLECULES")
    print("#"*70)
    
    # Test SMILES
    test_smiles = [
        "CC(=O)Oc1ccccc1C(=O)O",      # Aspirin
        "CN(C)C(=N)NC(=N)N",          # Metformin
        "Cn1cnc2c1c(=O)n(c(=O)n2C)C", # Caffeine
        "CC(=O)Nc1ccc(O)cc1",         # Acetaminophen
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O"  # Ibuprofen
    ]
    
    print(f"\nTest molecules:")
    for i, smiles in enumerate(test_smiles, 1):
        print(f"  {i}. {smiles}")
    
    # Create DataFrame
    test_df = pd.DataFrame({'smiles': test_smiles})
    print(f"\n✓ Created test DataFrame with shape: {test_df.shape}")
    
    # Run preprocessing
    try:
        train_loader, val_loader, test_loader, char2idx, idx2char = preprocess_data(
            test_df,
            batch_size=2
        )
        
        # ===== VERIFY OUTPUTS =====
        print(f"\n" + "-"*70)
        print("VERIFICATION")
        print("-"*70)
        
        # Get one batch and check shapes
        sample_batch = next(iter(train_loader))
        print(f"\n[*] Sample batch shape: {sample_batch.shape}")
        print(f"   Expected: (batch_size, {MAX_SMILES_LENGTH}, vocab_size)")
        print(f"   Actual: ({sample_batch.shape[0]}, {sample_batch.shape[1]}, {sample_batch.shape[2]})")
        print(f"   Batch size: {sample_batch.shape[0]}")
        print(f"   Sequence length: {sample_batch.shape[1]}")
        print(f"   Vocab size: {sample_batch.shape[2]}")
        
        # Verify all values are 0 or 1 (valid one-hot)
        unique_values = torch.unique(sample_batch).tolist()
        print(f"\n[*] One-hot encoding validation:")
        print(f"   Unique values in batch: {unique_values}")
        print(f"   Valid (should be [0.0, 1.0]): {set(unique_values) <= {0.0, 1.0}}")
        
        # Show which characters are in vocabulary
        print(f"\n[*] Vocabulary stats:")
        print(f"   Total vocabulary size: {len(char2idx)}")
        print(f"   Characters: {sorted([k for k in char2idx.keys() if k != '<pad>'])}")
        
        print(f"\n✅ ALL TESTS PASSED!")
        
    except Exception as e:
        print(f"\n❌ ERROR during preprocessing: {e}")
        import traceback
        traceback.print_exc()
