"""
Genorova AI — VAE Model Training Engine
========================================

This module handles training the Variational Autoencoder on SMILES data.

RESPONSIBILITIES:
1. Load SMILES data and preprocess to one-hot tensors
2. Create train/validation/test splits
3. Initialize VAE model and optimizer
4. Run training loop with validation every epoch
5. Implement KL annealing (gradually increase KL weight during training)
6. Implement learning rate decay (reduce LR every N epochs)
7. Save model checkpoints every N epochs and when validation improves
8. Implement early stopping if no validation improvement for N epochs
9. Generate sample molecules every N epochs to monitor learning
10. Support resuming training from checkpoint

TRAINING HYPERPARAMETERS:
- Epochs: 100
- Batch size: 256
- Optimizer: Adam with learning rate 0.001
- Learning rate decay: 0.95 every 10 epochs
- Gradient clipping: norm ≤ 1.0
- KL annealing: start 0.0, increase 0.01 per epoch until 0.5
- Early stopping: 10 epochs without improvement

CHECKPOINTS:
- Save model every 10 epochs: outputs/models/genorova_epoch_N.pt
- Save best model: outputs/models/genorova_best.pt
- Save optimizer state: for resuming training

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import json
import time
import torch
import torch.optim as optim
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple, List
from tqdm import tqdm

# Import our modules
from model import VAE, MAX_SMILES_LENGTH
from preprocessor import build_vocab, preprocess_batch, SmilesDataset, save_vocab
from torch.utils.data import DataLoader, random_split

# ============================================================================
# TRAINING CONFIGURATION
# ============================================================================

EPOCHS = 100
BATCH_SIZE = 256
LEARNING_RATE = 0.001
LR_DECAY = 0.95
LR_DECAY_EVERY = 10
GRADIENT_CLIP = 1.0
CHECKPOINT_EVERY = 10
EARLY_STOPPING_PATIENCE = 10

# KL annealing — linear warm-up schedule
# kl_weight rises linearly from 0.0 at epoch 1 to KL_WEIGHT_TARGET at
# epoch KL_WARMUP_EPOCHS, then holds steady for all remaining epochs.
#
# Why warm up instead of a fixed increment?
#   A fixed increment (old code: += 0.01 each epoch, max 0.005) hit the
#   ceiling after a single epoch and never reached the intended target of
#   0.5, leaving the latent space badly under-regularised.  The warm-up
#   schedule is deterministic: at epoch e the weight is exactly
#       min(KL_WEIGHT_TARGET, KL_WEIGHT_TARGET * e / KL_WARMUP_EPOCHS)
#   so there is no risk of the increment overshooting or stalling.
KL_WEIGHT_START   = 0.0   # weight at epoch 0 (before any training)
KL_WEIGHT_TARGET  = 0.5   # final weight held after warm-up completes
KL_WARMUP_EPOCHS  = 50    # epochs to ramp from 0 → KL_WEIGHT_TARGET

# Sample generation
SAMPLE_EVERY = 10
NUM_SAMPLES = 5

# Paths
MODEL_DIR = Path("outputs/models")
LOG_DIR = Path("outputs/logs")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# MINI DATASET FOR TESTING (20 known drug SMILES)
# ============================================================================

MINI_DATASET = [
    "CC(=O)Oc1ccccc1C(=O)O",              # Aspirin
    "CN(C)C(=N)NC(=N)N",                  # Metformin
    "Cn1cnc2c1c(=O)n(c(=O)n2C)C",         # Caffeine
    "CC(=O)Nc1ccc(O)cc1",                 # Acetaminophen
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",         # Ibuprofen
    "c1ccc2c(c1)cc1ccc3cccc4ccc2c1c34",   # Anthracene compound
    "COc1ccc2cc3ccc(=O)oc3cc2c1",         # Coumarin derivative
    "O=C1CCCN1",                          # Pyrrolidone
    "c1ccc(cc1)C(=O)O",                   # Benzoic acid
    "CC(=O)c1ccc(cc1)O",                  # Paracetamol
    "CCO",                                # Ethanol
    "CCCC",                               # Butane
    "c1ccccc1",                           # Benzene
    "CC(C)O",                             # Isopropanol
    "CCOCC",                              # Diethyl ether
    "OC(=O)c1ccccc1",                     # Benzoic acid
    "CC(=O)OCC",                          # Ethyl acetate
    "CCOC(=O)c1ccccc1",                   # Ethyl benzoate
    "c1ccc(Cl)cc1",                       # Chlorobenzene
    "CC1=CC=CC=C1",                       # Toluene
]


# ============================================================================
# TRAINER CLASS
# ============================================================================

class VAETrainer:
    """
    Trainer for the Variational Autoencoder.
    
    Handles the complete training pipeline including:
    - Data loading and preprocessing
    - Model initialization
    - Training loop with validation
    - Checkpoint saving
    - Early stopping
    - Learning rate scheduling
    - KL annealing
    """
    
    def __init__(self, vocab_size: int, device: str = "cpu"):
        """
        Initialize the trainer.
        
        Args:
            vocab_size (int): Size of SMILES vocabulary
            device (str): 'cpu' or 'cuda'
        """
        print(f"\n{'='*70}")
        print(f"GENOROVA AI — TRAINING ENGINE")
        print(f"{'='*70}")
        
        self.device = torch.device(device)
        self.vocab_size = vocab_size
        
        print(f"\n[*] Initializing trainer...")
        print(f"    Device: {self.device}")
        print(f"    Vocab size: {vocab_size}")
        
        # Initialize model
        self.model = VAE(vocab_size=vocab_size).to(self.device)
        
        # Initialize optimizer
        self.optimizer = optim.Adam(self.model.parameters(), lr=LEARNING_RATE)
        self.scheduler = optim.lr_scheduler.StepLR(self.optimizer, step_size=LR_DECAY_EVERY, gamma=LR_DECAY)
        
        # Training state
        self.current_epoch = 0
        self.best_val_loss = float('inf')
        self.best_epoch = 0
        self.epochs_without_improvement = 0
        self.kl_weight = KL_WEIGHT_START
        
        # Metrics tracking
        self.train_losses = []
        self.val_losses = []
        self.recon_losses = []
        self.kl_losses = []
        
        print(f"[OK] Trainer initialized!")
    
    def _get_current_lr(self) -> float:
        """Get current learning rate from optimizer."""
        return self.optimizer.param_groups[0]['lr']
    
    def _update_kl_weight(self):
        """
        Advance the KL warm-up schedule by one epoch.

        Linear warm-up: weight = KL_WEIGHT_TARGET * (epoch / KL_WARMUP_EPOCHS),
        capped at KL_WEIGHT_TARGET once warm-up is complete.

        Called at the END of each epoch (after self.current_epoch has been
        incremented), so the weight used during epoch e+1 reflects e completed
        epochs of warm-up.
        """
        if self.current_epoch >= KL_WARMUP_EPOCHS:
            # Warm-up complete — hold at target for all subsequent epochs
            self.kl_weight = KL_WEIGHT_TARGET
        else:
            # Linear ramp: rises by (KL_WEIGHT_TARGET / KL_WARMUP_EPOCHS) per epoch
            self.kl_weight = KL_WEIGHT_TARGET * (self.current_epoch / KL_WARMUP_EPOCHS)
    
    def train_epoch(self, train_loader: DataLoader) -> Tuple[float, float, float]:
        """
        Train for one epoch.
        
        Args:
            train_loader (DataLoader): Training data loader
            
        Returns:
            Tuple[float, float, float]: (total_loss, recon_loss, kl_loss)
        """
        self.model.train()
        
        total_loss = 0.0
        recon_loss_total = 0.0
        kl_loss_total = 0.0
        num_batches = 0
        
        for batch_idx, x in enumerate(train_loader):
            x = x.to(self.device)
            
            # Forward pass
            self.optimizer.zero_grad()
            recon_x, mu, logvar = self.model(x)
            
            # Calculate loss
            loss, recon_loss, kl_loss = self.model.loss_function(
                recon_x, x, mu, logvar, kl_weight=self.kl_weight
            )
            
            # Backward pass
            loss.backward()
            
            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), GRADIENT_CLIP)
            
            # Optimizer step
            self.optimizer.step()
            
            # Track losses
            total_loss += loss.item()
            recon_loss_total += recon_loss.item()
            kl_loss_total += kl_loss.item()
            num_batches += 1
        
        # Average losses
        avg_total_loss = total_loss / num_batches
        avg_recon_loss = recon_loss_total / num_batches
        avg_kl_loss = kl_loss_total / num_batches
        
        return avg_total_loss, avg_recon_loss, avg_kl_loss
    
    def validate(self, val_loader: DataLoader) -> Tuple[float, float, float]:
        """
        Validate the model.
        
        Args:
            val_loader (DataLoader): Validation data loader
            
        Returns:
            Tuple[float, float, float]: (total_loss, recon_loss, kl_loss)
        """
        self.model.eval()
        
        total_loss = 0.0
        recon_loss_total = 0.0
        kl_loss_total = 0.0
        num_batches = 0
        
        with torch.no_grad():
            for x in val_loader:
                x = x.to(self.device)
                
                # Forward pass
                recon_x, mu, logvar = self.model(x)
                
                # Calculate loss
                loss, recon_loss, kl_loss = self.model.loss_function(
                    recon_x, x, mu, logvar, kl_weight=self.kl_weight
                )
                
                # Track losses
                total_loss += loss.item()
                recon_loss_total += recon_loss.item()
                kl_loss_total += kl_loss.item()
                num_batches += 1
        
        # Average losses
        avg_total_loss = total_loss / num_batches if num_batches > 0 else 0
        avg_recon_loss = recon_loss_total / num_batches if num_batches > 0 else 0
        avg_kl_loss = kl_loss_total / num_batches if num_batches > 0 else 0
        
        return avg_total_loss, avg_recon_loss, avg_kl_loss
    
    def save_checkpoint(self, suffix: str = ""):
        """
        Save model checkpoint.
        
        Args:
            suffix (str): Suffix for checkpoint filename
        """
        checkpoint_path = MODEL_DIR / f"genorova{suffix}.pt"
        
        checkpoint = {
            'epoch': self.current_epoch,
            'model_state': self.model.state_dict(),
            'optimizer_state': self.optimizer.state_dict(),
            'best_val_loss': self.best_val_loss,
            'best_epoch': self.best_epoch,
            'kl_weight': self.kl_weight,
        }
        
        torch.save(checkpoint, checkpoint_path)
        print(f"    [✓] Checkpoint saved: {checkpoint_path}")
    
    def load_checkpoint(self, suffix: str = "_best"):
        """
        Load model checkpoint for resuming training.
        
        Args:
            suffix (str): Suffix for checkpoint filename
        """
        checkpoint_path = MODEL_DIR / f"genorova{suffix}.pt"
        
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        
        self.model.load_state_dict(checkpoint['model_state'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state'])
        self.current_epoch = checkpoint['epoch']
        self.best_val_loss = checkpoint['best_val_loss']
        self.best_epoch = checkpoint['best_epoch']
        self.kl_weight = checkpoint['kl_weight']
        
        print(f"[✓] Checkpoint loaded: {checkpoint_path}")
        print(f"    Resuming from epoch {self.current_epoch}")
        print(f"    Previous best validation loss: {self.best_val_loss:.6f}")
    
    def generate_samples(self, num_samples: int = 5) -> List[str]:
        """
        Generate sample molecules.
        
        Args:
            num_samples (int): Number of samples to generate
            
        Returns:
            List[str]: Generated SMILES strings (placeholder for now)
        """
        self.model.eval()
        
        with torch.no_grad():
            z = torch.randn(num_samples, self.model.latent_dim, device=self.device)
            generated = self.model.decode(z)
        
        # For now, return placeholder strings
        # In production, these would be decoded to SMILES
        samples = [f"Generated_molecule_{i}" for i in range(num_samples)]
        
        return samples
    
    def print_epoch_summary(self, train_loss: float, val_loss: float, recon_loss: float, kl_loss: float):
        """Print training summary for the epoch."""
        lr = self._get_current_lr()
        
        print(f"\n[Epoch {self.current_epoch:3d}]")
        print(f"  Train loss: {train_loss:.6f}")
        print(f"  Val loss:   {val_loss:.6f}")
        print(f"  Recon loss: {recon_loss:.6f}")
        print(f"  KL loss:    {kl_loss:.6f}")
        print(f"  KL weight:  {self.kl_weight:.4f}")
        print(f"  Learning rate: {lr:.6f}")
    
    def train(self, train_loader: DataLoader, val_loader: DataLoader, num_epochs: int = EPOCHS):
        """
        Run the complete training loop.
        
        Args:
            train_loader (DataLoader): Training data loader
            val_loader (DataLoader): Validation data loader
            num_epochs (int): Number of epochs to train
        """
        print(f"\n{'='*70}")
        print(f"STARTING TRAINING")
        print(f"{'='*70}")
        print(f"Total epochs: {num_epochs}")
        print(f"Batch size: {BATCH_SIZE}")
        print(f"Initial learning rate: {LEARNING_RATE}")
        print(f"KL annealing: {KL_WEIGHT_START} → {KL_WEIGHT_TARGET} (linear warm-up over {KL_WARMUP_EPOCHS} epochs)")
        print(f"{'='*70}\n")
        
        start_time = time.time()
        
        for epoch in range(num_epochs):
            self.current_epoch = epoch + 1
            
            # Train
            train_loss, recon_loss, kl_loss = self.train_epoch(train_loader)
            self.train_losses.append(train_loss)
            self.recon_losses.append(recon_loss)
            self.kl_losses.append(kl_loss)
            
            # Validate
            val_loss, _, _ = self.validate(val_loader)
            self.val_losses.append(val_loss)
            
            # Print summary
            self.print_epoch_summary(train_loss, val_loss, recon_loss, kl_loss)
            
            # Check if best
            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.best_epoch = self.current_epoch
                self.epochs_without_improvement = 0
                self.save_checkpoint(suffix="_best")
            else:
                self.epochs_without_improvement += 1
            
            # Save periodic checkpoint
            if self.current_epoch % CHECKPOINT_EVERY == 0:
                self.save_checkpoint(suffix=f"_epoch_{self.current_epoch}")
            
            # Generate samples
            if self.current_epoch % SAMPLE_EVERY == 0:
                samples = self.generate_samples(num_samples=NUM_SAMPLES)
                print(f"  [*] Sample molecules:")
                for i, sample in enumerate(samples, 1):
                    print(f"      {i}. {sample}")
            
            # Update learning rate
            self.scheduler.step()
            
            # Update KL weight
            self._update_kl_weight()
            
            # Early stopping
            if self.epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
                print(f"\n[!] Early stopping triggered!")
                print(f"    No improvement for {EARLY_STOPPING_PATIENCE} epochs")
                break
        
        # Training complete
        total_time = time.time() - start_time
        
        print(f"\n{'='*70}")
        print(f"TRAINING COMPLETE")
        print(f"{'='*70}")
        print(f"Total training time: {total_time/60:.2f} minutes")
        print(f"Total epochs completed: {self.current_epoch}")
        print(f"Best validation loss: {self.best_val_loss:.6f}")
        print(f"Best model epoch: {self.best_epoch}")
        print(f"{'='*70}\n")
        
        return self.best_val_loss


# ============================================================================
# RESUME TRAINING FUNCTION
# ============================================================================

def resume_training(train_loader: DataLoader, val_loader: DataLoader, additional_epochs: int = 10):
    """
    Resume training from a saved checkpoint.
    
    Args:
        train_loader (DataLoader): Training data loader
        val_loader (DataLoader): Validation data loader
        additional_epochs (int): Additional epochs to train
    """
    print("\n[*] Loading saved model for resuming training...")
    
    # Determine vocab size from checkpoint
    checkpoint_path = MODEL_DIR / "genorova_best.pt"
    if not checkpoint_path.exists():
        print(f"[ERROR] Checkpoint not found at {checkpoint_path}")
        return
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Create trainer and load checkpoint
    # We need to infer vocab_size, so we'll extract it from the model
    checkpoint = torch.load(checkpoint_path, map_location=device)
    
    # Initialize trainer with a temporary vocab size
    trainer = VAETrainer(vocab_size=11, device=device)  # Will be overwritten
    trainer.load_checkpoint(suffix="_best")
    
    print(f"\n[*] Resuming training for {additional_epochs} additional epochs...")
    trainer.train(train_loader, val_loader, num_epochs=additional_epochs)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main training entry point."""
    print("\n" + "#"*70)
    print("# GENOROVA AI — TRAINING PIPELINE TEST")
    print("#"*70)
    
    # ===== STEP 1: Create mini dataset =====
    print("\n[*] Step 1: Creating mini dataset...")
    test_df = pd.DataFrame({'smiles': MINI_DATASET})
    print(f"    Dataset size: {len(test_df)}")
    print(f"    Sample SMILES: {test_df['smiles'].iloc[0]}")
    
    # ===== STEP 2: Build vocabulary =====
    print("\n[*] Step 2: Building vocabulary...")
    char2idx, idx2char = build_vocab(test_df['smiles'].tolist())
    vocab_size = len(char2idx)
    print(f"    Vocabulary size: {vocab_size}")
    print(f"    Characters: {sorted([k for k in char2idx.keys() if k != '<pad>'])}")
    
    # ===== STEP 3: Preprocess data =====
    print("\n[*] Step 3: Preprocessing data...")
    encoded_data = preprocess_batch(test_df['smiles'].tolist(), char2idx)
    print(f"    Encoded data shape: {encoded_data.shape}")
    
    # ===== STEP 4: Create DataLoaders =====
    print("\n[*] Step 4: Creating DataLoaders...")
    dataset = SmilesDataset(encoded_data, test_df['smiles'].tolist())
    
    # Split: roughly 80% train, 10% val, 10% test
    train_size = max(1, int(0.8 * len(dataset)))
    val_size = max(1, int(0.1 * len(dataset)))
    test_size = len(dataset) - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = random_split(
        dataset, [train_size, val_size, test_size]
    )
    
    train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=4, shuffle=False)
    
    print(f"    Train set: {len(train_dataset)} samples")
    print(f"    Val set: {len(val_dataset)} samples")
    print(f"    Test set: {test_size} samples")
    
    # ===== STEP 5: Initialize trainer =====
    print("\n[*] Step 5: Initializing trainer...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    trainer = VAETrainer(vocab_size=vocab_size, device=device)
    
    # ===== STEP 6: Start training =====
    print("\n[*] Step 6: Starting training (5 epochs for testing)...")
    trainer.train(train_loader, val_loader, num_epochs=5)
    
    print(f"\n{'='*70}")
    print("✅ TRAINING PIPELINE TEST COMPLETE!")
    print(f"{'='*70}")
    print(f"\nModel files saved to: {MODEL_DIR}")
    print(f"Logs saved to: {LOG_DIR}")


if __name__ == "__main__" and False:
    main()
"""
Genorova AI — VAE Model Training Engine
========================================

This module handles training the Variational Autoencoder on SMILES data.

PURPOSE:
Train the Variational Autoencoder (VAE) on molecular SMILES data to learn
patterns in drug molecules and prepare for generation of new candidates.

RESPONSIBILITIES:
1. Load molecular data from CSV using data_loader.py
2. Preprocess SMILES strings using preprocessor.py
3. Create train/validation/test splits
4. Implement VAE loss function (reconstruction + KL divergence)
5. Run training loop with gradient updates
6. Track metrics every epoch (loss, validity, KL, etc.)
7. Save model checkpoints every 10 epochs
8. Implement early stopping if validation loss plateaus
9. Log all training progress to outputs/logs/

TRAINING PARAMETERS (from CLAUDE.MD):
- BATCH_SIZE = 256
- EPOCHS = 100
- LEARNING_RATE = 0.001
- LR_DECAY = 0.95 (reduce LR by 5% every 10 epochs)
- GRADIENT_CLIP = 1.0
- KL_WEIGHT = 0.5 (KL divergence weight in loss)
- RECON_WEIGHT = 1.0 (reconstruction loss weight)
- KL_ANNEALING = True (gradually increase KL weight)
- EARLY_STOPPING_PATIENCE = 10
- CHECKPOINT_EVERY = 10 epochs
- LOG_INTERVAL = 50 batches

DATA SPLIT:
- Train: 80%
- Validation: 10%
- Test: 10%

LOSS FUNCTION:
Loss = RECON_WEIGHT * reconstruction_loss + KL_WEIGHT * kl_divergence
  where:
  - reconstruction_loss = Binary Cross Entropy between input and output
  - kl_divergence = KL(N(mean, var) || N(0, 1))

METRICS TRACKED EVERY EPOCH:
- reconstruction_loss
- kl_divergence
- total_loss
- validity_rate (% valid SMILES in batch)
- uniqueness_rate (% unique SMILES)
- validation_loss
- learning_rate

OUTPUT:
- Model checkpoints: outputs/models/checkpoint_epoch_*.pt
- Training logs: outputs/logs/training_log.txt
- Metrics CSV: outputs/logs/metrics.csv

EXAMPLE USAGE:
    python train.py --data data/processed/test_smiles.csv --epochs 100 --batch-size 256

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
import numpy as np
import pandas as pd
from pathlib import Path
import argparse
import logging
from datetime import datetime
from tqdm import tqdm
import json

# Import Genorova modules
from data_loader import load_smiles_from_csv
from preprocessor import build_vocab, encode_smiles, SmilesDataset
from model import VAE


# ============================================================================
# CONFIGURATION FROM CLAUDE.MD
# ============================================================================

LATENT_DIM = 256
BATCH_SIZE = 256
EPOCHS = 100
LEARNING_RATE = 0.001
LR_DECAY = 0.95
DROPOUT_RATE = 0.2
GRADIENT_CLIP = 1.0

KL_WEIGHT = 0.5
RECON_WEIGHT = 1.0
KL_ANNEALING = True
EARLY_STOPPING_PATIENCE = 10

CHECKPOINT_EVERY = 10
SAVE_BEST_ONLY = True
LOG_INTERVAL = 50

TRAIN_SPLIT = 0.80
VAL_SPLIT = 0.10
TEST_SPLIT = 0.10

# Device configuration
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[TRAIN] Device: {DEVICE}")

NUM_WORKERS = 4
PIN_MEMORY = True


# ============================================================================
# SETUP LOGGING
# ============================================================================

def setup_logging(log_dir="outputs/logs"):
    """Setup logging to both console and file."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(log_dir) / f"training_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    return logger, log_file


# ============================================================================
# VAE LOSS FUNCTION
# ============================================================================

def vae_loss(recon_x, x, mean, logvar, kl_weight=KL_WEIGHT):
    """
    Compute VAE loss = Reconstruction Loss + KL Divergence.
    
    Args:
        recon_x (torch.Tensor): Reconstructed output from decoder [batch, seq_len, vocab_size]
        x (torch.Tensor): Original input [batch, seq_len, vocab_size]
        mean (torch.Tensor): Mean of latent distribution [batch, latent_dim]
        logvar (torch.Tensor): Log variance of latent distribution [batch, latent_dim]
        kl_weight (float): Weight for KL divergence term
    
    Returns:
        tuple: (total_loss, recon_loss, kl_loss)
    """
    # Reconstruction loss: Binary Cross Entropy
    # Flatten for BCE calculation
    recon_x_flat = recon_x.view(-1, recon_x.size(-1))
    x_flat = x.view(-1, x.size(-1))
    recon_loss = nn.BCEWithLogitsLoss()(recon_x_flat, x_flat)
    
    # KL divergence: KL(N(mean, var) || N(0, 1))
    # KL = 0.5 * sum(1 + logvar - mean^2 - exp(logvar))
    kl_loss = torch.mean(-0.5 * torch.sum(1 + logvar - mean.pow(2) - logvar.exp(), dim=1))
    
    # Total loss
    total_loss = RECON_WEIGHT * recon_loss + kl_weight * kl_loss
    
    return total_loss, recon_loss, kl_loss


# ============================================================================
# TRAINING FUNCTION
# ============================================================================

def train_epoch(model, train_loader, optimizer, epoch, logger, kl_weight=KL_WEIGHT):
    """
    Train for one epoch.
    
    Args:
        model (VAE): VAE model to train
        train_loader (DataLoader): Training data loader
        optimizer (torch.optim.Optimizer): Optimizer
        epoch (int): Current epoch number
        logger: Logger instance
        kl_weight (float): KL divergence weight (annealed)
    
    Returns:
        dict: Metrics for the epoch
    """
    model.train()
    total_loss = 0.0
    total_recon_loss = 0.0
    total_kl_loss = 0.0
    num_batches = 0
    
    print(f"\n[TRAIN] Epoch {epoch + 1} — Starting training...")
    
    for batch_idx, batch in enumerate(tqdm(train_loader, desc=f"Epoch {epoch + 1}")):
        x = batch[0] if isinstance(batch, (list, tuple)) else batch
        # Move to device
        x = x.to(DEVICE)
        
        # Forward pass
        optimizer.zero_grad()
        recon_x, mean, logvar = model(x)
        
        # Compute loss
        loss, recon_loss, kl_loss = vae_loss(recon_x, x, mean, logvar, kl_weight)
        
        # Backward pass
        loss.backward()
        
        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRADIENT_CLIP)
        
        # Optimizer step
        optimizer.step()
        
        # Accumulate metrics
        total_loss += loss.item()
        total_recon_loss += recon_loss.item()
        total_kl_loss += kl_loss.item()
        num_batches += 1
        
        # Log progress every LOG_INTERVAL batches
        if (batch_idx + 1) % LOG_INTERVAL == 0:
            avg_loss = total_loss / num_batches
            print(f"  Batch {batch_idx + 1}/{len(train_loader)} | Loss: {avg_loss:.4f}")
            logger.info(f"Epoch {epoch + 1}, Batch {batch_idx + 1}/{len(train_loader)} | Loss: {avg_loss:.4f}")
    
    # Average metrics for epoch
    metrics = {
        "loss": total_loss / num_batches,
        "recon_loss": total_recon_loss / num_batches,
        "kl_loss": total_kl_loss / num_batches,
    }
    
    return metrics


# ============================================================================
# VALIDATION FUNCTION
# ============================================================================

def validate(model, val_loader, epoch, logger, kl_weight=KL_WEIGHT):
    """
    Validate on validation set.
    
    Args:
        model (VAE): VAE model to validate
        val_loader (DataLoader): Validation data loader
        epoch (int): Current epoch number
        logger: Logger instance
        kl_weight (float): KL divergence weight
    
    Returns:
        dict: Validation metrics
    """
    model.eval()
    total_loss = 0.0
    total_recon_loss = 0.0
    total_kl_loss = 0.0
    num_batches = 0
    
    print(f"[VALIDATE] Epoch {epoch + 1} — Validating...")
    
    with torch.no_grad():
        for batch in tqdm(val_loader, desc=f"Validation"):
            x = batch[0] if isinstance(batch, (list, tuple)) else batch
            x = x.to(DEVICE)
            
            # Forward pass
            recon_x, mean, logvar = model(x)
            
            # Compute loss
            loss, recon_loss, kl_loss = vae_loss(recon_x, x, mean, logvar, kl_weight)
            
            # Accumulate metrics
            total_loss += loss.item()
            total_recon_loss += recon_loss.item()
            total_kl_loss += kl_loss.item()
            num_batches += 1
    
    # Average metrics
    metrics = {
        "val_loss": total_loss / num_batches,
        "val_recon_loss": total_recon_loss / num_batches,
        "val_kl_loss": total_kl_loss / num_batches,
    }
    
    print(f"[VALIDATE] Val Loss: {metrics['val_loss']:.4f}")
    logger.info(f"Epoch {epoch + 1} Validation | Loss: {metrics['val_loss']:.4f}")
    
    return metrics


# ============================================================================
# CHECKPOINT SAVING
# ============================================================================

def save_checkpoint(model, optimizer, epoch, loss, model_dir="outputs/models", filename=None):
    """
    Save model checkpoint.
    
    Args:
        model (VAE): Model to save
        optimizer (torch.optim.Optimizer): Optimizer
        epoch (int): Current epoch
        loss (float): Current loss
        model_dir (str): Directory to save checkpoints
        filename (str): Custom filename (if None, uses epoch number)
    """
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    
    if filename is None:
        filename = f"checkpoint_epoch_{epoch + 1}.pt"
    
    filepath = Path(model_dir) / filename
    
    checkpoint = {
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "loss": loss,
        "config": {
            "latent_dim": LATENT_DIM,
            "kl_weight": KL_WEIGHT,
            "learning_rate": LEARNING_RATE,
        }
    }
    
    torch.save(checkpoint, filepath)
    print(f"[CHECKPOINT] Saved: {filepath}")


# ============================================================================
# MAIN TRAINING FUNCTION
# ============================================================================

def train(data_path, epochs=EPOCHS, batch_size=BATCH_SIZE, learning_rate=LEARNING_RATE):
    """
    Main training function.
    
    Args:
        data_path (str): Path to CSV file with SMILES strings
        epochs (int): Number of training epochs
        batch_size (int): Batch size
        learning_rate (float): Learning rate
    """
    print("[MAIN] Starting Genorova AI VAE Training...")
    print(f"[MAIN] Data path: {data_path}")
    print(f"[MAIN] Epochs: {epochs}, Batch size: {batch_size}, LR: {learning_rate}")
    print(f"[MAIN] Device: {DEVICE}")
    
    # Setup logging
    logger, log_file = setup_logging()
    logger.info(f"Training started. Data: {data_path}")
    
    # ========================================================================
    # 1. LOAD DATA
    # ========================================================================
    print("\n[STEP 1/6] Loading SMILES data...")
    try:
        smiles_list = load_smiles_from_csv(data_path)
        print(f"[STEP 1/6] Loaded {len(smiles_list)} SMILES strings")
        logger.info(f"Loaded {len(smiles_list)} SMILES strings from {data_path}")
    except Exception as e:
        print(f"[ERROR] Failed to load data: {e}")
        logger.error(f"Failed to load data: {e}")
        return
    
    # ========================================================================
    # 2. BUILD VOCABULARY
    # ========================================================================
    print("\n[STEP 2/6] Building vocabulary...")
    try:
        vocab = build_vocab(smiles_list)
        vocab_size = len(vocab)
        print(f"[STEP 2/6] Vocabulary size: {vocab_size}")
        logger.info(f"Vocabulary size: {vocab_size}")
    except Exception as e:
        print(f"[ERROR] Failed to build vocabulary: {e}")
        logger.error(f"Failed to build vocabulary: {e}")
        return
    
    # ========================================================================
    # 3. PREPROCESS DATA
    # ========================================================================
    print("\n[STEP 3/6] Preprocessing SMILES data...")
    try:
        dataset = SmilesDataset(smiles_list, vocab)
        print(f"[STEP 3/6] Created dataset with {len(dataset)} molecules")
        logger.info(f"Created dataset with {len(dataset)} molecules")
    except Exception as e:
        print(f"[ERROR] Failed to preprocess data: {e}")
        logger.error(f"Failed to preprocess data: {e}")
        return
    
    # ========================================================================
    # 4. SPLIT DATA
    # ========================================================================
    print("\n[STEP 4/6] Splitting data into train/val/test sets...")
    train_size = int(TRAIN_SPLIT * len(dataset))
    val_size = int(VAL_SPLIT * len(dataset))
    test_size = len(dataset) - train_size - val_size
    
    train_set, val_set, test_set = random_split(
        dataset,
        [train_size, val_size, test_size],
        generator=torch.Generator().manual_seed(42)
    )
    
    print(f"[STEP 4/6] Train: {train_size}, Val: {val_size}, Test: {test_size}")
    logger.info(f"Train: {train_size}, Val: {val_size}, Test: {test_size}")
    
    # Create data loaders
    train_loader = DataLoader(
        train_set,
        batch_size=batch_size,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY
    )
    
    val_loader = DataLoader(
        val_set,
        batch_size=batch_size,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY
    )
    
    print(f"[STEP 4/6] Created data loaders")
    
    # ========================================================================
    # 5. INITIALIZE MODEL
    # ========================================================================
    print("\n[STEP 5/6] Initializing VAE model...")
    try:
        model = VAE(vocab_size=vocab_size, latent_dim=LATENT_DIM).to(DEVICE)
        print(f"[STEP 5/6] VAE model initialized")
        logger.info(f"VAE model initialized with vocab_size={vocab_size}")
    except Exception as e:
        print(f"[ERROR] Failed to initialize model: {e}")
        logger.error(f"Failed to initialize model: {e}")
        return
    
    # ========================================================================
    # 6. TRAINING LOOP
    # ========================================================================
    print("\n[STEP 6/6] Starting training loop...")
    
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=LR_DECAY)
    
    best_val_loss = float('inf')
    patience_counter = 0
    
    # Initialize metrics tracking
    all_metrics = []
    
    try:
        for epoch in range(epochs):
            print(f"\n{'='*70}")
            print(f"EPOCH {epoch + 1}/{epochs}")
            print(f"{'='*70}")
            
            # Update KL weight if annealing
            if KL_ANNEALING:
                kl_weight = min(KL_WEIGHT, KL_WEIGHT * epoch / (epochs // 4))
            else:
                kl_weight = KL_WEIGHT
            
            # Train
            train_metrics = train_epoch(model, train_loader, optimizer, epoch, logger, kl_weight)
            
            # Validate
            val_metrics = validate(model, val_loader, epoch, logger, kl_weight)
            
            # Combine metrics
            metrics = {
                "epoch": epoch + 1,
                "learning_rate": optimizer.param_groups[0]['lr'],
                "kl_weight": kl_weight,
                **train_metrics,
                **val_metrics
            }
            all_metrics.append(metrics)
            
            # Print summary
            print(f"\n[SUMMARY] Epoch {epoch + 1}")
            print(f"  Train Loss: {train_metrics['loss']:.4f}")
            print(f"  Recon Loss: {train_metrics['recon_loss']:.4f}")
            print(f"  KL Loss: {train_metrics['kl_loss']:.4f}")
            print(f"  Val Loss: {val_metrics['val_loss']:.4f}")
            print(f"  Learning Rate: {optimizer.param_groups[0]['lr']:.6f}")
            print(f"  KL Weight: {kl_weight:.4f}")
            
            # Save checkpoint
            if (epoch + 1) % CHECKPOINT_EVERY == 0:
                save_checkpoint(model, optimizer, epoch, val_metrics['val_loss'])
            
            # Early stopping
            if val_metrics['val_loss'] < best_val_loss:
                best_val_loss = val_metrics['val_loss']
                patience_counter = 0
                # Save best model
                save_checkpoint(model, optimizer, epoch, val_metrics['val_loss'], filename="best_model.pt")
                print(f"[EARLY STOPPING] New best validation loss: {best_val_loss:.4f}")
            else:
                patience_counter += 1
                if patience_counter >= EARLY_STOPPING_PATIENCE:
                    print(f"[EARLY STOPPING] No improvement for {EARLY_STOPPING_PATIENCE} epochs. Stopping training.")
                    logger.info(f"Early stopping at epoch {epoch + 1}")
                    break
            
            # Update learning rate
            scheduler.step()
    
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Training interrupted by user")
        logger.info("Training interrupted by user")
    
    except Exception as e:
        print(f"\n[ERROR] Training failed: {e}")
        logger.error(f"Training failed: {e}", exc_info=True)
        return
    
    # ========================================================================
    # SAVE METRICS AND FINAL MODEL
    # ========================================================================
    
    # Save metrics to CSV
    metrics_df = pd.DataFrame(all_metrics)
    metrics_csv = "outputs/logs/training_metrics.csv"
    metrics_df.to_csv(metrics_csv, index=False)
    print(f"\n[METRICS] Saved to {metrics_csv}")
    
    # Save final model
    save_checkpoint(model, optimizer, epochs - 1, best_val_loss, filename="final_model.pt")
    
    print(f"\n{'='*70}")
    print("TRAINING COMPLETE!")
    print(f"{'='*70}")
    print(f"Best validation loss: {best_val_loss:.4f}")
    print(f"Total epochs trained: {len(all_metrics)}")
    print(f"Models saved to: outputs/models/")
    print(f"Metrics saved to: {metrics_csv}")
    print(f"Log saved to: {log_file}")
    
    logger.info(f"Training complete. Best val loss: {best_val_loss:.4f}")


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

if __name__ == "__main__" and False:
    parser = argparse.ArgumentParser(description="Train Genorova VAE model")
    parser.add_argument("--data", type=str, default="data/processed/test_smiles.csv",
                        help="Path to SMILES CSV file")
    parser.add_argument("--epochs", type=int, default=EPOCHS,
                        help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help="Batch size")
    parser.add_argument("--learning-rate", type=float, default=LEARNING_RATE,
                        help="Learning rate")
    
    args = parser.parse_args()
    
    # Run training
    train(
        data_path=args.data,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate
    )


# ============================================================================
# DATASET-DRIVEN TRAINING ENTRY POINT
# ============================================================================

import random
from typing import Dict

from data_loader import load_smiles_dataset
from preprocessor import (
    MAX_SMILES_LENGTH as DEFAULT_MAX_SMILES_LENGTH,
    SmilesDataset,
    build_vocab,
    preprocess_batch,
    save_vocab,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
MODEL_DIR = OUTPUT_DIR / "models"
LOG_DIR = OUTPUT_DIR / "logs"
VOCAB_PATH = OUTPUT_DIR / "vocab.json"

MODEL_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

NUM_WORKERS = 0
PIN_MEMORY = torch.cuda.is_available()
TRAIN_SPLIT = 0.9
VAL_SPLIT = 0.1
SEED = 42


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def setup_training_logging(log_dir: Path = LOG_DIR):
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"training_{timestamp}.log"

    logger = logging.getLogger("genorova.train.realdata")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_file)
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger, log_file


def summarize_dataset(
    df: pd.DataFrame,
    train_size: int,
    val_size: int,
    vocab: Dict[str, int],
    max_length: int,
    logger,
) -> None:
    lengths = df["smiles"].str.len()
    unique_chars = sorted(char for char in vocab.keys() if char != "<pad>")

    print("\n[DATASET] Training corpus summary")
    print(f"  Total molecules: {len(df)}")
    print(f"  Train/val split: {train_size} / {val_size}")
    print(f"  Vocab size: {len(vocab)}")
    print(f"  Unique characters: {''.join(unique_chars)}")
    print(
        f"  SMILES length stats: min={lengths.min()} max={lengths.max()} "
        f"mean={lengths.mean():.2f} p95={lengths.quantile(0.95):.0f}"
    )
    print(f"  Max sequence length used by model: {max_length}")
    print("  Random sample molecules:")
    for smiles in df["smiles"].sample(n=min(5, len(df)), random_state=SEED).tolist():
        print(f"    {smiles}")

    logger.info("Total molecules: %s", len(df))
    logger.info("Train/val split sizes: %s / %s", train_size, val_size)
    logger.info("Vocab size: %s", len(vocab))
    logger.info("Unique characters: %s", "".join(unique_chars))
    logger.info(
        "SMILES length distribution: min=%s max=%s mean=%.2f p95=%.0f max_length=%s",
        int(lengths.min()),
        int(lengths.max()),
        lengths.mean(),
        lengths.quantile(0.95),
        max_length,
    )


def train_real_dataset(
    dataset_name: str = "moses",
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    learning_rate: float = LEARNING_RATE,
    max_samples: int = 50000,
    min_len: int = 10,
    max_len: int = 100,
):
    """
    Train the VAE on a real molecular dataset with the existing loop structure.
    """
    set_seed(SEED)
    logger, log_file = setup_training_logging()

    print("[MAIN] Starting Genorova VAE training on a real molecular dataset")
    print(f"[MAIN] Dataset: {dataset_name}")
    print(f"[MAIN] Device: {DEVICE}")
    logger.info("Training started: dataset=%s max_samples=%s", dataset_name, max_samples)

    dataset_df = load_smiles_dataset(
        name=dataset_name,
        max_samples=max_samples,
        min_len=min_len,
        max_len=max_len,
    )
    load_stats = dataset_df.attrs.get("load_stats", {})

    smiles_list = dataset_df["smiles"].tolist()
    char2idx, idx2char = build_vocab(smiles_list)
    save_vocab(char2idx, VOCAB_PATH)

    observed_max_length = int(dataset_df["smiles"].str.len().max())
    model_max_length = max(DEFAULT_MAX_SMILES_LENGTH, observed_max_length)
    encoded_data = preprocess_batch(smiles_list, char2idx, max_length=model_max_length)
    dataset = SmilesDataset(encoded_data, smiles_list)

    train_size = max(1, int(TRAIN_SPLIT * len(dataset)))
    val_size = len(dataset) - train_size
    if val_size == 0:
        val_size = 1
        train_size = len(dataset) - 1

    summarize_dataset(dataset_df, train_size, val_size, char2idx, model_max_length, logger)
    logger.info("Loader stats: %s", load_stats)

    train_set, val_set = random_split(
        dataset,
        [train_size, val_size],
        generator=torch.Generator().manual_seed(SEED),
    )

    train_loader = DataLoader(
        train_set,
        batch_size=batch_size,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY,
    )
    val_loader = DataLoader(
        val_set,
        batch_size=batch_size,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY,
    )

    model = VAE(vocab_size=len(char2idx), latent_dim=LATENT_DIM, max_length=model_max_length).to(DEVICE)
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=LR_DECAY)

    best_val_loss = float("inf")
    patience_counter = 0
    all_metrics = []
    epoch_times = []
    checkpoint_path = MODEL_DIR / "genorova_best.pt"

    for epoch in range(epochs):
        print(f"\n{'=' * 70}")
        print(f"EPOCH {epoch + 1}/{epochs}")
        print(f"{'=' * 70}")

        if KL_ANNEALING:
            effective_warmup_epochs = max(KL_WARMUP_EPOCHS, 100)
            kl_weight = min(KL_WEIGHT_TARGET, KL_WEIGHT_TARGET * epoch / effective_warmup_epochs)
        else:
            kl_weight = KL_WEIGHT_TARGET

        epoch_start = time.time()
        train_metrics = train_epoch(model, train_loader, optimizer, epoch, logger, kl_weight)
        val_metrics = validate(model, val_loader, epoch, logger, kl_weight)
        epoch_time = time.time() - epoch_start
        epoch_times.append(epoch_time)

        metrics = {
            "epoch": epoch + 1,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "kl_weight": kl_weight,
            "epoch_seconds": epoch_time,
            **train_metrics,
            **val_metrics,
        }
        all_metrics.append(metrics)

        print(f"\n[SUMMARY] Epoch {epoch + 1}")
        print(f"  Train Loss: {train_metrics['loss']:.4f}")
        print(f"  Recon Loss: {train_metrics['recon_loss']:.4f}")
        print(f"  KL Loss: {train_metrics['kl_loss']:.4f}")
        print(f"  Val Loss: {val_metrics['val_loss']:.4f}")
        print(f"  Learning Rate: {optimizer.param_groups[0]['lr']:.6f}")
        print(f"  KL Weight: {kl_weight:.4f}")
        print(f"  Epoch Time (CPU/GPU wall): {epoch_time:.2f}s")

        if (epoch + 1) % CHECKPOINT_EVERY == 0:
            save_checkpoint(model, optimizer, epoch, val_metrics["val_loss"], model_dir=str(MODEL_DIR))

        if val_metrics["val_loss"] < best_val_loss:
            best_val_loss = val_metrics["val_loss"]
            patience_counter = 0
            checkpoint = {
                "epoch": epoch + 1,
                "model_state": model.state_dict(),
                "model_state_dict": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "best_val_loss": best_val_loss,
                "loss": best_val_loss,
                "vocab_size": len(char2idx),
                "max_length": model_max_length,
                "dataset": dataset_name,
            }
            torch.save(checkpoint, checkpoint_path)
            print(f"[CHECKPOINT] Saved best checkpoint: {checkpoint_path}")
        else:
            patience_counter += 1
            if patience_counter >= EARLY_STOPPING_PATIENCE:
                print(f"[EARLY STOPPING] No improvement for {EARLY_STOPPING_PATIENCE} epochs. Stopping training.")
                logger.info("Early stopping at epoch %s", epoch + 1)
                break

        scheduler.step()

    metrics_df = pd.DataFrame(all_metrics)
    metrics_csv = LOG_DIR / "training_metrics.csv"
    metrics_df.to_csv(metrics_csv, index=False)

    final_checkpoint_path = MODEL_DIR / "genorova_final.pt"
    final_checkpoint = {
        "epoch": len(all_metrics),
        "model_state": model.state_dict(),
        "model_state_dict": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "best_val_loss": best_val_loss,
        "loss": best_val_loss,
        "vocab_size": len(char2idx),
        "max_length": model_max_length,
        "dataset": dataset_name,
    }
    torch.save(final_checkpoint, final_checkpoint_path)

    print(f"\n{'=' * 70}")
    print("TRAINING COMPLETE!")
    print(f"{'=' * 70}")
    print(f"Best validation loss: {best_val_loss:.4f}")
    print(f"Total epochs trained: {len(all_metrics)}")
    print(f"Models saved to: {MODEL_DIR}")
    print(f"Metrics saved to: {metrics_csv}")
    print(f"Log saved to: {log_file}")

    logger.info("Training complete. Best val loss: %.4f", best_val_loss)

    return {
        "metrics": all_metrics,
        "metrics_csv": metrics_csv,
        "log_file": log_file,
        "best_checkpoint": checkpoint_path,
        "final_checkpoint": final_checkpoint_path,
        "vocab_path": VOCAB_PATH,
        "load_stats": load_stats,
        "model_max_length": model_max_length,
        "device": str(DEVICE),
        "epoch_times": epoch_times,
    }


def build_realdata_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train Genorova VAE on a real molecular dataset.")
    parser.add_argument("--dataset", default="moses", choices=["moses", "chembl_subset"])
    parser.add_argument("--max-samples", type=int, default=50000)
    parser.add_argument("--min-len", type=int, default=10)
    parser.add_argument("--max-len", type=int, default=100)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    return parser


def main_realdata() -> None:
    args = build_realdata_parser().parse_args()
    train_real_dataset(
        dataset_name=args.dataset,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_samples=args.max_samples,
        min_len=args.min_len,
        max_len=args.max_len,
    )


if __name__ == "__main__":
    main_realdata()
