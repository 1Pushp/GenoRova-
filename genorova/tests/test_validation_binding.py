"""
Tests for validation/binding/target_binder.py
===============================================

Run from genorova/src/:
    python -m pytest ../tests/test_validation_binding.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from validation.binding.target_binder import run_binding_evaluation, KNOWN_TARGETS

ASPIRIN    = "CC(=O)Oc1ccccc1C(=O)O"
METFORMIN  = "CN(C)C(=N)NC(=N)N"
SITAGLIPTIN = "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F"
INVALID    = "not_a_smiles"


class TestRunBindingEvaluation:
    def test_returns_dict_with_required_keys(self):
        """All required fields must be present in the result."""
        result = run_binding_evaluation(ASPIRIN, "insulin_receptor")
        required = {
            "smiles", "target", "reference_drug",
            "docking_score", "reference_score", "delta_vs_reference",
            "key_h_bonds", "key_hydrophobic",
            "mode", "confidence", "data_source", "interpretation",
            "rdkit_available", "notes",
        }
        assert required.issubset(result.keys())

    def test_mode_is_valid(self):
        """Mode must be one of the three documented values."""
        result = run_binding_evaluation(ASPIRIN, "insulin_receptor")
        assert result["mode"] in ("real_docking", "scaffold_proxy", "unavailable")

    def test_confidence_is_valid(self):
        """Confidence must be one of the four documented values."""
        result = run_binding_evaluation(ASPIRIN, "insulin_receptor")
        assert result["confidence"] in ("high", "medium", "low", "none")

    def test_proxy_score_is_negative_or_none(self):
        """Proxy scores use a negative scale (more negative = better)."""
        result = run_binding_evaluation(ASPIRIN, "insulin_receptor")
        if result["docking_score"] is not None:
            assert result["docking_score"] < 0, (
                f"Docking/proxy score should be negative, got {result['docking_score']}"
            )

    def test_delta_computed_when_both_scores_present(self):
        """Delta must equal candidate_score - reference_score when both are available."""
        result = run_binding_evaluation(ASPIRIN, "insulin_receptor")
        if (result["docking_score"] is not None
                and result["reference_score"] is not None):
            expected_delta = round(result["docking_score"] - result["reference_score"], 2)
            assert abs(result["delta_vs_reference"] - expected_delta) < 0.01

    def test_known_target_gets_reference_score(self):
        """Targets in KNOWN_TARGETS should always have a reference score."""
        for target_key in list(KNOWN_TARGETS.keys())[:2]:  # test first two
            result = run_binding_evaluation(ASPIRIN, target_key)
            assert result["reference_score"] is not None, (
                f"reference_score should not be None for known target {target_key}"
            )

    def test_unknown_target_does_not_crash(self):
        """An unknown target name should fall back gracefully, not crash."""
        result = run_binding_evaluation(ASPIRIN, "unknown_protein_xyz")
        assert result["mode"] in ("real_docking", "scaffold_proxy", "unavailable")

    def test_invalid_smiles_handled(self):
        """An invalid SMILES should return a result, not an unhandled exception."""
        result = run_binding_evaluation(INVALID, "insulin_receptor")
        assert "mode" in result
        # docking_score may be None for invalid SMILES
        assert result["docking_score"] is None or isinstance(result["docking_score"], float)

    def test_notes_is_proxy_labelled(self):
        """When running in scaffold_proxy mode, notes should mention proxy."""
        result = run_binding_evaluation(ASPIRIN, "insulin_receptor")
        if result["mode"] == "scaffold_proxy":
            notes_text = " ".join(result["notes"]).upper()
            assert "PROXY" in notes_text, (
                "scaffold_proxy mode should include 'PROXY' in notes to warn caller"
            )

    def test_sitagliptin_on_dpp4(self):
        """Sitagliptin is the reference drug for DPP4 — delta should be near 0."""
        result = run_binding_evaluation(SITAGLIPTIN, "dpp4")
        if result["mode"] == "scaffold_proxy" and result["delta_vs_reference"] is not None:
            # Sitagliptin vs itself should give delta very close to 0
            assert abs(result["delta_vs_reference"]) < 1.0, (
                f"Sitagliptin vs DPP4 reference delta={result['delta_vs_reference']} "
                "should be near zero"
            )
