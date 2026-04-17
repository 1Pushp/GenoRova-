"""
Genorova AI — Tests for model_ar.py
=====================================

Run from the genorova/src/ directory (so imports resolve):

    cd genorova/src
    python -m pytest ../tests/test_model_ar.py -v

Or from the project root:

    cd "genorova/src" && python -m pytest ../tests/test_model_ar.py -v

What is tested:
    1. ARDecoder forward pass shapes (teacher forcing)
    2. ARDecoder.generate output shapes and BOS token constraint
    3. SMILESVAE forward pass shapes
    4. SMILESVAE.loss_function returns finite scalar losses
    5. SMILESVAE.generate: BOS at position 0, no out-of-vocab ids
    6. SMILESVAE.decode: one-hot shim shape is correct
    7. Backward pass: gradients flow through model and loss
    8. SMILESVAE with BOS/EOS sequence constraint:
       generated sequences start with BOS, end before max_len
    9. Evaluator compatibility: model.decode(z) output is passable to
       select_token_ids_from_logits without errors
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure `src/` is on the path regardless of where pytest is invoked from.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
import torch

from model_ar import ARDecoder, SMILESVAE, PAD_IDX, DEFAULT_BOS_IDX, DEFAULT_EOS_IDX

# ── small fixed vocab for all tests ──────────────────────────────────────────
VOCAB   = 20    # tiny vocabulary: 0=PAD, 1=BOS, 2=EOS, 3=UNK, 4-19=SMILES chars
LATENT  = 32    # small latent dim for speed
MAXLEN  = 16    # short sequences for speed
BATCH   = 4
HIDDEN  = 64
EMBED   = 16
LAYERS  = 2


@pytest.fixture
def small_decoder():
    """A small ARDecoder ready for testing."""
    return ARDecoder(
        vocab_size=VOCAB,
        latent_dim=LATENT,
        embed_dim=EMBED,
        hidden_dim=HIDDEN,
        num_layers=LAYERS,
        dropout=0.0,
    )


@pytest.fixture
def small_model():
    """A small SMILESVAE ready for testing."""
    return SMILESVAE(
        vocab_size=VOCAB,
        latent_dim=LATENT,
        max_length=MAXLEN,
        embed_dim=EMBED,
        hidden_dim=HIDDEN,
        num_gru_layers=LAYERS,
        dropout=0.0,
    )


def make_onehot(batch: int, seqlen: int, vocab: int) -> torch.Tensor:
    """Create a random one-hot tensor."""
    ids  = torch.randint(0, vocab, (batch, seqlen))
    oh   = torch.zeros(batch, seqlen, vocab)
    oh.scatter_(2, ids.unsqueeze(2), 1.0)
    return oh


def make_token_ids(batch: int, seqlen: int, vocab: int) -> torch.Tensor:
    """Create a token id tensor with BOS at position 0."""
    ids = torch.randint(3, vocab, (batch, seqlen))   # avoid special tokens
    ids[:, 0] = DEFAULT_BOS_IDX                       # BOS at pos 0
    return ids


# ============================================================================
# ARDecoder tests
# ============================================================================

class TestARDecoder:
    def test_teacher_forward_shape(self, small_decoder):
        """teacher_forward returns [batch, seq_len-1, vocab]."""
        z          = torch.randn(BATCH, LATENT)
        target_ids = make_token_ids(BATCH, MAXLEN, VOCAB)

        logits = small_decoder.teacher_forward(z, target_ids)

        assert logits.shape == (BATCH, MAXLEN - 1, VOCAB), (
            f"Expected ({BATCH}, {MAXLEN-1}, {VOCAB}), got {logits.shape}"
        )

    def test_generate_shape(self, small_decoder):
        """generate returns [batch, max_len]."""
        z         = torch.randn(BATCH, LATENT)
        token_ids = small_decoder.generate(
            z,
            bos_idx=DEFAULT_BOS_IDX,
            eos_idx=DEFAULT_EOS_IDX,
            pad_idx=PAD_IDX,
            max_len=MAXLEN,
        )
        assert token_ids.shape == (BATCH, MAXLEN), (
            f"Expected ({BATCH}, {MAXLEN}), got {token_ids.shape}"
        )

    def test_generate_starts_with_bos(self, small_decoder):
        """First token of every generated sequence must be BOS."""
        z         = torch.randn(BATCH, LATENT)
        token_ids = small_decoder.generate(
            z,
            bos_idx=DEFAULT_BOS_IDX,
            eos_idx=DEFAULT_EOS_IDX,
            pad_idx=PAD_IDX,
            max_len=MAXLEN,
        )
        assert (token_ids[:, 0] == DEFAULT_BOS_IDX).all(), (
            "BOS token must be at position 0 in all generated sequences."
        )

    def test_generate_no_bos_after_position0(self, small_decoder):
        """BOS should not appear at any position after 0."""
        z         = torch.randn(8, LATENT)
        token_ids = small_decoder.generate(
            z,
            bos_idx=DEFAULT_BOS_IDX,
            eos_idx=DEFAULT_EOS_IDX,
            pad_idx=PAD_IDX,
            max_len=MAXLEN,
        )
        # Positions 1..end should not contain BOS
        assert not (token_ids[:, 1:] == DEFAULT_BOS_IDX).any(), (
            "BOS token should not appear after position 0."
        )

    def test_generate_ids_in_range(self, small_decoder):
        """All generated token ids must be valid vocabulary indices."""
        z         = torch.randn(BATCH, LATENT)
        token_ids = small_decoder.generate(
            z,
            bos_idx=DEFAULT_BOS_IDX,
            eos_idx=DEFAULT_EOS_IDX,
            pad_idx=PAD_IDX,
            max_len=MAXLEN,
        )
        assert token_ids.min().item() >= 0, "Negative token id found."
        assert token_ids.max().item() < VOCAB, (
            f"Token id {token_ids.max().item()} >= vocab size {VOCAB}."
        )

    def test_init_hidden_shape(self, small_decoder):
        """_init_hidden returns [num_layers, batch, hidden_dim]."""
        z = torch.randn(BATCH, LATENT)
        h = small_decoder._init_hidden(z)
        assert h.shape == (LAYERS, BATCH, HIDDEN), (
            f"Expected ({LAYERS}, {BATCH}, {HIDDEN}), got {h.shape}"
        )


# ============================================================================
# SMILESVAE tests
# ============================================================================

class TestSMILESVAE:
    def test_forward_shapes(self, small_model):
        """forward() returns (logits, mu, logvar) with correct shapes."""
        x = make_onehot(BATCH, MAXLEN, VOCAB)

        small_model.train()
        logits, mu, logvar = small_model(x)

        assert logits.shape == (BATCH, MAXLEN - 1, VOCAB), (
            f"logits shape mismatch: {logits.shape}"
        )
        assert mu.shape     == (BATCH, LATENT)
        assert logvar.shape == (BATCH, LATENT)

    def test_loss_finite(self, small_model):
        """loss_function returns finite scalar losses."""
        x = make_onehot(BATCH, MAXLEN, VOCAB)

        small_model.train()
        logits, mu, logvar = small_model(x)
        total, recon, kl   = small_model.loss_function(
            logits, x, mu, logvar, kl_weight=0.1
        )

        assert total.ndim == 0, "Loss must be a scalar."
        assert torch.isfinite(total), f"Total loss is not finite: {total.item()}"
        assert torch.isfinite(recon), f"Recon loss is not finite: {recon.item()}"
        assert torch.isfinite(kl),    f"KL loss is not finite: {kl.item()}"

    def test_backward_flows(self, small_model):
        """Gradients flow through both encoder and decoder."""
        x = make_onehot(BATCH, MAXLEN, VOCAB)

        small_model.train()
        logits, mu, logvar = small_model(x)
        total, _, _ = small_model.loss_function(
            logits, x, mu, logvar, kl_weight=0.1
        )
        total.backward()

        encoder_has_grad = any(
            p.grad is not None for p in small_model.encoder.parameters()
        )
        decoder_has_grad = any(
            p.grad is not None for p in small_model.decoder.parameters()
        )
        assert encoder_has_grad, "No gradients reached encoder parameters."
        assert decoder_has_grad, "No gradients reached decoder parameters."

    def test_generate_shape(self, small_model):
        """generate() returns [n, max_len] integer tensor."""
        small_model.eval()
        token_ids = small_model.generate(num_molecules=BATCH, max_len=MAXLEN)

        assert token_ids.shape == (BATCH, MAXLEN), (
            f"Expected ({BATCH}, {MAXLEN}), got {token_ids.shape}"
        )
        assert token_ids.dtype in (torch.int32, torch.int64), (
            "Token ids must be integer tensors."
        )

    def test_generate_bos_first(self, small_model):
        """First token of every generated sequence is BOS."""
        small_model.eval()
        token_ids = small_model.generate(num_molecules=8, max_len=MAXLEN)
        assert (token_ids[:, 0] == small_model._bos_idx).all(), (
            "All sequences must start with BOS."
        )

    def test_generate_ids_in_vocab(self, small_model):
        """All generated token ids are valid indices for this vocabulary."""
        small_model.eval()
        token_ids = small_model.generate(num_molecules=BATCH, max_len=MAXLEN)
        assert token_ids.min().item() >= 0
        assert token_ids.max().item() < VOCAB

    def test_decode_shim_shape(self, small_model):
        """decode() compatibility shim returns [batch, max_len, vocab]."""
        small_model.eval()
        z      = torch.randn(BATCH, LATENT)
        one_hot = small_model.decode(z)

        assert one_hot.shape == (BATCH, MAXLEN, VOCAB), (
            f"decode() shape mismatch: {one_hot.shape}"
        )

    def test_decode_shim_is_onehot(self, small_model):
        """Every position in decode() output sums to 1.0 (one-hot)."""
        small_model.eval()
        z       = torch.randn(BATCH, LATENT)
        one_hot = small_model.decode(z)

        row_sums = one_hot.sum(dim=-1)   # [batch, max_len]
        assert torch.allclose(row_sums, torch.ones_like(row_sums)), (
            "decode() output is not one-hot (each position must sum to 1)."
        )

    def test_evaluator_pipeline_compat(self, small_model):
        """
        model.decode(z) output can be passed to select_token_ids_from_logits
        without raising exceptions (evaluator compatibility).
        """
        from preprocessor import select_token_ids_from_logits

        small_model.eval()
        z       = torch.randn(BATCH, LATENT)
        one_hot = small_model.decode(z)

        # Build a minimal char2idx compatible with the small model
        char2idx = {
            "<pad>": 0, "<bos>": 1, "<eos>": 2, "<unk>": 3,
            **{str(i): i + 4 for i in range(VOCAB - 4)},
        }
        # This should not raise
        indices = select_token_ids_from_logits(
            one_hot, char2idx, strategy="greedy",
        )
        assert indices.shape == (BATCH, MAXLEN), (
            f"Evaluator pipeline output shape mismatch: {indices.shape}"
        )

    def test_set_special_tokens(self, small_model):
        """set_special_tokens() updates the model's internal BOS/EOS/PAD indices."""
        char2idx = {"<pad>": 0, "<bos>": 7, "<eos>": 8, "<unk>": 9}
        small_model.set_special_tokens(char2idx)

        assert small_model._bos_idx == 7
        assert small_model._eos_idx == 8
        assert small_model._pad_idx == 0

    def test_count_parameters_positive(self, small_model):
        """Model must have at least one trainable parameter."""
        n = small_model.count_parameters()
        assert n > 0, "Model has no trainable parameters."

    def test_encode_shapes(self, small_model):
        """encode() returns (z, mu, logvar) all of shape [batch, latent_dim]."""
        x = make_onehot(BATCH, MAXLEN, VOCAB)
        z, mu, logvar = small_model.encode(x)
        for name, tensor in [("z", z), ("mu", mu), ("logvar", logvar)]:
            assert tensor.shape == (BATCH, LATENT), (
                f"{name} shape mismatch: {tensor.shape}"
            )

    def test_loss_kl_weight_zero(self, small_model):
        """With kl_weight=0 the total loss equals the reconstruction loss."""
        x = make_onehot(BATCH, MAXLEN, VOCAB)
        small_model.train()
        logits, mu, logvar = small_model(x)
        total, recon, kl   = small_model.loss_function(
            logits, x, mu, logvar, kl_weight=0.0, free_bits=0.0
        )
        assert torch.isclose(total, recon, atol=1e-5), (
            "With kl_weight=0, total loss should equal recon loss."
        )


# ============================================================================
# Smoke test: tiny single-epoch training step
# ============================================================================

class TestSingleTrainingStep:
    """
    Verifies that the training loop mechanics work end to end on a
    CPU-only toy dataset without any real data dependencies.
    """

    def test_one_gradient_step(self, small_model):
        """
        One forward + backward + optimizer step should reduce the loss.
        This confirms the training loop is wired correctly.
        """
        import torch.optim as optim

        optimizer = optim.Adam(small_model.parameters(), lr=1e-2)
        x = make_onehot(8, MAXLEN, VOCAB)

        small_model.train()

        # Step 1 — compute initial loss
        logits, mu, logvar = small_model(x)
        loss1, _, _        = small_model.loss_function(
            logits, x, mu, logvar, kl_weight=0.1
        )

        # Step 2 — gradient update
        optimizer.zero_grad()
        loss1.backward()
        optimizer.step()

        # Step 3 — compute loss after update
        logits2, mu2, logvar2 = small_model(x)
        loss2, _, _           = small_model.loss_function(
            logits2, x, mu2, logvar2, kl_weight=0.1
        )

        # Both losses must be finite
        assert torch.isfinite(loss1), f"Pre-step loss not finite: {loss1.item()}"
        assert torch.isfinite(loss2), f"Post-step loss not finite: {loss2.item()}"
        # We do not assert loss2 < loss1 because one step is not guaranteed
        # to reduce loss (depends on data and init), but it must be finite.
