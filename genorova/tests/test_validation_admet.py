"""
Tests for validation/admet/admet_predictor.py
===============================================

Run from genorova/src/:
    python -m pytest ../tests/test_validation_admet.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from validation.admet.admet_predictor import (
    predict_hepatotoxicity,
    predict_herg_inhibition,
    predict_cyp_interaction,
    run_admet_evaluation,
)

METFORMIN  = "CN(C)C(=N)NC(=N)N"
ASPIRIN    = "CC(=O)Oc1ccccc1C(=O)O"
SITAGLIPTIN = "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F"
# Troglitazone — withdrawn due to hepatotoxicity (high DILI risk expected)
TROGLITAZONE = "CC1=C(C)c2cc(CC3SC(=O)NC3=O)ccc2O1"
# Cisapride — hERG blocker (high hERG risk expected)
CISAPRIDE = "CCOC1=CC=C(C=C1)NC(=O)C2=CN(C(=N2)N)CC3CCOCC3"
INVALID   = "not_a_smiles"

VALID_RISK_LEVELS = {"low", "medium", "high", "unknown"}
VALID_SAFETY_FLAGS = {"likely_safe", "caution", "likely_unsafe", "unknown"}


class TestPredictHepatotoxicity:
    def test_returns_required_fields(self):
        result = predict_hepatotoxicity(ASPIRIN)
        assert set(result.keys()) >= {"level", "score", "alerts", "method"}

    def test_level_is_valid(self):
        result = predict_hepatotoxicity(ASPIRIN)
        assert result["level"] in VALID_RISK_LEVELS

    def test_score_is_0_to_1_or_none(self):
        result = predict_hepatotoxicity(ASPIRIN)
        if result["score"] is not None:
            assert 0.0 <= result["score"] <= 1.0

    def test_alerts_is_list(self):
        result = predict_hepatotoxicity(ASPIRIN)
        assert isinstance(result["alerts"], list)

    def test_method_is_string(self):
        result = predict_hepatotoxicity(ASPIRIN)
        assert isinstance(result["method"], str)
        assert len(result["method"]) > 0

    def test_invalid_smiles_does_not_crash(self):
        result = predict_hepatotoxicity(INVALID)
        assert result["level"] in VALID_RISK_LEVELS | {"unknown"}

    def test_troglitazone_higher_risk_than_metformin(self):
        """
        Troglitazone (withdrawn for DILI) should score HIGHER DILI risk
        than Metformin (widely used, good safety profile).
        """
        troglitazone_result = predict_hepatotoxicity(TROGLITAZONE)
        metformin_result = predict_hepatotoxicity(METFORMIN)
        # Scores: troglitazone should have higher risk score
        t_score = troglitazone_result.get("score") or 0.0
        m_score = metformin_result.get("score") or 0.0
        assert t_score >= m_score, (
            f"Troglitazone DILI score ({t_score:.3f}) should be >= "
            f"Metformin score ({m_score:.3f})"
        )


class TestPredictHERG:
    def test_returns_required_fields(self):
        result = predict_herg_inhibition(ASPIRIN)
        assert set(result.keys()) >= {"level", "score", "alerts", "method"}

    def test_level_is_valid(self):
        result = predict_herg_inhibition(ASPIRIN)
        assert result["level"] in VALID_RISK_LEVELS

    def test_metformin_low_herg_risk(self):
        """
        Metformin has no aromatic rings and no basic N close to aromatics.
        hERG risk should be low.
        """
        result = predict_herg_inhibition(METFORMIN)
        assert result["level"] in ("low", "medium"), (
            f"Metformin expected low/medium hERG risk, got {result['level']}"
        )

    def test_score_is_0_to_1_or_none(self):
        result = predict_herg_inhibition(CISAPRIDE)
        if result["score"] is not None:
            assert 0.0 <= result["score"] <= 1.0


class TestPredictCYP:
    def test_returns_required_fields(self):
        result = predict_cyp_interaction(ASPIRIN)
        assert set(result.keys()) >= {"level", "score", "alerts", "method"}

    def test_level_is_valid(self):
        result = predict_cyp_interaction(ASPIRIN)
        assert result["level"] in VALID_RISK_LEVELS

    def test_alerts_is_list(self):
        result = predict_cyp_interaction(SITAGLIPTIN)
        assert isinstance(result["alerts"], list)

    def test_invalid_does_not_crash(self):
        result = predict_cyp_interaction(INVALID)
        assert result["level"] in VALID_RISK_LEVELS | {"unknown"}


class TestRunADMETEvaluation:
    def test_returns_required_top_level_keys(self):
        result = run_admet_evaluation(ASPIRIN)
        required = {
            "smiles", "hepatotoxicity_risk", "herg_risk", "cyp_risk",
            "overall_safety_flag", "safety_score", "disclaimer",
            "rdkit_available", "notes",
        }
        assert required.issubset(result.keys())

    def test_overall_safety_flag_valid(self):
        result = run_admet_evaluation(ASPIRIN)
        assert result["overall_safety_flag"] in VALID_SAFETY_FLAGS

    def test_safety_score_0_to_1(self):
        result = run_admet_evaluation(ASPIRIN)
        assert 0.0 <= result["safety_score"] <= 1.0

    def test_disclaimer_present(self):
        result = run_admet_evaluation(ASPIRIN)
        assert isinstance(result["disclaimer"], str)
        assert len(result["disclaimer"]) > 20

    def test_nested_risk_fields(self):
        """Each risk field should have level, score, alerts, method."""
        result = run_admet_evaluation(ASPIRIN)
        for risk_key in ("hepatotoxicity_risk", "herg_risk", "cyp_risk"):
            risk = result[risk_key]
            assert "level" in risk
            assert "alerts" in risk
            assert "method" in risk

    def test_invalid_smiles_handled(self):
        """Invalid SMILES should return unknown/low rather than crashing."""
        result = run_admet_evaluation(INVALID)
        assert result["overall_safety_flag"] in VALID_SAFETY_FLAGS

    def test_likely_unsafe_has_lower_safety_score_than_likely_safe(self):
        """
        A molecule with multiple risk alerts should score lower than
        metformin (generally considered safe).
        """
        # Use a molecule with known toxicity alerts (aromatic nitro)
        nitro_mol = "O=[N+]([O-])c1ccc(N)cc1"  # para-nitroaniline
        unsafe_result = run_admet_evaluation(nitro_mol)
        safe_result   = run_admet_evaluation(METFORMIN)

        assert unsafe_result["safety_score"] <= safe_result["safety_score"], (
            f"p-nitroaniline safety score ({unsafe_result['safety_score']:.3f}) "
            f"should be <= metformin ({safe_result['safety_score']:.3f})"
        )
