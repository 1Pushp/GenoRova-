"""
genorova/models/cvae.py

Conditional Variational Autoencoder (CVAE) for guided SMILES generation.

Architecture
------------
  Encoder     : Transformer (4 heads, 3 layers, d_model=256)
                SMILES tokens -> (mu, log_var) in R^512
  Condition   : Property vector [QED, LogP, MW, SA] -> 64-dim embedding
                concatenated with z before decoding
  Decoder     : Transformer (4 heads, 3 layers), autoregressive
                Teacher forcing during training; beam search (k=5) at inference
  Aux head    : Property predictor from mu for additional learning signal

Loss
----
  L = L_recon + beta(t) * L_KL + lambda_prop * L_prop_aux
  beta uses cyclic annealing: 0 -> 1 linearly over 10 epochs, then resets.

Special token ids (must match BPE tokenizer)
--------------------------------------------
  [PAD]=0  [BOS]=1  [EOS]=2  [UNK]=3  [MASK]=4

Usage
-----
    model = CVAE(vocab_size=1000)
    out   = model(tokens, properties)       # training forward pass
    seqs  = model.generate(props, beam_k=5) # inference
"""

import math
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Special token ids  (match BPE tokenizer special_tokens order)
# ---------------------------------------------------------------------------
PAD_ID  = 0
BOS_ID  = 1
EOS_ID  = 2

# ---------------------------------------------------------------------------
# Default hyperparameters
# ---------------------------------------------------------------------------
D_MODEL     = 256
LATENT_DIM  = 512
PROP_DIM    = 64     # property embedding dimension
NUM_HEADS   = 4
NUM_LAYERS  = 3
FF_DIM      = 1024   # inner feed-forward dimension in each transformer layer
DROPOUT     = 0.1
MAX_SEQ_LEN = 128

NUM_PROPS   = 4      # [QED, LogP, MW, SA_score]
LAMBDA_PROP = 0.5    # weight of auxiliary property prediction loss


# ===========================================================================
# Helpers
# ===========================================================================

def _causal_mask(size: int, device: torch.device) -> torch.Tensor:
    """Upper-triangular bool mask: True = position the decoder must NOT attend to."""
    return torch.triu(torch.ones(size, size, device=device, dtype=torch.bool),
                      diagonal=1)


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding added to embeddings of shape [B, L, d_model]."""

    def __init__(self, d_model: int, max_len: int = MAX_SEQ_LEN,
                 dropout: float = DROPOUT):
        super().__init__()
        self.drop = nn.Dropout(dropout)

        pe  = torch.zeros(max_len, d_model)
        pos = torch.arange(max_len, dtype=torch.float).unsqueeze(1)
        div = torch.exp(torch.arange(0, d_model, 2, dtype=torch.float)
                        * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))  # [1, max_len, d_model]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [B, L, d_model]  ->  [B, L, d_model] with position information."""
        return self.drop(x + self.pe[:, : x.size(1)])


# ===========================================================================
# Sub-modules
# ===========================================================================

class PropertyEncoder(nn.Module):
    """
    Maps raw property vector [QED, LogP, MW, SA] to a fixed-size embedding.
    Two-layer MLP with GELU activation and layer norm for stability.
    """

    def __init__(self, num_props: int = NUM_PROPS, prop_dim: int = PROP_DIM):
        super().__init__()
        hidden = prop_dim * 2
        self.net = nn.Sequential(
            nn.Linear(num_props, hidden),
            nn.GELU(),
            nn.LayerNorm(hidden),
            nn.Linear(hidden, prop_dim),
        )

    def forward(self, props: torch.Tensor) -> torch.Tensor:
        """
        Args:
            props: [B, num_props]  raw property values
        Returns:
            [B, prop_dim]
        """
        return self.net(props)


class SMILESEncoder(nn.Module):
    """
    Transformer encoder: integer SMILES tokens -> (mu, log_var) for the VAE.

    Uses a [CLS]-style mean-pool over non-padding positions, then projects
    to mu and log_var with separate linear heads.
    Pre-LN (norm_first=True) is used for training stability.
    """

    def __init__(self, vocab_size: int, d_model: int = D_MODEL,
                 latent_dim: int = LATENT_DIM, num_heads: int = NUM_HEADS,
                 num_layers: int = NUM_LAYERS, ff_dim: int = FF_DIM,
                 dropout: float = DROPOUT, max_len: int = MAX_SEQ_LEN):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=PAD_ID)
        self.pos_enc   = PositionalEncoding(d_model, max_len, dropout)

        enc_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=num_heads, dim_feedforward=ff_dim,
            dropout=dropout, batch_first=True, norm_first=True,
        )
        self.transformer  = nn.TransformerEncoder(enc_layer, num_layers=num_layers,
                                                  enable_nested_tensor=False)
        self.mu_proj      = nn.Linear(d_model, latent_dim)
        self.logvar_proj  = nn.Linear(d_model, latent_dim)

    def forward(self, tokens: torch.Tensor
                ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            tokens: [B, L] integer token ids (PAD_ID for padding)
        Returns:
            mu      [B, latent_dim]
            log_var [B, latent_dim]
        """
        pad_mask = (tokens == PAD_ID)                            # [B, L] True=pad
        x = self.pos_enc(self.embedding(tokens))                 # [B, L, d_model]
        x = self.transformer(x, src_key_padding_mask=pad_mask)  # [B, L, d_model]

        # Mean-pool over non-padding positions
        not_pad = (~pad_mask).unsqueeze(-1).float()              # [B, L, 1]
        pooled  = (x * not_pad).sum(1) / not_pad.sum(1).clamp(min=1.0)  # [B, d_model]

        return self.mu_proj(pooled), self.logvar_proj(pooled)


class SMILESDecoder(nn.Module):
    """
    Autoregressive transformer decoder.

    The conditional latent vector z_cond is projected to d_model and used as
    a single-token memory sequence.  The decoder cross-attends to this memory
    at every position, effectively conditioning each generated token on z_cond.

    During training: receives full target sequence (teacher forcing).
    During inference: called step-by-step inside beam search.
    """

    def __init__(self, vocab_size: int, d_model: int = D_MODEL,
                 cond_dim: int = LATENT_DIM + PROP_DIM,
                 num_heads: int = NUM_HEADS, num_layers: int = NUM_LAYERS,
                 ff_dim: int = FF_DIM, dropout: float = DROPOUT,
                 max_len: int = MAX_SEQ_LEN):
        super().__init__()
        self.embedding   = nn.Embedding(vocab_size, d_model, padding_idx=PAD_ID)
        self.pos_enc     = PositionalEncoding(d_model, max_len, dropout)
        self.mem_proj    = nn.Linear(cond_dim, d_model)   # project z_cond to d_model

        dec_layer = nn.TransformerDecoderLayer(
            d_model=d_model, nhead=num_heads, dim_feedforward=ff_dim,
            dropout=dropout, batch_first=True, norm_first=True,
        )
        self.transformer = nn.TransformerDecoder(dec_layer, num_layers=num_layers)
        self.out_proj    = nn.Linear(d_model, vocab_size)

    def forward(self, tgt_tokens: torch.Tensor,
                z_cond: torch.Tensor) -> torch.Tensor:
        """
        Args:
            tgt_tokens: [B, L]  decoder input (BOS + token sequence, right-shifted)
            z_cond:     [B, cond_dim]  conditional latent vector
        Returns:
            logits: [B, L, vocab_size]
        """
        B, L = tgt_tokens.shape
        memory      = self.mem_proj(z_cond).unsqueeze(1)     # [B, 1, d_model]
        pad_mask    = (tgt_tokens == PAD_ID)                  # [B, L]
        causal_mask = _causal_mask(L, tgt_tokens.device)     # [L, L]

        x   = self.pos_enc(self.embedding(tgt_tokens))       # [B, L, d_model]
        out = self.transformer(
            tgt=x, memory=memory,
            tgt_mask=causal_mask,
            tgt_key_padding_mask=pad_mask,
        )                                                     # [B, L, d_model]
        return self.out_proj(out)                             # [B, L, vocab_size]


class PropertyPredictor(nn.Module):
    """
    Auxiliary head that regresses drug properties from the latent mu vector.
    Predicting from mu (rather than sampled z) gives a more stable gradient
    and helps the encoder organise its latent space by drug-likeness.
    """

    def __init__(self, latent_dim: int = LATENT_DIM, num_props: int = NUM_PROPS):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.GELU(),
            nn.LayerNorm(128),
            nn.Linear(128, num_props),
        )

    def forward(self, mu: torch.Tensor) -> torch.Tensor:
        """
        Args:
            mu: [B, latent_dim]
        Returns:
            predicted properties [B, num_props]
        """
        return self.net(mu)


# ===========================================================================
# Main model
# ===========================================================================

class CVAE(nn.Module):
    """
    Conditional VAE for property-guided SMILES generation.

    Training forward pass:
        out = model(tokens, properties)
        # out keys: recon_logits, mu, log_var, pred_props

    Inference:
        seqs = model.generate(properties, max_len=128, beam_k=5)
        # returns list of token-id lists, one per batch element

    Property vector order: [QED, LogP, MW, SA_score]
    Token conventions: PAD=0, BOS=1, EOS=2
    """

    def __init__(self,
                 vocab_size: int,
                 d_model:    int = D_MODEL,
                 latent_dim: int = LATENT_DIM,
                 prop_dim:   int = PROP_DIM,
                 num_heads:  int = NUM_HEADS,
                 num_layers: int = NUM_LAYERS,
                 ff_dim:     int = FF_DIM,
                 dropout:    float = DROPOUT,
                 max_len:    int = MAX_SEQ_LEN):
        super().__init__()
        self.latent_dim = latent_dim
        self.prop_dim   = prop_dim
        self.max_len    = max_len

        self.smiles_encoder   = SMILESEncoder(
            vocab_size, d_model, latent_dim, num_heads, num_layers,
            ff_dim, dropout, max_len,
        )
        self.prop_encoder     = PropertyEncoder(NUM_PROPS, prop_dim)
        self.decoder          = SMILESDecoder(
            vocab_size, d_model, latent_dim + prop_dim,
            num_heads, num_layers, ff_dim, dropout, max_len,
        )
        self.prop_predictor   = PropertyPredictor(latent_dim, NUM_PROPS)

    # -----------------------------------------------------------------------
    # Core operations
    # -----------------------------------------------------------------------

    @staticmethod
    def _reparameterize(mu: torch.Tensor,
                        log_var: torch.Tensor) -> torch.Tensor:
        """Sample z = mu + eps * std  (reparameterization trick)."""
        std = (0.5 * log_var).exp()
        return mu + torch.randn_like(std) * std

    def _build_z_cond(self, mu: torch.Tensor, log_var: torch.Tensor,
                      properties: torch.Tensor) -> torch.Tensor:
        """Sample z, encode properties, return concatenated z_cond [B, latent+prop]."""
        z        = self._reparameterize(mu, log_var)
        prop_emb = self.prop_encoder(properties)
        return torch.cat([z, prop_emb], dim=-1)

    def encode(self, tokens: torch.Tensor,
               properties: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Encode tokens + properties to posterior parameters and conditioned latent.

        Returns:
            mu      [B, latent_dim]
            log_var [B, latent_dim]
            z_cond  [B, latent_dim + prop_dim]
        """
        mu, log_var = self.smiles_encoder(tokens)
        z_cond      = self._build_z_cond(mu, log_var, properties)
        return mu, log_var, z_cond

    def forward(self, tokens: torch.Tensor,
                properties: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Training forward pass with teacher forcing.

        Args:
            tokens:     [B, L]  full sequence  [BOS, tok1, ..., tokN, EOS, PAD...]
            properties: [B, 4]  [QED, LogP, MW, SA_score]

        Returns dict:
            recon_logits [B, L-1, vocab_size]  predictions for positions 1..L
            mu           [B, latent_dim]
            log_var      [B, latent_dim]
            pred_props   [B, 4]
        """
        mu, log_var, z_cond = self.encode(tokens, properties)

        # Teacher forcing: feed [BOS..tokN-1], predict [tok1..EOS]
        dec_input    = tokens[:, :-1]           # drop last token
        recon_logits = self.decoder(dec_input, z_cond)   # [B, L-1, vocab]

        pred_props = self.prop_predictor(mu)    # regress from mu for stable gradients

        return {
            "recon_logits": recon_logits,
            "mu":           mu,
            "log_var":      log_var,
            "pred_props":   pred_props,
        }

    # -----------------------------------------------------------------------
    # Inference
    # -----------------------------------------------------------------------

    @torch.no_grad()
    def generate(self, properties: torch.Tensor,
                 max_len: int = MAX_SEQ_LEN,
                 beam_k: int = 5,
                 temperature: float = 1.0) -> list[list[int]]:
        """
        Generate SMILES sequences from desired property targets.

        Samples z from the prior N(0, I) — no encoder input needed.

        Args:
            properties:  [B, 4]  target drug properties
            max_len:     maximum tokens to generate (including BOS)
            beam_k:      beam width; 1 = greedy / temperature sampling
            temperature: logit temperature for greedy mode (ignored when beam_k > 1)

        Returns:
            List of B token-id sequences (each ends just before EOS or at max_len)
        """
        self.eval()
        device = properties.device
        B      = properties.size(0)

        # Sample from prior rather than encoding a SMILES input
        z        = torch.randn(B, self.latent_dim, device=device)
        prop_emb = self.prop_encoder(properties)
        z_cond   = torch.cat([z, prop_emb], dim=-1)     # [B, cond_dim]

        results = []
        for b in range(B):
            z_b = z_cond[b : b + 1]                     # [1, cond_dim]
            if beam_k > 1:
                seq = self._beam_search(z_b, max_len, beam_k, device)
            else:
                seq = self._greedy_decode(z_b, max_len, temperature, device)
            results.append(seq)
        return results

    def _decode_one_step(self, z_cond: torch.Tensor, token_ids: list[int],
                         device: torch.device) -> torch.Tensor:
        """
        Run decoder on accumulated token_ids and return logits for the last position.
        Called once per beam-search step (no KV-cache — simple but correct).
        Returns [vocab_size] float tensor.
        """
        tgt    = torch.tensor([token_ids], dtype=torch.long, device=device)
        logits = self.decoder(tgt, z_cond)   # [1, L, vocab]
        return logits[0, -1]                 # [vocab]

    def _beam_search(self, z_cond: torch.Tensor, max_len: int,
                     beam_k: int, device: torch.device) -> list[int]:
        """
        Beam search decoding for a single sample z_cond [1, cond_dim].

        Maintains beam_k partial hypotheses, expanding each by top-k tokens
        at every step.  Returns the highest-scoring completed hypothesis.
        """
        # Beam state: (cumulative_log_prob, token_ids, is_complete)
        beams:     list[tuple[float, list[int], bool]] = [(0.0, [BOS_ID], False)]
        completed: list[tuple[float, list[int]]]       = []

        for _ in range(max_len - 1):
            if not beams:
                break

            candidates: list[tuple[float, list[int], bool]] = []

            for log_prob, token_ids, is_done in beams:
                if is_done:
                    completed.append((log_prob, token_ids))
                    continue

                logits      = self._decode_one_step(z_cond, token_ids, device)
                log_probs   = F.log_softmax(logits, dim=-1)
                top_lp, top_ids = log_probs.topk(beam_k)

                for nlp, nid in zip(top_lp.tolist(), top_ids.tolist()):
                    new_ids   = token_ids + [nid]
                    new_lp    = log_prob + nlp
                    is_done_  = (nid == EOS_ID) or (len(new_ids) >= max_len)
                    candidates.append((new_lp, new_ids, is_done_))

            # Prune to top beam_k candidates
            candidates.sort(key=lambda t: t[0], reverse=True)
            beams = candidates[:beam_k]

            # Early exit if all beams are complete
            if all(done for _, _, done in beams):
                break

        # Collect all remaining beams
        for lp, toks, _ in beams:
            completed.append((lp, toks))

        if not completed:
            return [BOS_ID]

        completed.sort(key=lambda t: t[0], reverse=True)
        return completed[0][1]

    def _greedy_decode(self, z_cond: torch.Tensor, max_len: int,
                       temperature: float, device: torch.device) -> list[int]:
        """
        Temperature-scaled multinomial sampling for a single sample.

        Divides logits by temperature, then samples from the resulting
        categorical distribution.  temperature=1.0 is standard sampling;
        lower values sharpen the distribution (more deterministic);
        higher values flatten it (more diverse but less valid).

        Previously used argmax, which is invariant to temperature scaling
        (argmax(logits/T) == argmax(logits) for any T>0), causing every z
        sample to decode to the same molecule regardless of temperature.
        """
        token_ids = [BOS_ID]
        for _ in range(max_len - 1):
            logits  = self._decode_one_step(z_cond, token_ids, device)
            probs   = F.softmax(logits / max(temperature, 1e-6), dim=-1)
            next_id = int(torch.multinomial(probs, num_samples=1))
            token_ids.append(next_id)
            if next_id == EOS_ID:
                break
        return token_ids


# ===========================================================================
# Loss function
# ===========================================================================

def cvae_loss(
    recon_logits:  torch.Tensor,   # [B, L-1, vocab]  model output
    target_tokens: torch.Tensor,   # [B, L]   full sequence incl. BOS and EOS
    mu:            torch.Tensor,   # [B, latent_dim]
    log_var:       torch.Tensor,   # [B, latent_dim]
    pred_props:    torch.Tensor,   # [B, num_props]
    true_props:    torch.Tensor,   # [B, num_props]
    beta:          float = 1.0,
    lambda_prop:   float = LAMBDA_PROP,
) -> dict[str, torch.Tensor]:
    """
    Compute all CVAE loss components and return them in a dict.

    L_total = L_recon + beta * L_KL + lambda_prop * L_prop

    L_recon: token-level cross-entropy (ignores PAD positions)
    L_KL:    mean KL divergence from N(0,I) prior
    L_prop:  MSE between predicted and true drug properties

    Args:
        beta:        current KL weight (from cyclic_beta scheduler)
        lambda_prop: weight of the auxiliary property loss

    Returns:
        dict with keys: loss, recon_loss, kl_loss, prop_loss
    """
    # Target is tokens shifted left: skip BOS, keep EOS
    tgt          = target_tokens[:, 1:]          # [B, L-1]
    B, T, V      = recon_logits.shape

    l_recon = F.cross_entropy(
        recon_logits.reshape(B * T, V),
        tgt.reshape(B * T),
        ignore_index=PAD_ID,
        reduction="mean",
    )

    # KL term: -0.5 * sum_d(1 + log_var - mu^2 - exp(log_var)), averaged over batch
    l_kl = -0.5 * (1.0 + log_var - mu.pow(2) - log_var.exp()).sum(dim=1).mean()

    l_prop = F.mse_loss(pred_props, true_props)

    l_total = l_recon + beta * l_kl + lambda_prop * l_prop

    return {
        "loss":       l_total,
        "recon_loss": l_recon.detach(),
        "kl_loss":    l_kl.detach(),
        "prop_loss":  l_prop.detach(),
    }


# ===========================================================================
# Cyclic annealing schedule
# ===========================================================================

def cyclic_beta(epoch: int, cycle_len: int = 10,
                max_beta: float = 1.0) -> float:
    """
    Cyclic KL annealing schedule (Liu et al. 2019).

    beta rises linearly from 0 to max_beta over cycle_len epochs, then resets.
    This prevents posterior collapse by letting the decoder first learn
    reconstruction before the KL penalty becomes fully active.

    Args:
        epoch:     current training epoch (0-indexed)
        cycle_len: number of epochs per annealing cycle
        max_beta:  peak KL weight

    Returns:
        beta in [0, max_beta]

    Example:
        epoch=0  -> 0.0   (KL off, reconstruction dominates)
        epoch=5  -> 0.5
        epoch=9  -> 0.9
        epoch=10 -> 0.0   (new cycle begins)
    """
    return max_beta * ((epoch % cycle_len) / cycle_len)


# ===========================================================================
# Model summary
# ===========================================================================

def print_model_summary(model: CVAE) -> None:
    """Print parameter count per sub-module and total."""
    parts = {
        "SMILESEncoder":    model.smiles_encoder,
        "PropertyEncoder":  model.prop_encoder,
        "SMILESDecoder":    model.decoder,
        "PropertyPredictor": model.prop_predictor,
    }
    grand_total = 0
    print("\n" + "=" * 58)
    print(f"  Genorova CVAE -- Parameter Summary")
    print("=" * 58)
    print(f"  {'Component':<24} {'Parameters':>14} {'Trainable':>12}")
    print("-" * 58)
    for name, module in parts.items():
        n_all      = sum(p.numel() for p in module.parameters())
        n_train    = sum(p.numel() for p in module.parameters() if p.requires_grad)
        grand_total += n_all
        print(f"  {name:<24} {n_all:>14,} {n_train:>12,}")
    print("-" * 58)
    print(f"  {'TOTAL':<24} {grand_total:>14,}")
    print("=" * 58 + "\n")


# ===========================================================================
# Self-test
# ===========================================================================

if __name__ == "__main__":
    print("Genorova AI -- CVAE self-test")
    print("-" * 40)

    VOCAB  = 1000
    BATCH  = 4
    SEQLEN = 48     # shorter for fast test

    model = CVAE(vocab_size=VOCAB)
    print_model_summary(model)

    # Synthetic batch: random tokens with BOS/EOS markers
    tokens = torch.randint(5, VOCAB, (BATCH, SEQLEN))
    tokens[:, 0]  = BOS_ID
    tokens[:, -1] = EOS_ID
    props  = torch.rand(BATCH, 4)           # [QED, LogP, MW, SA]

    # --- Training forward pass ---
    out  = model(tokens, props)
    beta = cyclic_beta(epoch=3, cycle_len=10)
    loss = cvae_loss(
        out["recon_logits"], tokens,
        out["mu"], out["log_var"],
        out["pred_props"], props,
        beta=beta,
    )

    print("Training forward pass:")
    print(f"  recon_logits : {tuple(out['recon_logits'].shape)}")
    print(f"  mu           : {tuple(out['mu'].shape)}")
    print(f"  log_var      : {tuple(out['log_var'].shape)}")
    print(f"  pred_props   : {tuple(out['pred_props'].shape)}")
    print(f"\nLoss at epoch 3  (beta={beta:.2f}):")
    for k, v in loss.items():
        print(f"  {k:<14}: {v.item():.4f}")

    # --- Loss backward ---
    loss["loss"].backward()
    print("\n  backward() OK (gradients flow through all components)")

    # --- Beam search generation ---
    model.zero_grad()
    print("\nBeam search generation  (beam_k=5) ...")
    target_props = torch.tensor([[0.8, 2.5, 300.0, 3.0],
                                 [0.6, 1.0, 200.0, 4.0]])
    seqs = model.generate(target_props, max_len=30, beam_k=5)
    for i, seq in enumerate(seqs):
        print(f"  sample {i}: {len(seq)} tokens, first 8 ids: {seq[:8]}")

    # --- Greedy generation ---
    print("\nGreedy generation  (beam_k=1, temperature=0.8) ...")
    seqs2 = model.generate(target_props, max_len=30, beam_k=1, temperature=0.8)
    for i, seq in enumerate(seqs2):
        print(f"  sample {i}: {len(seq)} tokens, first 8 ids: {seq[:8]}")

    print("\n[PASS] CVAE self-test complete.")
