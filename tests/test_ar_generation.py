from __future__ import annotations

import torch

from genorova.src.model_ar import ARDecoder


def test_ar_decoder_blocks_early_eos_until_min_generation_length():
    vocab_size = 6
    pad_idx = 0
    bos_idx = 1
    eos_idx = 2
    fallback_token = 4

    decoder = ARDecoder(
        vocab_size=vocab_size,
        latent_dim=4,
        embed_dim=4,
        hidden_dim=4,
        num_layers=1,
        dropout=0.0,
    )

    with torch.no_grad():
        for parameter in decoder.parameters():
            parameter.zero_()
        decoder.output_proj.bias[eos_idx] = 10.0
        decoder.output_proj.bias[fallback_token] = 9.0

    token_ids = decoder.generate(
        z=torch.zeros(2, 4),
        bos_idx=bos_idx,
        eos_idx=eos_idx,
        pad_idx=pad_idx,
        max_len=16,
        top_k=1,
        min_generation_length=5,
    )

    assert token_ids.shape == (2, 16)
    assert torch.all(token_ids[:, 0] == bos_idx)
    assert torch.all(token_ids[:, 1:6] == fallback_token)
    assert torch.all(token_ids[:, 6] == eos_idx)
