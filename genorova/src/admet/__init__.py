"""ADMET scoring module — RDKit-only, fully offline."""
from .scorer import score_smiles, score_batch

__all__ = ["score_smiles", "score_batch"]
