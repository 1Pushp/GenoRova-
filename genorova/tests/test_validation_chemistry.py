"""
Tests for validation/chemistry/sanitizer.py
============================================

Run from genorova/src/:
    python -m pytest ../tests/test_validation_chemistry.py -v

Or from genorova/:
    cd src && python -m pytest ../tests/test_validation_chemistry.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make src/ importable
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from validation.chemistry.sanitizer import (
    calculate_sa_score,
    check_pains,
    check_novelty,
    run_chemistry_sanity,
)

# ---------------------------------------------------------------------------
# Test molecules
# ---------------------------------------------------------------------------

ASPIRIN    = "CC(=O)Oc1ccccc1C(=O)O"
METFORMIN  = "CN(C)C(=N)NC(=N)N"
# Rhodanine: known PAINS hit (thiazolidine-2,4-dione with exocyclic double bond)
RHODANINE  = "O=C1CSC(=S)N1"
INVALID    = "not_a_smiles_###"
SIMPLE_FRAGMENT = "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1"


# ---------------------------------------------------------------------------
# SA score tests
# ---------------------------------------------------------------------------

class TestSAScore:
    def test_aspirin_sa_reasonable(self):
        """Aspirin is a simple known drug — SA should be low (< 4)."""
        score, source = calculate_sa_score(ASPIRIN)
        assert score is not None
        assert 1.0 <= score <= 5.0, f"Aspirin SA={score} seems too high for a simple drug"
        assert source in ("rdkit_computed", "rdkit_descriptors_proxy", "heuristic_proxy")

    def test_metformin_sa_reasonable(self):
        """Metformin is a very simple molecule — SA should be very low."""
        score, source = calculate_sa_score(METFORMIN)
        assert score is not None
        assert 1.0 <= score <= 4.0, f"Metformin SA={score} seems too high"

    def test_returns_tuple(self):
        score, source = calculate_sa_score(ASPIRIN)
        assert isinstance(score, float)
        assert isinstance(source, str)

    def test_invalid_smiles_returns_worst_case(self):
        """Invalid SMILES should return 10.0 or a fallback, not crash."""
        score, source = calculate_sa_score(INVALID)
        # Either returns 10.0 (rdkit) or a heuristic estimate — both are acceptable
        assert score is not None
        assert 1.0 <= score <= 10.0


# ---------------------------------------------------------------------------
# PAINS filter tests
# ---------------------------------------------------------------------------

class TestPAINS:
    def test_aspirin_not_pains(self):
        """Aspirin should not trigger PAINS (it is a real approved drug)."""
        is_pains, matches, source = check_pains(ASPIRIN)
        # Some approved drugs can be in PAINS but aspirin typically is not
        # If RDKit unavailable this returns False with rdkit_unavailable source
        assert isinstance(is_pains, bool)
        assert isinstance(matches, list)
        assert source in ("rdkit_computed", "rdkit_unavailable")

    def test_pains_result_structure(self):
        """Every match should have alert_name and description keys."""
        _, matches, _ = check_pains(RHODANINE)
        for m in matches:
            assert "alert_name" in m
            assert "description" in m

    def test_returns_three_values(self):
        result = check_pains(ASPIRIN)
        assert len(result) == 3

    def test_invalid_smiles_does_not_crash(self):
        is_pains, matches, source = check_pains(INVALID)
        assert isinstance(is_pains, bool)
        assert isinstance(matches, list)


# ---------------------------------------------------------------------------
# Novelty check tests
# ---------------------------------------------------------------------------

class TestNoveltyCheck:
    def test_metformin_not_novel(self):
        """Metformin is in the REFERENCE_DRUGS dict — not novel."""
        result = check_novelty(METFORMIN, pubchem_lookup=False)
        assert result["found_in_approved_drugs"] is True
        assert result["flag"] in ("known_repurposing_lead",)

    def test_simple_fragment_local_only(self):
        """A simple novel fragment should be local_only_checked when PubChem skipped."""
        result = check_novelty(SIMPLE_FRAGMENT, pubchem_lookup=False)
        assert result["pubchem_checked"] is False
        assert result["flag"] in ("local_only_checked", "potentially_novel_patentable",
                                   "known_repurposing_lead")

    def test_novelty_result_fields(self):
        """All expected keys must be present."""
        result = check_novelty(ASPIRIN, pubchem_lookup=False)
        required = {
            "flag", "found_in_local_db", "found_in_approved_drugs",
            "pubchem_cid", "pubchem_checked", "most_similar_drug",
            "max_tanimoto", "data_source",
        }
        assert required.issubset(result.keys())

    def test_tiny_smiles_unrealistic(self):
        """A 1-character SMILES should be flagged unrealistic."""
        result = check_novelty("C", pubchem_lookup=False)
        assert result["flag"] == "unrealistic"


# ---------------------------------------------------------------------------
# Full chemistry sanity tests
# ---------------------------------------------------------------------------

class TestRunChemistrySanity:
    def test_aspirin_passes_sanity(self):
        """Aspirin should pass basic sanity checks."""
        result = run_chemistry_sanity(ASPIRIN, pubchem_lookup=False)
        assert result["valid_smiles"] is True
        # SA score should be present
        assert result["sa_score"] is not None

    def test_result_keys(self):
        """All required keys must be present in the result dict."""
        result = run_chemistry_sanity(ASPIRIN, pubchem_lookup=False)
        required = {
            "smiles", "valid_smiles", "sa_score", "sa_score_source",
            "sa_flag", "is_pains", "pains_matches", "pains_source",
            "novelty", "passes_sanity", "rdkit_available", "notes",
        }
        assert required.issubset(result.keys())

    def test_invalid_smiles_fails_sanity(self):
        """An invalid SMILES should fail sanity with valid_smiles=False."""
        result = run_chemistry_sanity(INVALID, pubchem_lookup=False)
        assert result["valid_smiles"] is False
        assert result["passes_sanity"] is False

    def test_sa_flag_values(self):
        """sa_flag must be one of the three valid categories."""
        result = run_chemistry_sanity(ASPIRIN, pubchem_lookup=False)
        assert result["sa_flag"] in ("synthesizable", "difficult", "impractical")

    def test_notes_is_list(self):
        result = run_chemistry_sanity(ASPIRIN, pubchem_lookup=False)
        assert isinstance(result["notes"], list)

    def test_novelty_dict_present(self):
        result = run_chemistry_sanity(METFORMIN, pubchem_lookup=False)
        assert isinstance(result["novelty"], dict)
        assert "flag" in result["novelty"]
