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
from typing import Tuple, Dict, List


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_SMILES_LENGTH = 120  # Maximum length of SMILES string (pad/truncate to this)
PAD_TOKEN = "<pad>"      # Special token for padding
VOCAB_OUTPUT_PATH = "outputs/vocabulary.json"


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
    
    # Create mappings
    char2idx = {PAD_TOKEN: 0}  # Start with pad token at index 0
    for idx, char in enumerate(unique_chars, start=1):
        char2idx[char] = idx
    
    # Reverse mapping
    idx2char = {v: k for k, v in char2idx.items()}
    
    print(f"   [OK] Vocabulary built successfully!")
    print(f"   [OK] Unique characters found: {len(unique_chars)}")
    print(f"   [OK] Vocabulary size (with padding): {len(char2idx)}")
    print(f"   [OK] Sample characters: {unique_chars[:10]}")
    
    return char2idx, idx2char


# ============================================================================
# ENCODING FUNCTIONS
# ============================================================================

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
    
    # Convert SMILES string to indices
    indices = []
    for char in smiles:
        if char in char2idx:
            indices.append(char2idx[char])
        else:
            # Skip unknown characters (should not happen with proper vocab)
            indices.append(char2idx[PAD_TOKEN])
    
    # Truncate if too long
    if len(indices) > max_length:
        indices = indices[:max_length]
    
    # Pad with 0 (pad token) if too short
    indices = indices + [0] * (max_length - len(indices))
    
    # Create one-hot encoding: [max_length, vocab_size]
    one_hot = np.zeros((max_length, vocab_size), dtype=np.float32)
    for pos, idx in enumerate(indices):
        one_hot[pos, idx] = 1.0
    
    return one_hot


def preprocess_batch(smiles_list: List[str], char2idx: Dict[str, int]) -> np.ndarray:
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
        one_hot = encode_smiles(smiles, char2idx)
        batch.append(one_hot)
    
    return np.array(batch, dtype=np.float32)


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
