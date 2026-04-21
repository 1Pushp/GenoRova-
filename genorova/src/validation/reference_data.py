"""
Genorova AI — Canonical Reference Data
=======================================

PURPOSE:
Single source of truth for:
  - KNOWN_TARGETS    : supported protein targets with PDB IDs, reference drugs,
                       literature binding energies, and disease associations.
  - DISEASE_TARGET_MAP: maps each target key → expected disease label so the
                        pipeline can warn when a caller passes a mismatched pair.
  - REFERENCE_DRUGS  : SMILES for known approved drugs used in novelty checking
                       and Tanimoto comparisons.
  - CANONICAL_TARGET / CANONICAL_DISEASE: the single primary narrative path
                       used by default throughout reports and generation.

WHY THIS FILE EXISTS:
Before Day 11, KNOWN_TARGETS was defined independently in target_binder.py and
reference SMILES were duplicated in sanitizer.py and scorer.py.  Any update to
one copy did not propagate to the others.  This file eliminates that drift.

IMPORTANT:
  known_binding_kcal_mol values are from published crystallography / ITC data
  and are used ONLY as reference benchmarks, NOT as model outputs.
  Sources are cited in docs/scientific_limitations.md.

AUTHOR: Claude Code (Pushp Dwivedi)
DATE:   April 2026
"""

from __future__ import annotations

from typing import Dict

# ---------------------------------------------------------------------------
# Canonical narrative path
# ---------------------------------------------------------------------------
# All default reports, API defaults, and generation evaluation should use
# bacterial carbonic anhydrase (bCA) / acetazolamide / infection unless explicitly overridden.
#
# Rationale: acetazolamide's binding to bacterial CA is crystal-structure validated
# (PDB 3CYU) with published Ki=6.4 nM, making it the most scientifically defensible anchor.
# DPP4 / sitagliptin remains in KNOWN_TARGETS for legacy reference but is no longer active.

CANONICAL_TARGET  = "bca"
CANONICAL_DISEASE = "infection"


# ---------------------------------------------------------------------------
# Target database
# ---------------------------------------------------------------------------

KNOWN_TARGETS: Dict[str, Dict] = {
    "bca": {
        "pdb_id":                 "3CYU",
        "description":            "Bacterial carbonic anhydrase (H. pylori HpCA) — antibacterial target",
        "disease":                "infection",
        "reference_drug":         "acetazolamide",
        "reference_smiles":       "CC(=O)Nc1nnc(s1)S(N)(=O)=O",
        "known_binding_kcal_mol": -11.2,    # from published Ki = 6.4 nM (ΔG ≈ RT·ln Ki)
        "ki_nm":                  6.4,      # experimentally measured Ki, nM
        "binding_box": {
            "center": [18.0, 22.0, 14.0],
            "size":   [18.0, 18.0, 18.0],
        },
    },
    "insulin_receptor": {
        "pdb_id":                 "1IR3",
        "description":            "Insulin receptor kinase domain (diabetes)",
        "disease":                "diabetes",
        "reference_drug":         "staurosporine",
        "reference_smiles":       "CC1C2CC3C(C1OC(=O)C4=CC=CN=C4)N(C)C5=C3C2=C6C(=C5)C(=O)NC6=O",
        "known_binding_kcal_mol": -9.2,     # approximate literature value
        "binding_box": {
            "center": [15.5, 25.3, 12.8],
            "size":   [20.0, 20.0, 20.0],
        },
    },
    "dpp4": {
        "pdb_id":                 "1NNY",
        "description":            "Dipeptidyl peptidase-4 (DPP4), sitagliptin target",
        "disease":                "diabetes",
        "reference_drug":         "sitagliptin",
        "reference_smiles":       "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
        "known_binding_kcal_mol": -8.1,
        "binding_box": {
            "center": [21.0, 37.0, 53.0],
            "size":   [22.0, 22.0, 22.0],
        },
    },
    "glut4": {
        "pdb_id":                 "6THA",
        "description":            "GLUT4 glucose transporter (diabetes)",
        "disease":                "diabetes",
        "reference_drug":         "cytochalasin_b",
        "reference_smiles":       "CC1CCC(CC1)C2CC(=O)O[C@@H]3CC(=C)C=C4C(=O)NCC(=C4)O3",
        "known_binding_kcal_mol": -7.5,
        "binding_box": {
            "center": [12.0, 18.0, 30.0],
            "size":   [20.0, 20.0, 20.0],
        },
    },
    "ace2": {
        "pdb_id":                 "6M0J",
        "description":            "ACE2 receptor (COVID-19 / infectious disease)",
        "disease":                "infection",
        "reference_drug":         "MLN-4760",
        "reference_smiles":       "OC(=O)CN1C(=O)[C@@H](CC2=CC=CC=C2)[C@@H](O)CN[C@@H](CC3=CC=CC=C3)[C@@H]1O",
        "known_binding_kcal_mol": -8.8,
        "binding_box": {
            "center": [20.0, 30.0, 40.0],
            "size":   [24.0, 24.0, 24.0],
        },
    },
    "hiv_protease": {
        "pdb_id":                 "3OXC",
        "description":            "HIV-1 protease (infectious disease)",
        "disease":                "infection",
        "reference_drug":         "lopinavir",
        "reference_smiles":       "CC1=CC(=C(C=C1)C2=CC=CC=C2)NC(=O)C[C@@H](CC3=CC=CC=C3)NC(=O)[C@H](CC(C)C)NC(=O)C4=CN=CC=C4",
        "known_binding_kcal_mol": -9.5,
        "binding_box": {
            "center": [10.0, 20.0, 15.0],
            "size":   [18.0, 18.0, 18.0],
        },
    },
}

# ---------------------------------------------------------------------------
# Disease → target set mapping (for validation)
# ---------------------------------------------------------------------------

DISEASE_TARGET_MAP: Dict[str, set] = {
    "diabetes":  {"insulin_receptor", "dpp4", "glut4"},
    "infection": {"ace2", "hiv_protease", "bca"},
}

# Reverse lookup: target → expected disease
TARGET_DISEASE_MAP: Dict[str, str] = {
    target_key: info["disease"]
    for target_key, info in KNOWN_TARGETS.items()
}


def validate_disease_target_pair(target: str, disease: str) -> list:
    """
    Check that the target and disease are scientifically consistent.

    Returns a list of warning strings (empty = no issues).
    Does NOT raise — callers decide whether to treat warnings as errors.

    Examples:
        validate_disease_target_pair("dpp4", "diabetes")      → []
        validate_disease_target_pair("ace2", "diabetes")      → [warning]
        validate_disease_target_pair("unknown_target", "diabetes") → [warning]
    """
    warnings = []
    target_key = target.lower().replace("-", "_").replace(" ", "_")

    if target_key not in KNOWN_TARGETS:
        warnings.append(
            f"Target '{target}' is not in KNOWN_TARGETS. "
            "Binding evaluation will use a generic property proxy with no target anchor."
        )
        return warnings  # can't check disease consistency for unknown targets

    expected_disease = TARGET_DISEASE_MAP.get(target_key)
    if expected_disease and expected_disease != disease.lower():
        warnings.append(
            f"Disease-target mismatch: target '{target}' is associated with "
            f"'{expected_disease}' but disease was set to '{disease}'. "
            "Clinical scoring weights will reflect the declared disease, which may "
            "not match the target's biological context. "
            "Consider using target='{canonical_for_disease}' or correcting the disease label."
            .replace(
                "{canonical_for_disease}",
                next(
                    (k for k, v in KNOWN_TARGETS.items() if v["disease"] == disease.lower()),
                    CANONICAL_TARGET,
                )
            )
        )

    return warnings


# ---------------------------------------------------------------------------
# Approved reference drugs (novelty checking + Tanimoto comparisons)
# ---------------------------------------------------------------------------
# These SMILES are the single canonical copy used by sanitizer.py, scorer.py,
# and any other module that needs to compare against known drugs.
# When adding a new reference drug, add it here only.

REFERENCE_DRUGS: Dict[str, str] = {
    # Diabetes — primary disease program
    "metformin":       "CN(C)C(=N)NC(=N)N",
    "sitagliptin":     "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
    "empagliflozin":   "OC[C@@H]1O[C@@H](c2ccc(Cl)cc2-c2ccc(OCC3CCOCC3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
    "glipizide":       "Cc1cnc(CN2C(=O)CCC2=O)s1",
    "semaglutide_core":"CC(C)(C)NCC(=O)N1CCC[C@H]1C(=O)N",
    "linagliptin":     "CN1C=NC2=C1C(=O)N(C(=O)N2CC3=CC=CC(=C3)F)C4CCCCC4",

    # Bacterial carbonic anhydrase — primary active program
    "acetazolamide":   "CC(=O)Nc1nnc(s1)S(N)(=O)=O",   # Ki=6.4 nM vs H. pylori bCA (PDB 3CYU)

    # Infection / cardiovascular
    "lopinavir":       "CC1=CC(=C(C=C1)C2=CC=CC=C2)NC(=O)C[C@@H](CC3=CC=CC=C3)NC(=O)[C@H](CC(C)C)NC(=O)C4=CN=CC=C4",
    "remdesivir":      "CCC(CC)COC(=O)[C@@H](N[P@@](=O)(OC[C@H]1O[C@@H]([C@@H]([C@@H]1O)O)n2cnc3c(N)ncnc23)Oc4ccccc4)C",
    "azithromycin":    "CC[C@@H]1[C@@]([C@@H]([C@H](N(C)[C@@H]1[C@@H](C[C@@H](CC=O)OC)O)C)O[C@H]2C[C@@]([C@H]([C@@H](O2)C)OC3C[C@@H]([C@H]([C@@H](O3)C)N(C)C)O)(C)OC)(C)O",

    # Common reference compounds for novelty sanity checks.
    # A generated molecule is NOT novel if it is merely aspirin, paracetamol,
    # ibuprofen, or caffeine. These were present in the historical local copies
    # in sanitizer.py and scorer.py; they are now consolidated here so all
    # novelty checks share one list.
    "aspirin":         "CC(=O)Oc1ccccc1C(=O)O",
    "paracetamol":     "CC(=O)Nc1ccc(O)cc1",
    "ibuprofen":       "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "caffeine":        "Cn1cnc2c1c(=O)n(c(=O)n2C)C",
}

# Tanimoto similarity threshold above which a generated molecule is considered
# a "known repurposing lead" rather than truly novel.
TANIMOTO_KNOWN_THRESHOLD = 0.70   # conservative: flag anything ≥ 70% similar

# Delta vs reference threshold (kcal/mol) for real docking:
# A candidate must be within this many kcal/mol of the reference to be considered
# "comparable". Used consistently by target_binder and pipeline.
ACCEPTABLE_DELTA_VS_REFERENCE = 1.0   # candidate can be up to 1.0 kcal/mol worse
BETTER_THAN_REFERENCE_DELTA   = -1.0  # candidate is better if delta ≤ this value
