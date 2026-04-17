"""
End-to-end tests for validation/pipeline.py
============================================

These tests run the full four-stage pipeline against a handful of real
molecules.  They verify that:
  - The pipeline does not crash
  - All output fields are present
  - Results are consistent across stages
  - Proxy/real modes are correctly labelled
  - The five core questions are answered as expected booleans or None

Run from genorova/src/:
    python -m pytest ../tests/test_validation_pipeline.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from validation.pipeline import validate_molecule, validate_batch

# ---------------------------------------------------------------------------
# Test molecules
# ---------------------------------------------------------------------------

METFORMIN   = "CN(C)C(=N)NC(=N)N"
ASPIRIN     = "CC(=O)Oc1ccccc1C(=O)O"
SITAGLIPTIN = "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F"
SIMPLE_FRAG = "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1"
INVALID     = "xyz_not_valid_###"

VALID_DECISIONS = {"advance", "conditional_advance", "reject"}


class TestValidateMolecule:
    """End-to-end tests for the single-molecule pipeline."""

    def test_does_not_crash_on_valid_smiles(self):
        """Pipeline must complete without exceptions for a valid molecule."""
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        assert result is not None
        assert isinstance(result, dict)

    def test_all_top_level_keys_present(self):
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        required = {
            "smiles", "target", "disease", "reference_drug",
            "chemistry", "binding", "admet", "clinical",
            "final_decision", "summary",
            "can_be_synthesized", "likely_novel",
            "binds_well_vs_standard", "likely_safe_to_investigate",
            "clinically_worth_pursuing",
            "pipeline_version",
        }
        assert required.issubset(result.keys())

    def test_final_decision_is_valid(self):
        result = validate_molecule(SIMPLE_FRAG, target="insulin_receptor", disease="diabetes")
        assert result["final_decision"] in VALID_DECISIONS

    def test_summary_is_non_empty_string(self):
        result = validate_molecule(ASPIRIN, target="dpp4", disease="diabetes")
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 80

    def test_five_questions_are_bool_or_none(self):
        """Each core question must be True, False, or None — never a string."""
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        for key in (
            "can_be_synthesized", "likely_novel",
            "binds_well_vs_standard", "likely_safe_to_investigate",
            "clinically_worth_pursuing",
        ):
            val = result[key]
            assert val is None or isinstance(val, bool), (
                f"{key} should be bool or None, got {type(val).__name__}={val!r}"
            )

    def test_final_decision_matches_clinical_decision(self):
        """final_decision must mirror clinical.decision exactly."""
        result = validate_molecule(SIMPLE_FRAG, target="insulin_receptor", disease="diabetes")
        assert result["final_decision"] == result["clinical"]["decision"]

    def test_chemistry_stage_present(self):
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        chem = result["chemistry"]
        assert "valid_smiles" in chem
        assert "sa_score" in chem
        assert "is_pains" in chem
        assert "novelty" in chem

    def test_binding_stage_present(self):
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        bind = result["binding"]
        assert "mode" in bind
        assert "confidence" in bind
        assert "data_source" in bind

    def test_admet_stage_present(self):
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        admet = result["admet"]
        assert "hepatotoxicity_risk" in admet
        assert "herg_risk" in admet
        assert "cyp_risk" in admet
        assert "overall_safety_flag" in admet

    def test_clinical_stage_present(self):
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        clin = result["clinical"]
        assert "decision" in clin
        assert "decision_score" in clin
        assert "explanation" in clin

    def test_binding_mode_is_labelled(self):
        """Binding mode must never be an empty string."""
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        assert result["binding"]["mode"] in ("real_docking", "scaffold_proxy", "unavailable")

    def test_invalid_smiles_always_rejected(self):
        """An invalid SMILES should produce a reject decision."""
        result = validate_molecule(INVALID, target="insulin_receptor", disease="diabetes")
        # The chemistry stage should mark valid_smiles=False
        assert result["chemistry"]["valid_smiles"] is False
        # Clinical decision should be reject
        assert result["final_decision"] == "reject"

    def test_pipeline_version_present(self):
        result = validate_molecule(ASPIRIN, target="insulin_receptor", disease="diabetes")
        assert result["pipeline_version"] == "2.0"

    def test_metformin_known_drug_novelty(self):
        """Metformin is a known approved drug — should not be flagged as novel."""
        result = validate_molecule(METFORMIN, target="insulin_receptor", disease="diabetes")
        novelty_flag = result["chemistry"]["novelty"]["flag"]
        assert novelty_flag in ("known_repurposing_lead",), (
            f"Metformin should be 'known_repurposing_lead', got '{novelty_flag}'"
        )
        assert result["likely_novel"] is False

    def test_proxy_scores_never_labelled_as_real_docking(self):
        """
        Unless AutoDock Vina actually ran successfully, mode must not be
        'real_docking'.  This guards against hardcoded results.
        """
        result = validate_molecule(SIMPLE_FRAG, target="insulin_receptor", disease="diabetes")
        bind = result["binding"]
        if bind["mode"] == "real_docking":
            # If real docking ran, data_source must say real_docking
            assert bind["data_source"] == "real_docking"
        else:
            # If proxy, notes must contain a warning
            notes_text = " ".join(bind.get("notes", [])).upper()
            assert "PROXY" in notes_text or bind["mode"] == "unavailable"

    def test_different_targets(self):
        """Pipeline should handle multiple known targets without crashing."""
        for target in ("dpp4", "glut4", "ace2"):
            result = validate_molecule(ASPIRIN, target=target, disease="diabetes")
            assert result["final_decision"] in VALID_DECISIONS

    def test_diabetes_vs_infection_disease(self):
        """Disease parameter should not crash the pipeline."""
        for disease in ("diabetes", "infection"):
            result = validate_molecule(ASPIRIN, target="insulin_receptor", disease=disease)
            assert result is not None


class TestValidateBatch:
    """Tests for the batch pipeline function."""

    def test_returns_list(self):
        results = validate_batch([ASPIRIN, METFORMIN], target="insulin_receptor")
        assert isinstance(results, list)
        assert len(results) == 2

    def test_sorted_by_decision_score_descending(self):
        """Results should be sorted best-first."""
        results = validate_batch([ASPIRIN, METFORMIN, SIMPLE_FRAG], target="insulin_receptor")
        scores = [r["clinical"]["decision_score"] for r in results]
        assert scores == sorted(scores, reverse=True), (
            f"Batch results not sorted descending: {scores}"
        )

    def test_empty_list_returns_empty(self):
        results = validate_batch([], target="insulin_receptor")
        assert results == []

    def test_handles_mixed_valid_invalid(self):
        """Batch with one invalid SMILES should not crash."""
        results = validate_batch([ASPIRIN, INVALID], target="insulin_receptor")
        assert len(results) == 2
        # Invalid SMILES result should be rejected
        invalid_result = next(r for r in results if r["chemistry"]["valid_smiles"] is False)
        assert invalid_result["final_decision"] == "reject"
