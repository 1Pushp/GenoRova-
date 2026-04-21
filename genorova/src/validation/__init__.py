"""
Genorova AI — Second-Stage Validation Pipeline
===============================================

This package provides four validation modules that evaluate generated
drug molecules against scientific criteria before they are reported as
candidates.

Quick start:
    from validation.pipeline import validate_molecule

    result = validate_molecule(
        smiles="Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        target="insulin_receptor",
        disease="diabetes",
    )
    print(result["final_decision"])
    print(result["summary"])

Modules:
    chemistry/sanitizer.py      — SA score, PAINS, novelty
    binding/target_binder.py    — Docking / scaffold proxy
    admet/admet_predictor.py    — DILI, hERG, CYP450
    clinical/clinical_evaluator.py — Decision engine
    pipeline.py                 — Orchestrator (use this)
    models.py                   — Pydantic v2 output schemas
"""

from validation.models import ValidationResult  # noqa: F401

__version__ = "2.0.0"
__all__ = ["validate_molecule", "validate_batch", "ValidationResult"]


def validate_molecule(*args, **kwargs):
    """Lazily import the pipeline entrypoint to avoid package import cycles."""
    from validation.pipeline import validate_molecule as _validate_molecule

    return _validate_molecule(*args, **kwargs)


def validate_batch(*args, **kwargs):
    """Lazily import the batch entrypoint to avoid package import cycles."""
    from validation.pipeline import validate_batch as _validate_batch

    return _validate_batch(*args, **kwargs)
