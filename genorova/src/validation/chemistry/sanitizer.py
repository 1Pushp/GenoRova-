"""
Genorova AI — Validation: Chemical Sanity Module
=================================================

PURPOSE:
Perform chemical sanity checks on a generated molecule before it advances
through the rest of the validation pipeline.

CHECKS PERFORMED:
1. Synthetic Accessibility (SA score) via RDKit sascorer
2. PAINS filtering via RDKit FilterCatalog (Pan-Assay Interference Compounds)
3. Novelty lookup — three layers:
      a. Local Genorova database (SQLite)
      b. Known approved-drug SMILES (exact match)
      c. PubChem REST API (optional, requires internet)
   Each layer is clearly labeled in the output.

HONESTY POLICY:
  - SA score is labelled "rdkit_computed" when RDKit is available and
    "heuristic_proxy" when the pure-Python fallback is used.
  - PAINS is labelled "rdkit_unavailable" if RDKit cannot be loaded, and
    the check is skipped with a note rather than returning a false negative.
  - Novelty flags are explicit about what was and was not checked.

PUBLIC API:
  run_chemistry_sanity(smiles, pubchem_lookup=False) -> ChemistryResult

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

from __future__ import annotations

import contextlib
import io
import re
import sqlite3
import warnings
from pathlib import Path
from typing import List, Optional, Tuple

warnings.filterwarnings("ignore")

# Resolve paths relative to the package root so this module can be imported
# from any working directory.
_SRC_DIR  = Path(__file__).resolve().parents[2]   # genorova/src/
_REPO_DIR = _SRC_DIR.parent                       # genorova/
_DB_PATH  = _REPO_DIR / "outputs" / "genorova_memory.db"

# ---------------------------------------------------------------------------
# Lazy RDKit loader (same pattern used throughout Genorova)
# ---------------------------------------------------------------------------

_RDKIT_LOADED       = None
_Chem               = None
_Descriptors        = None
_AllChem            = None
_DataStructs        = None
_FilterCatalog      = None
_FilterCatalogParams = None
_sascorer           = None


def _try_load_rdkit() -> bool:
    """
    Try to import RDKit exactly once.  Caches the result globally.
    Returns True if successful, False if RDKit is not available.
    """
    global _RDKIT_LOADED, _Chem, _Descriptors, _AllChem, _DataStructs
    global _FilterCatalog, _FilterCatalogParams, _sascorer

    if _RDKIT_LOADED is not None:
        return _RDKIT_LOADED

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            from rdkit import Chem as _c
            from rdkit.Chem import Descriptors as _d
            from rdkit.Chem import AllChem as _ac
            from rdkit.Chem import DataStructs as _ds
            from rdkit.Chem.FilterCatalog import FilterCatalog as _fc
            from rdkit.Chem.FilterCatalog import FilterCatalogParams as _fcp
            from rdkit import RDLogger as _rl
            _rl.DisableLog("rdApp.*")

        _Chem                = _c
        _Descriptors         = _d
        _AllChem             = _ac
        _DataStructs         = _ds
        _FilterCatalog       = _fc
        _FilterCatalogParams = _fcp

        # SA scorer is in RDKit Contrib — may not be present in all installs
        try:
            from rdkit.Contrib.SA_Score import sascorer as _sa
            _sascorer = _sa
        except ImportError:
            _sascorer = None   # will fall back to descriptor-based estimate

        _RDKIT_LOADED = True
        return True

    except Exception:
        _RDKIT_LOADED = False
        return False


# ---------------------------------------------------------------------------
# Known reference drugs (shared with scorer.py and validate.py)
# ---------------------------------------------------------------------------

REFERENCE_DRUGS: dict[str, str] = {
    "metformin":      "CN(C)C(=N)NC(=N)N",
    "sitagliptin":    "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
    "empagliflozin":  "OC[C@@H]1O[C@@H](c2ccc(Cl)cc2-c2ccc(OCC3CCOCC3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
    "glipizide":      "Cc1cnc(CN2C(=O)CCC2=O)s1",
    "aspirin":        "CC(=O)Oc1ccccc1C(=O)O",
    "paracetamol":    "CC(=O)Nc1ccc(O)cc1",
    "ibuprofen":      "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "caffeine":       "Cn1cnc2c1c(=O)n(c(=O)n2C)C",
}


# ---------------------------------------------------------------------------
# 1.  Synthetic Accessibility Score
# ---------------------------------------------------------------------------

def _sa_heuristic(smiles: str) -> float:
    """
    Pure-Python SA score approximation when RDKit is unavailable.
    Uses ring count and heavy-atom count as a rough proxy.
    Clearly labelled as heuristic in the returned ChemistryResult.
    """
    ring_digits = set(re.findall(r"\d", re.sub(r"%\d\d", "", smiles)))
    n_rings = len(ring_digits)
    n_heavy = sum(1 for ch in smiles if ch.isalpha() and ch not in "HhRr")
    sa = max(1.0, min(10.0, 1.5 + n_rings * 0.5 + n_heavy * 0.04))
    return round(sa, 2)


def calculate_sa_score(smiles: str) -> Tuple[float, str]:
    """
    Calculate the Synthetic Accessibility score for a SMILES string.

    Returns a tuple (score, source) where:
      score  -- float in [1, 10], lower = easier to synthesise
      source -- "rdkit_computed" | "rdkit_descriptors_proxy" | "heuristic_proxy"

    1–4  : synthesizable
    4–6  : difficult but feasible
    >6   : impractical for most labs
    """
    print(f"   [SA] Calculating SA score for {smiles[:50]}...")

    if not _try_load_rdkit():
        score = _sa_heuristic(smiles)
        print(f"   [SA] RDKit unavailable — heuristic SA = {score:.2f}")
        return score, "heuristic_proxy"

    mol = _Chem.MolFromSmiles(smiles)
    if mol is None:
        print("   [SA] Invalid SMILES — returning worst-case SA = 10.0")
        return 10.0, "rdkit_computed"

    # Prefer the official sascorer
    if _sascorer is not None:
        try:
            score = float(_sascorer.calculateScore(mol))
            print(f"   [SA] sascorer SA = {score:.2f}")
            return round(score, 2), "rdkit_computed"
        except Exception as e:
            print(f"   [SA] sascorer failed ({e}), falling back to descriptor proxy")

    # Descriptor-based proxy (still RDKit, but less accurate than sascorer)
    num_atoms  = mol.GetNumAtoms()
    num_rings  = _Descriptors.RingCount(mol)
    num_stereo = len(_Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    num_hetero = _Descriptors.NumHeteroatoms(mol)
    complexity = (
        0.2 * min(num_atoms, 30)
        + 0.5 * min(num_rings, 5)
        + 0.3 * min(num_stereo, 5)
        + 0.1 * min(num_hetero, 10)
    )
    score = round(max(1.0, min(10.0, 1.0 + complexity)), 2)
    print(f"   [SA] descriptor-proxy SA = {score:.2f}")
    return score, "rdkit_descriptors_proxy"


def _sa_flag(score: float) -> str:
    """Convert numeric SA score to a categorical flag."""
    if score <= 4.0:
        return "synthesizable"
    if score <= 6.0:
        return "difficult"
    return "impractical"


# ---------------------------------------------------------------------------
# 2.  PAINS Filtering
# ---------------------------------------------------------------------------

def check_pains(smiles: str) -> Tuple[bool, List[dict], str]:
    """
    Check whether a molecule matches any PAINS structural alerts.

    Returns:
      is_pains  -- True if one or more alerts match
      matches   -- list of dicts with keys 'alert_name' and 'description'
      source    -- "rdkit_computed" | "rdkit_unavailable"

    PAINS (Pan-Assay Interference Compounds) are substructures known to
    produce false positives in many biochemical assays.  A PAINS hit does
    NOT automatically disqualify a molecule, but it flags it for scrutiny.
    """
    print(f"   [PAINS] Checking {smiles[:50]}...")

    if not _try_load_rdkit():
        print("   [PAINS] RDKit unavailable — skipping PAINS check")
        return False, [], "rdkit_unavailable"

    mol = _Chem.MolFromSmiles(smiles)
    if mol is None:
        print("   [PAINS] Invalid SMILES")
        return False, [], "rdkit_computed"

    try:
        params = _FilterCatalogParams()
        params.AddCatalog(_FilterCatalogParams.FilterCatalogs.PAINS)
        catalog = _FilterCatalog(params)

        matches = []
        entry = catalog.GetFirstMatch(mol)
        if entry is not None:
            # Collect ALL matches, not just the first
            all_entries = catalog.GetMatches(mol)
            for e in all_entries:
                matches.append({
                    "alert_name":  e.GetDescription(),
                    "description": (
                        "Pan-Assay Interference Compound structural alert. "
                        "May produce false positives in biochemical assays."
                    ),
                })

        is_pains = len(matches) > 0
        if is_pains:
            print(f"   [PAINS] ALERT: {len(matches)} match(es): "
                  f"{', '.join(m['alert_name'] for m in matches)}")
        else:
            print("   [PAINS] No PAINS alerts matched.")
        return is_pains, matches, "rdkit_computed"

    except Exception as e:
        print(f"   [PAINS] Error during PAINS check: {e}")
        return False, [], "rdkit_computed"


# ---------------------------------------------------------------------------
# 3.  Novelty Lookup
# ---------------------------------------------------------------------------

def _tanimoto_vs_approved(smiles: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Compute maximum Tanimoto similarity (Morgan FP radius 2, 2048 bits)
    between the query molecule and each known reference drug.

    Returns (max_similarity, drug_name) or (None, None) on failure.
    """
    if not _try_load_rdkit():
        return None, None

    mol = _Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, None

    try:
        fp_query = _AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        best_sim = 0.0
        best_name = None

        for drug_name, drug_smiles in REFERENCE_DRUGS.items():
            drug_mol = _Chem.MolFromSmiles(drug_smiles)
            if drug_mol is None:
                continue
            fp_drug = _AllChem.GetMorganFingerprintAsBitVect(drug_mol, 2, nBits=2048)
            sim = _DataStructs.TanimotoSimilarity(fp_query, fp_drug)
            if sim > best_sim:
                best_sim = sim
                best_name = drug_name

        return (round(best_sim, 4), best_name) if best_name else (None, None)

    except Exception:
        return None, None


def _check_pubchem(smiles: str, timeout: int = 10) -> Tuple[Optional[int], bool]:
    """
    Query PubChem PUG REST API to check if this SMILES is already known.

    Returns:
      (cid, checked) where:
        cid     -- PubChem Compound ID if found, None if not found
        checked -- True if the API was actually queried, False on error/skip
    """
    try:
        import requests  # noqa: PLC0415
        url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/cids/JSON"
        response = requests.post(
            url,
            data={"smiles": smiles},
            timeout=timeout,
        )
        if response.status_code == 200:
            data = response.json()
            cids = data.get("IdentifierList", {}).get("CID", [])
            cid = int(cids[0]) if cids else None
            print(f"   [Novelty/PubChem] CID={cid} (found={cid is not None})")
            return cid, True
        elif response.status_code == 404:
            # 404 = not found in PubChem — genuinely novel at PubChem level
            print("   [Novelty/PubChem] Not found in PubChem (404)")
            return None, True
        else:
            print(f"   [Novelty/PubChem] Unexpected status {response.status_code}")
            return None, False

    except Exception as e:
        print(f"   [Novelty/PubChem] Request failed: {e}")
        return None, False


def _check_local_db(smiles: str, db_path: Path = _DB_PATH) -> bool:
    """
    Check if the exact SMILES string exists in the Genorova SQLite database.
    Returns True if found (= already generated before), False otherwise.
    """
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM molecules WHERE smiles = ?", (smiles,))
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def check_novelty(
    smiles: str,
    pubchem_lookup: bool = False,
) -> dict:
    """
    Determine novelty status of a molecule across three layers:
      1. Exact match in approved reference drugs
      2. Exact match in local Genorova database
      3. PubChem REST API lookup (only if pubchem_lookup=True)

    Also computes Tanimoto similarity to reference drugs to detect close
    analogues that should be classified as repurposing leads.

    Returns a dict compatible with NoveltyStatus fields.
    """
    print(f"   [Novelty] Checking novelty for {smiles[:50]}...")

    # Layer 1: exact match in approved drugs
    in_approved = smiles in REFERENCE_DRUGS.values()
    if in_approved:
        print("   [Novelty] Exact match in approved drug list.")

    # Layer 2: exact match in local DB
    in_local_db = _check_local_db(smiles)
    if in_local_db:
        print("   [Novelty] Found in local Genorova database.")

    # Tanimoto similarity to reference drugs
    max_tanimoto, most_similar = _tanimoto_vs_approved(smiles)

    # Layer 3: PubChem (optional)
    pubchem_cid, pubchem_checked = (None, False)
    if pubchem_lookup:
        pubchem_cid, pubchem_checked = _check_pubchem(smiles)
    else:
        print("   [Novelty] PubChem lookup skipped (pubchem_lookup=False).")

    # --- Determine flag ---
    # "unrealistic": very short SMILES (< 5 chars) = probably not a real drug lead
    if len(smiles.strip()) < 5:
        flag = "unrealistic"

    elif in_approved or in_local_db:
        flag = "known_repurposing_lead"

    elif pubchem_checked and pubchem_cid is not None:
        # Found in PubChem → known compound, useful as repurposing lead
        flag = "known_repurposing_lead"

    elif max_tanimoto is not None and max_tanimoto >= 0.85:
        # Very high similarity to a known drug → likely a close analogue
        flag = "known_repurposing_lead"

    elif not pubchem_checked:
        # We didn't actually check PubChem; be honest about uncertainty
        flag = "local_only_checked"

    else:
        # Not found locally and not found in PubChem
        flag = "potentially_novel_patentable"

    # Data source label
    if pubchem_checked:
        data_source = "pubchem_lookup"
    elif in_local_db:
        data_source = "local_db_lookup"
    else:
        data_source = "local_db_lookup"

    print(f"   [Novelty] Flag: {flag}  |  Max Tanimoto: {max_tanimoto}")

    return {
        "flag":                   flag,
        "found_in_local_db":      in_local_db,
        "found_in_approved_drugs": in_approved,
        "pubchem_cid":            pubchem_cid,
        "pubchem_checked":        pubchem_checked,
        "most_similar_drug":      most_similar,
        "max_tanimoto":           max_tanimoto,
        "data_source":            data_source,
    }


# ---------------------------------------------------------------------------
# 4.  Main entry point
# ---------------------------------------------------------------------------

def run_chemistry_sanity(
    smiles: str,
    pubchem_lookup: bool = False,
) -> dict:
    """
    Run all chemical sanity checks and return a dict compatible with
    ChemistryResult.  Callers can either use the raw dict or cast it:

        from genorova.src.validation.models import ChemistryResult
        result = ChemistryResult(**run_chemistry_sanity(smiles))

    Args:
        smiles         -- SMILES string to evaluate
        pubchem_lookup -- if True, query PubChem REST API (needs internet)

    Returns:
        dict with keys matching ChemistryResult fields
    """
    print(f"\n[ChemistrySanity] Starting for: {smiles[:60]}...")
    rdkit_ok = _try_load_rdkit()

    notes: List[str] = []

    # --- Validate SMILES first ---
    valid = False
    if rdkit_ok:
        mol = _Chem.MolFromSmiles(smiles)
        valid = mol is not None
    else:
        # Very rough check: at least one letter present
        valid = bool(re.search(r"[A-Za-z]", smiles))
        notes.append("RDKit unavailable — SMILES validity is approximate.")

    if not valid:
        notes.append("SMILES could not be parsed. All downstream checks skipped.")
        # Return a minimal failing result without running expensive checks
        return {
            "smiles":         smiles,
            "valid_smiles":   False,
            "sa_score":       None,
            "sa_score_source": "rdkit_computed" if rdkit_ok else "heuristic_proxy",
            "sa_flag":        "impractical",
            "is_pains":       False,
            "pains_matches":  [],
            "pains_source":   "rdkit_computed" if rdkit_ok else "rdkit_unavailable",
            "novelty": {
                "flag":                    "unrealistic",
                "found_in_local_db":       False,
                "found_in_approved_drugs": False,
                "pubchem_cid":             None,
                "pubchem_checked":         False,
                "most_similar_drug":       None,
                "max_tanimoto":            None,
                "data_source":             "local_db_lookup",
            },
            "passes_sanity":  False,
            "rdkit_available": rdkit_ok,
            "notes":          notes,
        }

    # --- SA Score ---
    sa_score, sa_source = calculate_sa_score(smiles)
    sa_flag_val = _sa_flag(sa_score)

    # --- PAINS ---
    is_pains, pains_raw, pains_src = check_pains(smiles)
    pains_matches = [
        {"alert_name": m["alert_name"], "description": m["description"]}
        for m in pains_raw
    ]
    if not rdkit_ok:
        notes.append(
            "RDKit unavailable — PAINS check was skipped. "
            "is_pains=False does NOT confirm the molecule is PAINS-clean."
        )

    # --- Novelty ---
    novelty_dict = check_novelty(smiles, pubchem_lookup=pubchem_lookup)

    # --- Passes sanity? ---
    # A molecule passes chemical sanity if:
    #   1. SMILES is valid
    #   2. Not a PAINS hit (or PAINS check was unavailable — give benefit of doubt)
    #   3. SA score is not impractical (> 6)
    pains_ok = (not is_pains) or (pains_src == "rdkit_unavailable")
    sa_ok    = sa_score is not None and sa_score <= 6.0
    passes   = valid and pains_ok and sa_ok

    if is_pains:
        notes.append(
            f"PAINS alert(s) detected: "
            + ", ".join(m["alert_name"] for m in pains_matches)
            + ". This molecule may cause assay interference."
        )
    if sa_flag_val == "impractical":
        notes.append(
            f"SA score {sa_score:.1f} > 6.0 — synthesis is likely impractical "
            "for most medicinal chemistry labs."
        )

    result = {
        "smiles":          smiles,
        "valid_smiles":    valid,
        "sa_score":        sa_score,
        "sa_score_source": sa_source,
        "sa_flag":         sa_flag_val,
        "is_pains":        is_pains,
        "pains_matches":   pains_matches,
        "pains_source":    pains_src,
        "novelty":         novelty_dict,
        "passes_sanity":   passes,
        "rdkit_available": rdkit_ok,
        "notes":           notes,
    }

    print(f"[ChemistrySanity] Done. SA={sa_score}, PAINS={is_pains}, "
          f"novelty={novelty_dict['flag']}, passes={passes}")
    return result


# ---------------------------------------------------------------------------
# Example usage (run this file directly to test)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_molecules = {
        "Metformin (known drug)":       "CN(C)C(=N)NC(=N)N",
        "Aspirin":                      "CC(=O)Oc1ccccc1C(=O)O",
        "Sitagliptin":                  "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
        "Simple novel fragment":        "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "PAINS example (rhodanine)":    "O=C1CSC(=S)N1",
    }

    for name, smiles in test_molecules.items():
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        result = run_chemistry_sanity(smiles, pubchem_lookup=False)
        print(f"  valid={result['valid_smiles']}, SA={result['sa_score']} "
              f"({result['sa_flag']}), PAINS={result['is_pains']}, "
              f"novelty={result['novelty']['flag']}, passes={result['passes_sanity']}")
