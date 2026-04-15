from __future__ import annotations

import logging

import pandas as pd

import genorova.src.train as train_module


def test_train_real_dataset_smoke(monkeypatch, project_temp_dir, null_logger):
    sample_df = pd.DataFrame(
        {
            "smiles": [
                "CCOCCNCCO",
                "CCN(CC)CCO",
                "CCOC(=O)N1CCCCC1",
                "CC1=CC=CC=C1O",
                "CCN1CCOCC1",
                "CCOC(=O)C1=CC=CC=C1",
            ]
        }
    )
    sample_df.attrs["load_stats"] = {"returned_rows": len(sample_df), "dataset": "test"}

    model_dir = project_temp_dir / "models"
    log_dir = project_temp_dir / "logs"
    vocab_path = project_temp_dir / "vocab.json"
    model_dir.mkdir()
    log_dir.mkdir()

    monkeypatch.setattr(train_module, "MODEL_DIR", model_dir)
    monkeypatch.setattr(train_module, "LOG_DIR", log_dir)
    monkeypatch.setattr(train_module, "VOCAB_PATH", vocab_path)
    monkeypatch.setattr(
        train_module,
        "load_smiles_dataset",
        lambda name, max_samples=None, min_len=10, max_len=100: sample_df.copy(),
    )

    def fake_setup_training_logging():
        return null_logger, log_dir / "training.log"

    monkeypatch.setattr(train_module, "setup_training_logging", fake_setup_training_logging)
    monkeypatch.setattr(
        train_module,
        "train_epoch",
        lambda model, train_loader, optimizer, epoch, logger, kl_weight: {
            "loss": 0.1,
            "recon_loss": 0.08,
            "kl_loss": 0.02,
        },
    )
    monkeypatch.setattr(
        train_module,
        "validate",
        lambda model, val_loader, epoch, logger, kl_weight: {
            "val_loss": 0.2,
        },
    )

    result = train_module.train_real_dataset(
        dataset_name="moses",
        epochs=1,
        batch_size=2,
        max_samples=6,
    )

    assert result["best_checkpoint"].exists()
    assert result["final_checkpoint"].exists()
    assert result["vocab_path"].exists()
