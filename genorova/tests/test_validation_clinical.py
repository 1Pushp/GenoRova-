"""
Tests for validation/clinical/clinical_evaluator.py
=====================================================

Run from genorova/src/:
    python -m pytest ../tests/test_validation_clinical.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from validation.clinical.clinical_evaluator import run_clinical_evaluation

# ---------------------------------------------------------------------------
# Reusable mock upstream results (avoid running RDKit in every unit test)
# ---------------------------------------------------------------------------

def _make_chemistry(
    valid=True, sa_score=2.5, sa_flag="synthesizable",
    is_pains=False, novelty_flag="local_only_checked",
):
    return {
        "smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "valid_smiles": valid,
        "sa_score": sa_score,
        "sa_score_source": "rdkit_computed",
        "sa_flag": sa_flag,
        "is_pains": is_pains,
        "pains_matches": [],
        "pains_source": "rdkit_computed",
        "novelty": {
            "flag": novelty_flag,
            "found_in_local_db": False,
            "found_in_approved_drugs": False,
            "pubchem_cid": None,
            "pubchem_checked": False,
            "most_similar_drug": None,
            "max_tanimoto": None,
            "data_source": "local_db_lookup",
        },
        "passes_sanity": valid and not is_pains and sa_score <= 6.0,
        "rdkit_available": True,
        "notes": [],
    }


def _make_binding(score=-7.5, ref=-9.2, mode="scaffold_proxy"):
    delta = round(score - ref, 2) if (score is not None and ref is not None) else None
    return {
        "smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "target": "insulin_receptor",
        "reference_drug": "staurosporine",
        "docking_score": score,
        "reference_score": ref,
        "delta_vs_reference": delta,
        "key_h_bonds": [],
        "key_hydrophobic": [],
        "mode": mode,
        "confidence": "medium",
        "data_source": "heuristic_proxy",
        "interpretation": "Proxy score.",
        "rdkit_available": True,
        "notes": ["SCAFFOLD PROXY MODE"],
    }


def _make_admet(overall="likely_safe", dili="low", herg="low", cyp="low", safety_score=0.85):
    return {
        "smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "hepatotoxicity_risk": {"level": dili, "score": 0.1, "alerts": [], "method": "heuristic"},
        "herg_risk": {"level": herg, "score": 0.1, "alerts": [], "method": "heuristic"},
        "cyp_risk": {"level": cyp, "score": 0.2, "alerts": [], "method": "heuristic"},
        "overall_safety_flag": overall,
        "safety_score": safety_score,
        "disclaimer": "Heuristic proxy only.",
        "rdkit_available": True,
        "notes": [],
    }


SMILES = "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1"
VALID_DECISIONS = {"advance", "conditional_advance", "reject"}


class TestRunClinicalEvaluation:
    def test_returns_required_keys(self):
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "staurosporine",
            _make_chemistry(), _make_binding(), _make_admet(),
        )
        required = {
            "smiles", "target", "disease", "reference_drug",
            "decision", "decision_score", "explanation",
            "conditions", "rejection_reasons", "comparisons",
            "potency_vs_toxicity_note", "recommended_next_step",
        }
        assert required.issubset(result.keys())

    def test_decision_is_valid(self):
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "staurosporine",
            _make_chemistry(), _make_binding(), _make_admet(),
        )
        assert result["decision"] in VALID_DECISIONS

    def test_decision_score_0_to_1(self):
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "staurosporine",
            _make_chemistry(), _make_binding(), _make_admet(),
        )
        assert 0.0 <= result["decision_score"] <= 1.0

    def test_explanation_is_non_empty_string(self):
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "staurosporine",
            _make_chemistry(), _make_binding(), _make_admet(),
        )
        assert isinstance(result["explanation"], str)
        assert len(result["explanation"]) > 50

    def test_comparisons_is_list(self):
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "staurosporine",
            _make_chemistry(), _make_binding(), _make_admet(),
        )
        assert isinstance(result["comparisons"], list)
        assert len(result["comparisons"]) > 0

    def test_invalid_smiles_rejected(self):
        """A molecule with invalid SMILES should always be rejected."""
        result = run_clinical_evaluation(
            "not_valid", "insulin_receptor", "diabetes", "ref",
            _make_chemistry(valid=False), _make_binding(score=None), _make_admet(),
        )
        assert result["decision"] == "reject"

    def test_likely_unsafe_always_rejected(self):
        """A likely_unsafe safety flag should always produce a reject decision."""
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "ref",
            _make_chemistry(),
            _make_binding(),
            _make_admet(overall="likely_unsafe", dili="high", herg="high", safety_score=0.1),
        )
        assert result["decision"] == "reject"
        assert len(result["rejection_reasons"]) > 0

    def test_impractical_sa_rejected(self):
        """A molecule with SA > 6 should be rejected unless binding is exceptional."""
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "ref",
            _make_chemistry(sa_score=8.5, sa_flag="impractical"),
            _make_binding(score=-5.0),
            _make_admet(),
        )
        assert result["decision"] == "reject"

    def test_good_all_round_molecule_advances(self):
        """
        A molecule with good binding, clean safety, low SA, and novel flag
        should score high enough to advance or conditionally advance.
        """
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "staurosporine",
            _make_chemistry(sa_score=2.0, sa_flag="synthesizable",
                            novelty_flag="potentially_novel_patentable"),
            _make_binding(score=-8.5, ref=-9.2, mode="scaffold_proxy"),
            _make_admet(overall="likely_safe", dili="low", herg="low", cyp="low",
                        safety_score=0.90),
            qed_score=0.72,
            passes_lipinski=True,
        )
        assert result["decision"] in ("advance", "conditional_advance"), (
            f"Expected advance/conditional, got {result['decision']} "
            f"(score={result['decision_score']:.3f})"
        )

    def test_conditions_populated_for_conditional(self):
        """conditional_advance should have at least one condition."""
        # Force conditional by using borderline scores
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "ref",
            _make_chemistry(sa_score=3.5, sa_flag="synthesizable"),
            _make_binding(score=-5.5, ref=-9.2, mode="scaffold_proxy"),
            _make_admet(overall="caution", dili="medium", safety_score=0.60),
            qed_score=0.55,
            passes_lipinski=True,
        )
        if result["decision"] == "conditional_advance":
            assert len(result["conditions"]) > 0

    def test_potency_vs_toxicity_note_present(self):
        result = run_clinical_evaluation(
            SMILES, "insulin_receptor", "diabetes", "ref",
            _make_chemistry(), _make_binding(), _make_admet(),
        )
        assert isinstance(result["potency_vs_toxicity_note"], str)
        assert len(result["potency_vs_toxicity_note"]) > 10
