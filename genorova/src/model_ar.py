"""
Genorova AI -- Autoregressive SMILES VAE  (model_ar.py)
=======================================================

WHY THIS FILE EXISTS
--------------------
The original parallel (non-autoregressive) decoder in model.py maps a single
latent vector z directly to ALL 120 output positions in one MLP pass.  Each
position is predicted independently, so the decoder never learns sequential
constraints like:

    "if I opened '(' at position 5, I must close it later"
    "ring-closure digit '1' must appear exactly twice"
    "a bond token '=' must precede an atom, not appear at the end"

Post-hoc structural guards in select_token_ids_from_logits (preprocessor.py)
try to paper over this, but they cannot teach the model what it was never
trained to know.  The result: ~9.8% SMILES validity.

THIS FILE'S APPROACH
--------------------
Replace the MLP decoder with a 2-layer GRU that generates tokens one at a time,
conditioned on the latent vector z via the GRU initial hidden state.

  Training (teacher forcing):
    at step t: input = embedding of ground-truth token[t-1]
               target = ground-truth token[t]
    Loss = CrossEntropy on non-padding positions + KL divergence

  Inference (autoregressive):
    at step t: input = embedding of model's own prediction at t-1
               stop when EOS token is predicted or max_len is reached

ARCHITECTURE SUMMARY
--------------------
  Encoder : 3-layer MLP  (re-used from model.py, unchanged)
    Input : [batch, max_length, vocab_size]  (one-hot SMILES)
    Output: mu, logvar  each [batch, latent_dim=256]

  ARDecoder : 2-layer GRU
    z → latent_to_hidden → initial hidden [2, batch, hidden_dim=512]
    embed[token] → GRU step → linear → logits over vocab
    Parameters: ~1.5 M (vs ~9 M in the original flat decoder)

  SMILESVAE : Encoder + ARDecoder
    forward(x) → (logits, mu, logvar)
    generate(n, bos, eos, pad, ...) → token_ids [n, max_len]
    decode(z) → one-hot [batch, max_len, vocab]   (evaluator compat shim)

BACKWARD COMPATIBILITY
----------------------
- Encoder class and all preprocessor.py utilities are unchanged.
- evaluate_generation.py can load SMILESVAE checkpoints via the
  model_type="SMILESVAE_AR" key in the checkpoint dict; a minimal patch
  to _load_model() in that file enables this.
- Old VAE checkpoints continue to load and run unchanged.

AUTHOR  : Claude Code  (Genorova AI Sprint 2)
DATE    : April 2026
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple

# Re-use the existing encoder and its constants so the encoder stays frozen.
from model import Encoder, LATENT_DIM, MAX_SMILES_LENGTH, DROPOUT_RATE, FREE_BITS

# PAD index must match preprocessor.py: SPECIAL_TOKENS = [PAD, BOS, EOS, UNK]
PAD_IDX = 0
DEFAULT_BOS_IDX = 1   # index of <bos> in default vocabulary
DEFAULT_EOS_IDX = 2   # index of <eos> in default vocabulary
DEFAULT_MIN_GENERATION_LENGTH = 20

# AR-decoder hyperparameters
EMBED_DIM   = 128   # token embedding dimension
HIDDEN_DIM  = 512   # GRU hidden state dimension
NUM_GRU_LAYERS = 2  # stacked GRU layers


# ============================================================================
# AUTOREGRESSIVE GRU DECODER
# ============================================================================

class ARDecoder(nn.Module):
    """
    Autoregressive GRU decoder for SMILES token generation.

    The decoder is conditioned on the latent vector z via the GRU initial
    hidden state.  At each step it reads one token embedding and emits
    logits over the vocabulary.

    Training (called from SMILESVAE.forward):
        teacher_forward(z, target_ids) → logits [batch, seq_len-1, vocab]

    Inference (called from SMILESVAE.generate):
        generate(z, bos_idx, eos_idx, pad_idx, ...) → token_ids [batch, max_len]
    """

    def __init__(
        self,
        vocab_size: int,
        latent_dim: int = LATENT_DIM,
        embed_dim: int   = EMBED_DIM,
        hidden_dim: int  = HIDDEN_DIM,
        num_layers: int  = NUM_GRU_LAYERS,
        dropout: float   = DROPOUT_RATE,
    ):
        """
        Build the autoregressive GRU decoder.

        Args:
            vocab_size  : number of tokens in the SMILES vocabulary
            latent_dim  : dimensionality of z coming from the encoder
            embed_dim   : size of each token embedding vector
            hidden_dim  : GRU hidden state size
            num_layers  : number of stacked GRU layers
            dropout     : dropout probability applied to token embeddings
        """
        super().__init__()

        self.vocab_size = vocab_size
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.embed_dim  = embed_dim

        # Each token index → dense vector of size embed_dim
        # padding_idx=PAD_IDX ensures pad token embeddings stay zero and
        # do not contribute to gradients.
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=PAD_IDX)

        # Project latent vector → initial GRU hidden state.
        # Output is num_layers * hidden_dim so we can reshape to
        # [num_layers, batch, hidden_dim] directly.
        self.latent_to_hidden = nn.Linear(latent_dim, num_layers * hidden_dim)

        # Stacked GRU: reads one token embedding per step.
        # batch_first=True means input/output are [batch, seq_len, features].
        self.gru = nn.GRU(
            input_size=embed_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        # Map GRU output → vocabulary logits
        self.output_proj = nn.Linear(hidden_dim, vocab_size)

        # Dropout applied to token embeddings during training
        self.dropout = nn.Dropout(dropout)

        print(f"[*] ARDecoder built: embed={embed_dim} hidden={hidden_dim} "
              f"layers={num_layers} vocab={vocab_size}")

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _init_hidden(self, z: torch.Tensor) -> torch.Tensor:
        """
        Convert latent vector z into the initial GRU hidden state.

        Args:
            z : [batch, latent_dim]

        Returns:
            h : [num_layers, batch, hidden_dim]
        """
        batch_size = z.size(0)
        # Linear projection then tanh squash
        h = torch.tanh(self.latent_to_hidden(z))        # [batch, num_layers*hidden]
        h = h.view(batch_size, self.num_layers, self.hidden_dim)
        h = h.permute(1, 0, 2).contiguous()             # [num_layers, batch, hidden]
        return h

    # ------------------------------------------------------------------
    # Teacher-forced forward pass (training)
    # ------------------------------------------------------------------

    def teacher_forward(
        self,
        z: torch.Tensor,
        target_ids: torch.Tensor,
    ) -> torch.Tensor:
        """
        Teacher-forced decoding for training.

        At step t the decoder input is the ground-truth token at t-1,
        and the target is the token at t.  This is the classic shifted-
        sequence setup:

            input  : target_ids[:, :-1]   (BOS … token[n-1])
            target : target_ids[:, 1:]    (token[1] … EOS)

        Args:
            z          : [batch, latent_dim]
            target_ids : [batch, seq_len]  full padded token id sequence

        Returns:
            logits : [batch, seq_len-1, vocab_size]
                     logits[b, t] predicts target_ids[b, t+1]
        """
        # Build initial hidden state from latent vector
        h = self._init_hidden(z)                        # [L, B, H]

        # Decoder input = all tokens except the last
        decoder_input = target_ids[:, :-1]              # [B, S-1]

        # Embed and apply dropout
        embedded = self.dropout(self.embed(decoder_input))  # [B, S-1, E]

        # Run GRU over the full input sequence in one call
        output, _ = self.gru(embedded, h)               # [B, S-1, H]

        # Project to vocabulary logits
        logits = self.output_proj(output)               # [B, S-1, V]
        return logits

    # ------------------------------------------------------------------
    # Autoregressive generation (inference)
    # ------------------------------------------------------------------

    def generate(
        self,
        z: torch.Tensor,
        bos_idx: int,
        eos_idx: int,
        pad_idx: int,
        max_len: int   = MAX_SMILES_LENGTH,
        temperature: float = 1.0,
        top_k: int     = 0,
        min_generation_length: int = DEFAULT_MIN_GENERATION_LENGTH,
    ) -> torch.Tensor:
        """
        Token-by-token autoregressive generation for inference.

        Starts with the BOS token, feeds the model's own predictions back
        as inputs, and stops when EOS is produced or max_len is reached.

        Args:
            z           : [batch, latent_dim]
            bos_idx     : index of the <bos> token in the vocabulary
            eos_idx     : index of the <eos> token in the vocabulary
            pad_idx     : index of the <pad> token in the vocabulary
            max_len     : maximum number of tokens to generate
            temperature : softmax temperature (higher = more diverse)
            top_k       : if > 0, sample only from the top-k tokens
            min_generation_length : minimum number of generated non-special
                                    tokens before EOS can terminate the
                                    sequence

        Returns:
            token_ids : [batch, max_len]
              sequences padded with pad_idx after EOS is emitted
        """
        batch_size = z.size(0)
        device     = z.device
        effective_min_generation_length = max(
            0,
            min(int(min_generation_length), max(0, max_len - 2)),
        )

        # Initialize hidden state from z
        h = self._init_hidden(z)                        # [L, B, H]

        # Output buffer filled with padding
        generated = torch.full(
            (batch_size, max_len), pad_idx, dtype=torch.long, device=device
        )

        # Start every sequence with BOS
        generated[:, 0] = bos_idx
        current_token   = torch.full(
            (batch_size, 1), bos_idx, dtype=torch.long, device=device
        )

        # Track which sequences have already produced EOS
        finished = torch.zeros(batch_size, dtype=torch.bool, device=device)

        for step in range(1, max_len):
            # Embed current token
            embedded = self.embed(current_token)        # [B, 1, E]

            # One GRU step
            output, h = self.gru(embedded, h)           # [B, 1, H], [L, B, H]

            # Project to logits
            logits = self.output_proj(output.squeeze(1))  # [B, V]

            # Never generate BOS again after position 0
            logits[:, bos_idx] = -1e9
            # PAD is only meaningful after termination.
            logits[:, pad_idx] = -1e9

            # Count only real generated tokens after BOS. PAD does not count,
            # and EOS is blocked until the minimum length is reached.
            real_tokens_generated = step - 1
            if real_tokens_generated < effective_min_generation_length:
                logits[:, eos_idx] = -1e9

            # Temperature scaling
            if temperature != 1.0:
                logits = logits / max(temperature, 1e-6)

            # Top-k filtering
            if top_k > 0 and top_k < logits.size(-1):
                top_vals, top_ids = torch.topk(logits, k=top_k, dim=-1)
                mask = torch.full_like(logits, -1e9)
                mask.scatter_(1, top_ids, top_vals)
                logits = mask

            # Sample from the filtered distribution
            probs      = torch.softmax(logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1).squeeze(1)  # [B]

            # Finished sequences keep emitting pad instead of new tokens
            next_token = torch.where(
                finished,
                torch.tensor(pad_idx, dtype=torch.long, device=device),
                next_token,
            )

            generated[:, step] = next_token

            # Mark sequences that just hit EOS as done
            finished = finished | (next_token == eos_idx)

            # Prepare input for next step
            current_token = next_token.unsqueeze(1)     # [B, 1]

            if finished.all():
                break

        return generated


# ============================================================================
# SMILESVAE: ENCODER + AUTOREGRESSIVE DECODER
# ============================================================================

class SMILESVAE(nn.Module):
    """
    Variational Autoencoder for SMILES generation with an autoregressive decoder.

    The encoder is identical to model.VAE's encoder (a 3-layer MLP).
    The decoder is a 2-layer GRU that generates tokens one at a time,
    conditioned on the latent vector z.

    Training:
        model.forward(x)  →  (logits, mu, logvar)
        model.loss_function(logits, x, mu, logvar, kl_weight)  →  losses

    Inference:
        model.generate(n, bos, eos, pad, ...)  →  token_ids [n, max_len]

    Evaluator compatibility:
        model.decode(z)  →  one-hot [batch, max_len, vocab]
        (so evaluate_generation.py can call model.decode(z) as usual and
         pass the result to select_token_ids_from_logits)
    """

    # Sentinel used in checkpoint dict to identify this model type.
    MODEL_TYPE = "SMILESVAE_AR"

    def __init__(
        self,
        vocab_size: int,
        latent_dim: int   = LATENT_DIM,
        max_length: int   = MAX_SMILES_LENGTH,
        embed_dim: int    = EMBED_DIM,
        hidden_dim: int   = HIDDEN_DIM,
        num_gru_layers: int = NUM_GRU_LAYERS,
        dropout: float    = DROPOUT_RATE,
    ):
        """
        Build the SMILESVAE.

        Args:
            vocab_size     : SMILES vocabulary size
            latent_dim     : latent space dimensionality
            max_length     : maximum SMILES token length
            embed_dim      : token embedding size for the AR decoder
            hidden_dim     : GRU hidden size
            num_gru_layers : number of stacked GRU layers
            dropout        : dropout rate
        """
        super().__init__()

        self.latent_dim  = latent_dim
        self.vocab_size  = vocab_size
        self.max_length  = max_length

        # Special token index defaults (preprocessor.py SPECIAL_TOKENS order:
        # [PAD, BOS, EOS, UNK] → indices 0, 1, 2, 3)
        # These can be overridden after loading via set_special_tokens().
        self._bos_idx = DEFAULT_BOS_IDX
        self._eos_idx = DEFAULT_EOS_IDX
        self._pad_idx = PAD_IDX

        print(f"\n{'='*60}")
        print(f"SMILESVAE (autoregressive decoder)")
        print(f"{'='*60}")
        print(f"  vocab_size  : {vocab_size}")
        print(f"  latent_dim  : {latent_dim}")
        print(f"  max_length  : {max_length}")
        print(f"  embed_dim   : {embed_dim}")
        print(f"  gru_hidden  : {hidden_dim}  x{num_gru_layers} layers")

        # Encoder: reuse the existing 3-layer MLP encoder unchanged
        self.encoder = Encoder(vocab_size, latent_dim, max_length)

        # Decoder: new autoregressive GRU
        self.decoder = ARDecoder(
            vocab_size   = vocab_size,
            latent_dim   = latent_dim,
            embed_dim    = embed_dim,
            hidden_dim   = hidden_dim,
            num_layers   = num_gru_layers,
            dropout      = dropout,
        )

        n = self.count_parameters()
        print(f"  total params: {n:,}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def set_special_tokens(self, char2idx: dict) -> None:
        """
        Store special token indices from a vocabulary dict.

        Called after loading a checkpoint so that decode() uses the
        correct BOS/EOS/PAD ids for this vocabulary.

        Args:
            char2idx : mapping from token string → integer index
        """
        self._bos_idx = char2idx.get("<bos>", DEFAULT_BOS_IDX)
        self._eos_idx = char2idx.get("<eos>", DEFAULT_EOS_IDX)
        self._pad_idx = char2idx.get("<pad>", PAD_IDX)

    def count_parameters(self) -> int:
        """Return total trainable parameter count."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    # ------------------------------------------------------------------
    # VAE core
    # ------------------------------------------------------------------

    def reparameterize(
        self, mu: torch.Tensor, logvar: torch.Tensor
    ) -> torch.Tensor:
        """
        VAE reparameterization trick.

        z = mu + epsilon * std   where epsilon ~ N(0, 1)

        Differentiable with respect to mu and logvar, allowing gradients
        to flow through the sampling step.
        """
        std     = torch.exp(0.5 * logvar)
        epsilon = torch.randn_like(std)
        return mu + epsilon * std

    def encode(
        self, x: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Encode one-hot SMILES to (z, mu, logvar).

        Args:
            x : [batch, max_length, vocab_size]  one-hot input

        Returns:
            (z, mu, logvar) each of shape [batch, latent_dim]
        """
        mu, logvar = self.encoder(x)
        z = self.reparameterize(mu, logvar)
        return z, mu, logvar

    # ------------------------------------------------------------------
    # Training forward pass
    # ------------------------------------------------------------------

    def forward(
        self, x: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Full VAE forward pass with teacher forcing.

        The encoder sees the full one-hot input x.
        The decoder sees the token-id sequence derived from x (teacher forcing).

        Args:
            x : [batch, max_length, vocab_size]  one-hot encoded SMILES

        Returns:
            logits  : [batch, max_length-1, vocab_size]  decoder predictions
                       logits[:, t] is the prediction for position t+1
            mu      : [batch, latent_dim]
            logvar  : [batch, latent_dim]
        """
        # Derive token ids from the one-hot input (no extra data needed)
        target_ids = torch.argmax(x, dim=-1)       # [batch, max_length]

        # Encode to latent space
        z, mu, logvar = self.encode(x)

        # Decode with teacher forcing
        logits = self.decoder.teacher_forward(z, target_ids)  # [B, L-1, V]

        return logits, mu, logvar

    # ------------------------------------------------------------------
    # Loss function
    # ------------------------------------------------------------------

    def loss_function(
        self,
        logits: torch.Tensor,
        x: torch.Tensor,
        mu: torch.Tensor,
        logvar: torch.Tensor,
        kl_weight: float = 0.5,
        free_bits: float = FREE_BITS,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        VAE loss = CrossEntropy reconstruction + KL divergence.

        Reconstruction:
            logits[:, t] predicts target_ids[:, t+1], so the target for
            the reconstruction loss is target_ids[:, 1:] (everything after BOS).
            Padding positions (pad_idx) are masked out.

        KL divergence with free-bits regularization:
            Prevents posterior collapse by clamping per-dimension KL to a
            minimum value (free_bits).  Dimensions below that threshold
            receive zero gradient, so the encoder cannot be rewarded for
            collapsing them.

        Args:
            logits    : [batch, seq_len-1, vocab_size]  from forward()
            x         : [batch, seq_len, vocab_size]    original one-hot input
            mu        : [batch, latent_dim]
            logvar    : [batch, latent_dim]
            kl_weight : weight applied to KL term (annealed during training)
            free_bits : minimum KL per latent dimension (0 = disabled)

        Returns:
            (total_loss, recon_loss, kl_loss)
        """
        # Recover token ids from one-hot (same argmax used in forward())
        target_ids     = torch.argmax(x, dim=-1)   # [batch, seq_len]
        shifted_target = target_ids[:, 1:].contiguous()  # [batch, seq_len-1]

        # Flatten to [batch*(seq_len-1), vocab_size] for F.cross_entropy
        B, S, V    = logits.shape
        logits_2d  = logits.view(B * S, V)
        targets_1d = shifted_target.view(B * S)

        # Mask padding so the model is not penalised for pad tokens
        non_pad = targets_1d != self._pad_idx
        if non_pad.any():
            recon_loss = F.cross_entropy(
                logits_2d[non_pad], targets_1d[non_pad], reduction="mean"
            )
        else:
            recon_loss = F.cross_entropy(logits_2d, targets_1d, reduction="mean")

        # KL divergence: -0.5 * sum(1 + logvar - mu^2 - exp(logvar))
        kl_per_dim = -0.5 * (1.0 + logvar - mu.pow(2) - logvar.exp())

        # Free bits: zero gradient when KL is already below the threshold
        if free_bits > 0.0:
            kl_per_dim = torch.clamp(kl_per_dim, min=free_bits)

        kl_loss    = kl_per_dim.mean()
        total_loss = recon_loss + kl_weight * kl_loss

        return total_loss, recon_loss, kl_loss

    # ------------------------------------------------------------------
    # Inference generation
    # ------------------------------------------------------------------

    def generate(
        self,
        num_molecules: int,
        bos_idx: int   = None,
        eos_idx: int   = None,
        pad_idx: int   = None,
        max_len: int   = None,
        temperature: float = 1.0,
        top_k: int     = 0,
        min_generation_length: int = DEFAULT_MIN_GENERATION_LENGTH,
        device: torch.device = None,
    ) -> torch.Tensor:
        """
        Generate novel molecules by sampling z ~ N(0, I) and decoding.

        Args:
            num_molecules : number of molecules to generate
            bos_idx       : BOS token index (defaults to self._bos_idx)
            eos_idx       : EOS token index (defaults to self._eos_idx)
            pad_idx       : PAD token index (defaults to self._pad_idx)
            max_len       : max tokens per sequence (defaults to self.max_length)
            temperature   : sampling temperature
            top_k         : top-k filtering (0 = disabled)
            min_generation_length : minimum number of generated tokens before
                                    EOS is allowed
            device        : target device

        Returns:
            token_ids : [num_molecules, max_len]
        """
        if device is None:
            device = next(self.parameters()).device
        if max_len  is None: max_len  = self.max_length
        if bos_idx  is None: bos_idx  = self._bos_idx
        if eos_idx  is None: eos_idx  = self._eos_idx
        if pad_idx  is None: pad_idx  = self._pad_idx

        z = torch.randn(num_molecules, self.latent_dim, device=device)
        return self.generate_from_latent(
            z,
            bos_idx=bos_idx,
            eos_idx=eos_idx,
            pad_idx=pad_idx,
            max_len=max_len,
            temperature=temperature,
            top_k=top_k,
            min_generation_length=min_generation_length,
        )

    def generate_from_latent(
        self,
        z: torch.Tensor,
        bos_idx: int = None,
        eos_idx: int = None,
        pad_idx: int = None,
        max_len: int = None,
        temperature: float = 1.0,
        top_k: int = 0,
        min_generation_length: int = DEFAULT_MIN_GENERATION_LENGTH,
    ) -> torch.Tensor:
        """
        Decode a provided latent batch autoregressively.

        This gives the evaluator a direct AR generation path so it does not
        have to resample token ids from the one-hot compatibility shim.
        """
        if max_len  is None: max_len  = self.max_length
        if bos_idx  is None: bos_idx  = self._bos_idx
        if eos_idx  is None: eos_idx  = self._eos_idx
        if pad_idx  is None: pad_idx  = self._pad_idx

        with torch.no_grad():
            token_ids = self.decoder.generate(
                z,
                bos_idx=bos_idx,
                eos_idx=eos_idx,
                pad_idx=pad_idx,
                max_len=max_len,
                temperature=temperature,
                top_k=top_k,
                min_generation_length=min_generation_length,
            )
        return token_ids

    # ------------------------------------------------------------------
    # Evaluator compatibility shim
    # ------------------------------------------------------------------

    def decode(self, z: torch.Tensor, **kwargs) -> torch.Tensor:
        """
        Compatibility shim so evaluate_generation.py can call model.decode(z)
        without any changes.

        Runs autoregressive generation and returns a one-hot tensor with the
        same shape as the old parallel decoder's output.  When the evaluator
        calls select_token_ids_from_logits on this tensor, argmax simply
        recovers the generated token ids.

        Args:
            z      : [batch, latent_dim]
            kwargs : temperature, top_k  (forwarded to decoder.generate)

        Returns:
            one_hot : [batch, max_length, vocab_size]
        """
        temperature = float(kwargs.get("temperature", 1.0))
        top_k       = int(kwargs.get("top_k", 0))
        min_generation_length = int(
            kwargs.get("min_generation_length", DEFAULT_MIN_GENERATION_LENGTH)
        )

        token_ids = self.generate_from_latent(
            z,
            bos_idx=self._bos_idx,
            eos_idx=self._eos_idx,
            pad_idx=self._pad_idx,
            max_len=self.max_length,
            temperature=temperature,
            top_k=top_k,
            min_generation_length=min_generation_length,
        )  # [batch, max_length]

        # Convert to one-hot so the evaluator pipeline is unchanged
        one_hot = torch.zeros(
            token_ids.size(0), token_ids.size(1), self.vocab_size,
            device=z.device,
        )
        one_hot.scatter_(2, token_ids.unsqueeze(2), 1.0)
        return one_hot


# ============================================================================
# QUICK SELF-TEST
# ============================================================================

if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# SMILESVAE (AR) — quick self-test")
    print("#" * 60)

    VOCAB = 42
    B, L  = 4, 32
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = SMILESVAE(vocab_size=VOCAB, max_length=L).to(device)

    # --- forward pass (teacher forcing) ---
    x_oh = torch.zeros(B, L, VOCAB, device=device)
    ids  = torch.randint(0, VOCAB, (B, L))
    x_oh.scatter_(2, ids.unsqueeze(2).to(device), 1.0)

    model.train()
    logits, mu, logvar = model(x_oh)
    assert logits.shape == (B, L - 1, VOCAB), f"Bad logits shape: {logits.shape}"

    total, recon, kl = model.loss_function(logits, x_oh, mu, logvar, kl_weight=0.1)
    total.backward()
    print(f"  loss={total.item():.4f}  recon={recon.item():.4f}  kl={kl.item():.4f}")
    print(f"  logits shape : {logits.shape}")
    print(f"  params       : {model.count_parameters():,}")

    # --- generation (autoregressive) ---
    model.eval()
    with torch.no_grad():
        tok = model.generate(num_molecules=B, max_len=L, device=device)
        assert tok.shape == (B, L), f"Bad generation shape: {tok.shape}"
        assert tok[:, 0].eq(model._bos_idx).all(), "First token must be BOS"
        print(f"  generated ids : {tok.shape}  first_tokens={tok[:, 0].tolist()}")

        # --- decode() shim ---
        z   = torch.randn(B, model.latent_dim, device=device)
        oh  = model.decode(z)
        assert oh.shape == (B, L, VOCAB), f"Bad decode shape: {oh.shape}"
        print(f"  decode() one-hot shape : {oh.shape}")

    print("\n[OK] All SMILESVAE self-tests passed.")
