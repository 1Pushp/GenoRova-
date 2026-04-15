from __future__ import annotations

import numpy as np

from genorova.src.preprocessor import (
    PAD_TOKEN,
    build_vocab,
    load_vocab,
    preprocess_batch,
    save_vocab,
)


def test_vocab_build_and_save_load_roundtrip(project_temp_dir):
    smiles_list = ["CCO", "N#CC(=O)O", "c1ccccc1"]

    char2idx, idx2char = build_vocab(smiles_list)

    assert PAD_TOKEN in char2idx
    assert char2idx[PAD_TOKEN] == 0
    assert idx2char[0] == PAD_TOKEN

    vocab_path = project_temp_dir / "vocab.json"
    save_vocab(char2idx, str(vocab_path))
    loaded_char2idx, loaded_idx2char = load_vocab(str(vocab_path))

    assert loaded_char2idx == char2idx
    assert loaded_idx2char == idx2char


def test_preprocess_batch_produces_one_hot_sequences():
    smiles_list = ["CCO", "N#CC(=O)O"]
    char2idx, _ = build_vocab(smiles_list)

    encoded = preprocess_batch(smiles_list, char2idx, max_length=8)

    assert encoded.shape == (2, 8, len(char2idx))
    assert encoded.dtype == np.float32
    assert np.allclose(encoded.sum(axis=2), 1.0)
