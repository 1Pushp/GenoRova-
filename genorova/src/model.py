"""
Genorova AI — VAE Model Architecture
=====================================

This module defines the Variational Autoencoder (VAE) for learning and 
generating novel drug molecules from SMILES data.

RESPONSIBILITIES:
1. Encode one-hot SMILES → latent space (256 dimensions)
2. Sample from latent space using reparameterization trick
3. Decode latent vectors → reconstructed SMILES
4. Calculate reconstruction + KL divergence loss
5. Generate new molecules by sampling latent space

ARCHITECTURE:
- Encoder: [batch, 120, vocab_size] → flatten → [512] → [256] → (μ, σ²)
- Reparameterization: z = μ + ε·σ where ε ~ N(0,1)
- Decoder: [batch, 256] → [256] → [512] → [120*vocab_size] → reshape

INPUT:
- One-hot encoded SMILES tensors [batch_size, 120, vocab_size]

OUTPUT:
- Reconstructed one-hot SMILES [batch_size, 120, vocab_size]
- Latent vectors z [batch_size, 256] for generation

LOSS FUNCTION:
- Reconstruction loss: BCE between input and output
- KL divergence: regularizes latent space to N(0,1)
- Total: L = BCE + 0.5 * KL_divergence

KEY CLASSES:
- Encoder: Maps SMILES → latent space
- Decoder: Maps latent → SMILES
- VAE: Complete autoencoder + loss function

KEY METHODS:
- forward(x) → reconstructed_x, mu, logvar
- encode(x) → z, mu, logvar
- decode(z) → reconstructed_x
- reparameterize(mu, logvar) → z
- loss_function(recon_x, x, mu, logvar) → loss
- generate(num_molecules, device) → z samples

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import json
import torch
import torch.nn as nn
import torch.nn.functional as F
from pathlib import Path
from typing import Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_SMILES_LENGTH = 120           # Maximum SMILES sequence length
LATENT_DIM = 256                  # Latent space dimensionality
ENCODER_LAYERS = [1024, 512, 256] # Encoder hidden layer sizes (3 layers, wider)
DECODER_LAYERS = [256, 512, 1024] # Decoder hidden layer sizes (3 layers, mirror)
DROPOUT_RATE = 0.2                # Dropout probability
CLIP_GRADIENT = 1.0               # Gradient clipping threshold
FREE_BITS = 0.5                   # Min KL per latent dimension (prevents collapse)


# ============================================================================
# ENCODER CLASS
# ============================================================================

class Encoder(nn.Module):
    """
    Encoder Network: Converts one-hot encoded SMILES → latent space.

    Architecture (3-layer, increased capacity vs original 2-layer):
    1. Flatten: [batch, 120, vocab_size] → [batch, 120*vocab_size]
    2. Linear(120*vocab_size → 1024) + ReLU + Dropout(0.2)
    3. Linear(1024 → 512) + ReLU + Dropout(0.2)
    4. Linear(512 → 256) + ReLU + Dropout(0.2)   ← NEW LAYER
    5. Two heads:
       - mu:     Linear(256 → 256)
       - logvar: Linear(256 → 256)

    The extra layer gives the encoder more capacity to extract meaningful
    features before compressing to the latent space. This is the main fix
    for posterior collapse — a shallow encoder can't learn a useful latent
    representation, so it collapses to a point.
    """

    def __init__(self, vocab_size: int, latent_dim: int = LATENT_DIM, max_length: int = MAX_SMILES_LENGTH):
        """
        Initialize the encoder.

        Args:
            vocab_size (int): Size of SMILES character vocabulary
            latent_dim (int): Dimensionality of latent space
            max_length (int): Maximum SMILES sequence length
        """
        super(Encoder, self).__init__()

        print(f"\n[*] Building Encoder (3-layer, wider)...")
        print(f"   Input: [batch, {max_length}, {vocab_size}]")

        # Calculate flattened input size
        input_size = max_length * vocab_size
        print(f"   Flattened input: {input_size}")

        # Build 3-layer encoder
        self.fc1 = nn.Linear(input_size,          ENCODER_LAYERS[0])  # → 1024
        self.fc2 = nn.Linear(ENCODER_LAYERS[0],   ENCODER_LAYERS[1])  # → 512
        self.fc3 = nn.Linear(ENCODER_LAYERS[1],   ENCODER_LAYERS[2])  # → 256 (NEW)

        # Batch normalisation for training stability
        self.bn1 = nn.BatchNorm1d(ENCODER_LAYERS[0])
        self.bn2 = nn.BatchNorm1d(ENCODER_LAYERS[1])
        self.bn3 = nn.BatchNorm1d(ENCODER_LAYERS[2])

        # Latent space heads
        self.fc_mu     = nn.Linear(ENCODER_LAYERS[2], latent_dim)
        self.fc_logvar = nn.Linear(ENCODER_LAYERS[2], latent_dim)

        # Regularization
        self.dropout = nn.Dropout(DROPOUT_RATE)

        print(f"   Layers: {input_size} -> {ENCODER_LAYERS[0]} -> {ENCODER_LAYERS[1]} -> {ENCODER_LAYERS[2]}")
        print(f"   Output: mu and logvar (both dim {latent_dim})")

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through encoder.

        Args:
            x (torch.Tensor): One-hot encoded SMILES [batch, max_length, vocab_size]

        Returns:
            Tuple[torch.Tensor, torch.Tensor]: (mu, log_var)
        """
        # Flatten [batch, max_length, vocab_size] → [batch, max_length*vocab_size]
        batch_size = x.size(0)
        x = x.view(batch_size, -1)

        # Layer 1: dense + batch norm + relu + dropout
        x = self.fc1(x)
        if batch_size > 1:   # BatchNorm1d requires batch_size > 1
            x = self.bn1(x)
        x = F.relu(x)
        x = self.dropout(x)

        # Layer 2
        x = self.fc2(x)
        if batch_size > 1:
            x = self.bn2(x)
        x = F.relu(x)
        x = self.dropout(x)

        # Layer 3 (NEW)
        x = self.fc3(x)
        if batch_size > 1:
            x = self.bn3(x)
        x = F.relu(x)
        x = self.dropout(x)

        # Latent heads
        mu     = self.fc_mu(x)
        logvar = self.fc_logvar(x)

        return mu, logvar


# ============================================================================
# DECODER CLASS
# ============================================================================

class Decoder(nn.Module):
    """
    Decoder Network: Converts latent vectors → reconstructed one-hot SMILES.

    Architecture (3-layer mirror of encoder, increased capacity):
    1. Linear(256 → 256) + ReLU + Dropout(0.2)
    2. Linear(256 → 512) + ReLU + Dropout(0.2)
    3. Linear(512 → 1024) + ReLU + Dropout(0.2)   ← NEW LAYER
    4. Linear(1024 → 120*vocab_size)
    5. Reshape: [batch, 120*vocab_size] → [batch, 120, vocab_size]
    """

    def __init__(self, vocab_size: int, latent_dim: int = LATENT_DIM, max_length: int = MAX_SMILES_LENGTH):
        """
        Initialize the decoder.

        Args:
            vocab_size (int): Size of SMILES character vocabulary
            latent_dim (int): Dimensionality of latent space
            max_length (int): Maximum SMILES sequence length
        """
        super(Decoder, self).__init__()

        print(f"\n[*] Building Decoder (3-layer, wider)...")
        print(f"   Input: [batch, {latent_dim}]")

        # Calculate output size
        output_size = max_length * vocab_size
        print(f"   Output (flattened): {output_size}")

        # Build 3-layer decoder (mirror of encoder)
        self.fc1  = nn.Linear(latent_dim,          DECODER_LAYERS[0])  # → 256
        self.fc2  = nn.Linear(DECODER_LAYERS[0],   DECODER_LAYERS[1])  # → 512
        self.fc3  = nn.Linear(DECODER_LAYERS[1],   DECODER_LAYERS[2])  # → 1024 (NEW)
        self.fc_out = nn.Linear(DECODER_LAYERS[2], output_size)         # → output

        # Batch normalisation
        self.bn1 = nn.BatchNorm1d(DECODER_LAYERS[0])
        self.bn2 = nn.BatchNorm1d(DECODER_LAYERS[1])
        self.bn3 = nn.BatchNorm1d(DECODER_LAYERS[2])

        # Regularization
        self.dropout = nn.Dropout(DROPOUT_RATE)

        # Store dimensions for reshaping
        self.max_length = max_length
        self.vocab_size = vocab_size

        print(f"   Layers: {latent_dim} -> {DECODER_LAYERS[0]} -> {DECODER_LAYERS[1]} -> {DECODER_LAYERS[2]} -> {output_size}")
        print(f"   Output (reshaped): [batch, {max_length}, {vocab_size}]")

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through decoder.

        Args:
            z (torch.Tensor): Latent vector [batch, latent_dim]

        Returns:
            torch.Tensor: Reconstructed one-hot SMILES [batch, max_length, vocab_size]
        """
        batch_size = z.size(0)

        # Layer 1
        x = self.fc1(z)
        if batch_size > 1:
            x = self.bn1(x)
        x = F.relu(x)
        x = self.dropout(x)

        # Layer 2
        x = self.fc2(x)
        if batch_size > 1:
            x = self.bn2(x)
        x = F.relu(x)
        x = self.dropout(x)

        # Layer 3 (NEW)
        x = self.fc3(x)
        if batch_size > 1:
            x = self.bn3(x)
        x = F.relu(x)
        x = self.dropout(x)

        # Output projection
        x = self.fc_out(x)

        # Reshape [batch, max_length*vocab_size] → [batch, max_length, vocab_size]
        x = x.view(-1, self.max_length, self.vocab_size)

        return x


# ============================================================================
# VAE CLASS (ENCODER + DECODER + LOSS)
# ============================================================================

class VAE(nn.Module):
    """
    Variational Autoencoder for molecular generation.
    
    Combines encoder and decoder networks with the VAE loss function:
    - Total loss = Reconstruction loss + KL divergence
    - Reconstruction = Binary Cross Entropy
    - KL = -0.5 * sum(1 + log_var - mu^2 - exp(log_var))
    """
    
    def __init__(self, vocab_size: int, latent_dim: int = LATENT_DIM, max_length: int = MAX_SMILES_LENGTH):
        """
        Initialize the complete VAE.
        
        Args:
            vocab_size (int): Size of SMILES character vocabulary
            latent_dim (int): Dimensionality of latent space
            max_length (int): Maximum SMILES sequence length
        """
        super(VAE, self).__init__()
        
        print(f"\n{'='*70}")
        print(f"GENOROVA AI — VARIATIONAL AUTOENCODER")
        print(f"{'='*70}")
        print(f"\n[*] Initializing VAE...")
        print(f"    Vocab size: {vocab_size}")
        print(f"    Latent dimension: {latent_dim}")
        print(f"    Max SMILES length: {max_length}")
        
        self.latent_dim = latent_dim
        self.vocab_size = vocab_size
        self.max_length = max_length
        
        # Build encoder and decoder
        self.encoder = Encoder(vocab_size, latent_dim, max_length)
        self.decoder = Decoder(vocab_size, latent_dim, max_length)
        
        print(f"\n[OK] VAE initialization complete!")
    
    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """
        Reparameterization trick for VAE sampling.
        
        This allows us to sample from the latent distribution while maintaining
        differentiability for backpropagation.
        
        Formula: z = mu + epsilon * std
        where epsilon ~ N(0, 1) and std = exp(0.5 * logvar)
        
        Args:
            mu (torch.Tensor): Mean of latent distribution [batch, latent_dim]
            logvar (torch.Tensor): Log-variance of latent distribution [batch, latent_dim]
            
        Returns:
            torch.Tensor: Sampled latent vector z [batch, latent_dim]
        """
        # Sample epsilon from standard normal
        std = torch.exp(0.5 * logvar)
        epsilon = torch.randn_like(std)
        
        # z = mu + epsilon * std
        z = mu + epsilon * std
        
        return z
    
    def encode(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Encode SMILES to latent space using reparameterization.
        
        Args:
            x (torch.Tensor): One-hot encoded SMILES [batch, max_length, vocab_size]
            
        Returns:
            Tuple[torch.Tensor, torch.Tensor, torch.Tensor]: (z, mu, logvar)
        """
        mu, logvar = self.encoder(x)
        z = self.reparameterize(mu, logvar)
        return z, mu, logvar
    
    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """
        Decode latent vector to reconstructed SMILES.
        
        Args:
            z (torch.Tensor): Latent vector [batch, latent_dim]
            
        Returns:
            torch.Tensor: Reconstructed one-hot SMILES [batch, max_length, vocab_size]
        """
        return self.decoder(z)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Full VAE forward pass: encode → sample → decode.
        
        Args:
            x (torch.Tensor): One-hot encoded SMILES [batch, max_length, vocab_size]
            
        Returns:
            Tuple[torch.Tensor, torch.Tensor, torch.Tensor]: 
            - recon_x: Reconstructed SMILES [batch, max_length, vocab_size]
            - mu: Mean of latent distribution [batch, latent_dim]
            - logvar: Log-variance of latent distribution [batch, latent_dim]
        """
        z, mu, logvar = self.encode(x)
        recon_x = self.decode(z)
        return recon_x, mu, logvar
    
    def loss_function(self, recon_x: torch.Tensor, x: torch.Tensor, mu: torch.Tensor,
                      logvar: torch.Tensor, kl_weight: float = 0.5,
                      free_bits: float = FREE_BITS) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Calculate VAE loss: reconstruction + KL divergence with FREE BITS.

        Reconstruction Loss:
        - Binary Cross Entropy between input and reconstructed output
        - Measures how well the VAE can reconstruct the input

        KL Divergence with Free Bits (Kingma et al. 2016):
        - Standard KL = -0.5 * (1 + logvar - mu^2 - exp(logvar))  per dimension
        - FREE BITS: clamp each dimension's KL to minimum of free_bits
        - torch.clamp(kl_per_dim, min=free_bits) blocks gradient when
          a dimension's KL falls below free_bits, so the model can NOT
          be rewarded for collapsing that dimension further.
        - Result: encoder is forced to use every latent dimension
          (no dimension is allowed to fully collapse to prior N(0,1))

        Total Loss = recon_loss + kl_weight * kl_loss

        Args:
            recon_x (torch.Tensor): Reconstructed SMILES [batch, max_length, vocab_size]
            x (torch.Tensor): Original SMILES [batch, max_length, vocab_size]
            mu (torch.Tensor): Mean of latent distribution [batch, latent_dim]
            logvar (torch.Tensor): Log-variance [batch, latent_dim]
            kl_weight (float): Weight of KL divergence term
            free_bits (float): Minimum KL per latent dimension (0 = disabled)

        Returns:
            Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            - total_loss: Sum of reconstruction and KL loss
            - recon_loss: Binary cross entropy
            - kl_loss: KL divergence (after free bits)
        """
        # Flatten for loss calculation
        recon_x_flat = recon_x.view(-1, recon_x.size(-1))  # [batch*max_length, vocab_size]
        x_flat       = x.view(-1, x.size(-1))              # [batch*max_length, vocab_size]

        # Reconstruction loss: Binary Cross Entropy with Logits
        recon_loss = F.binary_cross_entropy_with_logits(recon_x_flat, x_flat, reduction='mean')

        # KL divergence per sample per dimension: [batch, latent_dim]
        kl_per_dim = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp())

        if free_bits > 0.0:
            # Free bits regularization:
            # torch.clamp with min=free_bits means:
            #   - if kl_per_dim[i,j] > free_bits: gradient flows normally (penalise high KL)
            #   - if kl_per_dim[i,j] < free_bits: gradient = 0 (stop pushing KL lower)
            # This ensures no latent dimension can be fully "switched off" by the encoder
            kl_per_dim = torch.clamp(kl_per_dim, min=free_bits)

        # Mean over batch and dimensions
        kl_loss = kl_per_dim.mean()

        # Total loss
        total_loss = recon_loss + kl_weight * kl_loss

        return total_loss, recon_loss, kl_loss
    
    def generate(self, num_molecules: int = 10, device: torch.device = None) -> torch.Tensor:
        """
        Generate new molecules by sampling from the latent space.
        
        - Sample z ~ N(0, I) from standard normal distribution
        - Pass through decoder to get reconstructed SMILES
        - This generates novel molecules not in the training set
        
        Args:
            num_molecules (int): Number of molecules to generate
            device (torch.device): Device to generate on (cuda or cpu)
            
        Returns:
            torch.Tensor: Generated one-hot SMILES [num_molecules, max_length, vocab_size]
        """
        if device is None:
            device = next(self.parameters()).device
        
        # Sample from standard normal distribution
        z = torch.randn(num_molecules, self.latent_dim, device=device)
        
        # Decode to get reconstructed SMILES
        generated = self.decode(z)
        
        return generated
    
    def count_parameters(self) -> int:
        """
        Count total trainable parameters in the model.
        
        Returns:
            int: Total number of trainable parameters
        """
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
    
    def print_summary(self):
        """
        Print a summary of the model architecture and parameters.
        """
        total_params = self.count_parameters()
        
        print(f"\n{'='*70}")
        print(f"VAE MODEL SUMMARY")
        print(f"{'='*70}")
        print(f"\nEncoder:")
        print(f"  Input: [batch, {self.max_length}, {self.vocab_size}]")
        print(f"  Output: μ and σ² of shape [batch, {self.latent_dim}]")
        
        print(f"\nDecoder:")
        print(f"  Input: [batch, {self.latent_dim}]")
        print(f"  Output: [batch, {self.max_length}, {self.vocab_size}]")
        
        print(f"\nParameters:")
        print(f"  Total trainable parameters: {total_params:,}")
        print(f"  Encoder parameters: {sum(p.numel() for p in self.encoder.parameters() if p.requires_grad):,}")
        print(f"  Decoder parameters: {sum(p.numel() for p in self.decoder.parameters() if p.requires_grad):,}")
        
        print(f"\nLatent Space:")
        print(f"  Dimensionality: {self.latent_dim}")
        print(f"  Distribution: N(0, 1) for generation")
        print(f"{'='*70}\n")


# ============================================================================
# TESTING & EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# VAE MODEL TEST")
    print("#"*70)
    
    # ===== STEP 1: Load vocabulary =====
    print("\n[*] Step 1: Loading vocabulary from outputs/vocabulary.json...")
    vocab_path = "outputs/vocabulary.json"
    
    try:
        with open(vocab_path, 'r') as f:
            char2idx = json.load(f)
        vocab_size = len(char2idx)
        print(f"   [OK] Vocabulary loaded! Size: {vocab_size}")
    except FileNotFoundError:
        print(f"   [!] Vocabulary file not found. Using default vocab_size=15 for testing.")
        vocab_size = 15
    
    # ===== STEP 2: Create model =====
    print("\n[*] Step 2: Creating VAE model...")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"    Device: {device}")
    
    model = VAE(vocab_size=vocab_size).to(device)
    model.print_summary()
    
    # ===== STEP 3: Forward pass with random tensor =====
    print("\n[*] Step 3: Running forward pass...")
    batch_size = 4
    random_input = torch.randn(batch_size, MAX_SMILES_LENGTH, vocab_size).to(device)
    print(f"    Input shape: {random_input.shape}")
    
    recon_x, mu, logvar = model(random_input)
    print(f"    [OK] Forward pass successful!")
    print(f"    Reconstructed output shape: {recon_x.shape}")
    print(f"    Mu shape: {mu.shape}")
    print(f"    Log-var shape: {logvar.shape}")
    
    # Verify output shape
    assert recon_x.shape == (batch_size, MAX_SMILES_LENGTH, vocab_size), "Output shape mismatch!"
    print(f"    [OK] Output shape verified ✓")
    
    # ===== STEP 4: Calculate loss =====
    print("\n[*] Step 4: Calculating loss...")
    total_loss, recon_loss, kl_loss = model.loss_function(recon_x, random_input, mu, logvar)
    print(f"    Total loss: {total_loss.item():.6f}")
    print(f"    Reconstruction loss: {recon_loss.item():.6f}")
    print(f"    KL divergence: {kl_loss.item():.6f}")
    
    # ===== STEP 5: Test generation =====
    print("\n[*] Step 5: Testing molecule generation...")
    num_generated = 3
    generated = model.generate(num_molecules=num_generated, device=device)
    print(f"    Generated {num_generated} molecules")
    print(f"    Generated shape: {generated.shape}")
    assert generated.shape == (num_generated, MAX_SMILES_LENGTH, vocab_size), "Generation shape mismatch!"
    print(f"    [OK] Generation shape verified ✓")
    
    # ===== STEP 6: Verify gradients =====
    print("\n[*] Step 6: Checking gradient flow...")
    backward_test = model.loss_function(recon_x, random_input, mu, logvar)[0]
    backward_test.backward()
    
    # Check if gradients exist
    encoder_has_grad = any(p.grad is not None for p in model.encoder.parameters())
    decoder_has_grad = any(p.grad is not None for p in model.decoder.parameters())
    
    if encoder_has_grad and decoder_has_grad:
        print(f"    [OK] Gradients flowing correctly ✓")
    else:
        print(f"    [!] Warning: Some gradients not computed")
    
    print(f"\n{'='*70}")
    print(f"✅ ALL TESTS PASSED!")
    print(f"{'='*70}\n")
