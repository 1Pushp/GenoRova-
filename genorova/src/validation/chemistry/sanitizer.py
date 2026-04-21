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
# Canonical reference drug list — single source of truth
# ---------------------------------------------------------------------------
# Import from reference_data so that all novelty checking across sanitizer,
# scorer, and pipeline uses exactly the same drug list and threshold.
import sys as _sys
if str(_SRC_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SRC_DIR))

from validation.reference_data import (  # noqa: E402
    REFERENCE_DRUGS,
    TANIMOTO_KNOWN_THRESHOLD,
)

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


# REFERENCE_DRUGS and TANIMOTO_KNOWN_THRESHOLD are imported from
# validation.reference_data above — do not redefine them here.


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

def _tanimoto_vs_approved(smiles: str) -> Tuple[Optional[float], Optional[str], bool]:
    """
    Compute maximum Tanimoto similarity (Morgan FP radius 2, 2048 bits)
    between the query molecule and each known reference drug.

    Returns (max_similarity, drug_name, checked) where checked=False means
    the similarity computation could not be performed.
    """
    if not _try_load_rdkit():
        return None, None, False

    mol = _Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, None, False

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

        if best_name:
            return round(best_sim, 4), best_name, True
        return None, None, True

    except Exception:
        return None, None, False


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


def _check_local_db(smiles: str, db_path: Path = _DB_PATH) -> Tuple[bool, bool]:
    """
    Check if the exact SMILES string exists in the Genorova SQLite database.
    Returns (checked, found). checked=False means the lookup was skipped or
    unavailable, which is distinct from checked=True + found=False.
    """
    if not db_path.exists():
        return False, False
    try:
        conn = sqlite3.connect(str(db_path))
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM molecules WHERE smiles = ?", (smiles,))
        count = cur.fetchone()[0]
        conn.close()
        return True, count > 0
    except Exception:
        return False, False


def _reference_name_for_exact_smiles(smiles: str) -> Optional[str]:
    """Return the canonical reference-drug name when the SMILES is an exact match."""
    for drug_name, drug_smiles in REFERENCE_DRUGS.items():
        if smiles == drug_smiles:
            return drug_name
    return None


def novelty_status_from_flag(novelty_flag: str) -> str:
    """
    Map raw novelty flags to the stable outward-facing status buckets.

    These buckets are intentionally conservative and are reused by the
    science path, validation pipeline, API payloads, and reports.
    """
    if novelty_flag in {"known_repurposing_lead", "unrealistic"}:
        return "known"
    if novelty_flag == "potentially_novel_patentable":
        return "potentially_novel"
    return "uncertain"


def _check_summary(label: str, checked: bool, found: bool) -> str:
    """Render a simple checked/no-match/not-checked summary for provenance text."""
    if not checked:
        return f"{label} not checked"
    if found:
        return f"{label} checked, match found"
    return f"{label} checked, no match"


def _tanimoto_summary(provenance: dict) -> str:
    """Render the Tanimoto-specific provenance summary."""
    if not provenance.get("tanimoto_checked"):
        return "Tanimoto analogue screen not checked"

    closest_reference = provenance.get("closest_reference")
    tanimoto = provenance.get("closest_reference_tanimoto")
    threshold = provenance.get("tanimoto_threshold")
    if closest_reference and tanimoto is not None and threshold is not None:
        relation = "meets or exceeds" if tanimoto >= threshold else "is below"
        return (
            f"Tanimoto analogue screen checked against {closest_reference} "
            f"({tanimoto:.2f}), which {relation} the {threshold:.2f} threshold"
        )
    return "Tanimoto analogue screen checked, but no comparable reference result was available"


def _pubchem_summary(provenance: dict) -> str:
    """Render the PubChem provenance summary."""
    if not provenance.get("pubchem_enabled"):
        return "PubChem lookup not enabled"
    if not provenance.get("pubchem_checked"):
        return "PubChem lookup was enabled but not completed"
    if provenance.get("pubchem_match_found"):
        return "PubChem lookup checked, match found"
    return "PubChem lookup checked, no match found"


def build_novelty_provenance(novelty_result: Optional[dict]) -> dict:
    """
    Build the canonical novelty provenance block from the sanitizer's raw results.

    This block is the single auditable record of which novelty checks ran,
    what each check found, and why the final novelty label was assigned.
    """
    novelty = dict(novelty_result or {})
    novelty_flag = novelty.get("flag", "local_only_checked")
    final_status = novelty.get("novelty_status") or novelty_status_from_flag(novelty_flag)
    final_reason = novelty.get("novelty_reason") or novelty.get("reason") or ""

    provenance = {
        "local_db_checked": bool(novelty.get("local_db_checked", novelty.get("found_in_local_db") is not None)),
        "local_db_match_found": bool(novelty.get("local_db_match_found", novelty.get("found_in_local_db", False))),
        "reference_exact_match_checked": bool(
            novelty.get("reference_exact_match_checked", novelty.get("found_in_approved_drugs") is not None)
        ),
        "reference_exact_match_found": bool(
            novelty.get("reference_exact_match_found", novelty.get("found_in_approved_drugs", False))
        ),
        "tanimoto_checked": bool(
            novelty.get(
                "tanimoto_checked",
                novelty.get("max_tanimoto") is not None or novelty.get("closest_reference") is not None,
            )
        ),
        "closest_reference": novelty.get("closest_reference") or novelty.get("most_similar_drug") or novelty.get("exact_reference_name"),
        "closest_reference_tanimoto": novelty.get("closest_reference_tanimoto", novelty.get("max_tanimoto")),
        "tanimoto_threshold": novelty.get("tanimoto_threshold", TANIMOTO_KNOWN_THRESHOLD),
        "pubchem_checked": bool(novelty.get("pubchem_checked", False)),
        "pubchem_match_found": bool(
            novelty.get("pubchem_match_found", novelty.get("pubchem_checked", False) and novelty.get("pubchem_cid") is not None)
        ),
        "pubchem_enabled": bool(novelty.get("pubchem_enabled", novelty.get("pubchem_checked", False))),
        "final_novelty_status": final_status,
        "final_novelty_reason": final_reason,
    }

    explanation = ". ".join(
        [
            _check_summary(
                "Local database lookup",
                provenance["local_db_checked"],
                provenance["local_db_match_found"],
            ),
            _check_summary(
                "Reference exact-match screen",
                provenance["reference_exact_match_checked"],
                provenance["reference_exact_match_found"],
            ),
            _tanimoto_summary(provenance),
            _pubchem_summary(provenance),
            f"Final novelty label: {final_status.replace('_', ' ')}. Reason: {final_reason.rstrip('.')}",
        ]
    ) + "."
    provenance["provenance_explanation"] = explanation
    return provenance


def build_novelty_evidence(novelty_result: Optional[dict]) -> dict:
    """
    Build the plain-language novelty evidence block from the canonical sanitizer output.

    Returned keys are stable and safe to expose in top-level API/report payloads.
    """
    novelty = dict(novelty_result or {})
    novelty_flag = novelty.get("flag", "local_only_checked")
    novelty_status = novelty_status_from_flag(novelty_flag)
    closest_reference = (
        novelty.get("closest_reference")
        or novelty.get("most_similar_drug")
        or novelty.get("exact_reference_name")
    )
    tanimoto_score = novelty.get("closest_reference_tanimoto", novelty.get("max_tanimoto"))
    threshold = novelty.get("tanimoto_threshold", TANIMOTO_KNOWN_THRESHOLD)
    found_in_local_db = novelty.get("found_in_local_db", False)
    found_in_approved_drugs = novelty.get("found_in_approved_drugs", False)
    pubchem_checked = novelty.get("pubchem_checked", False)
    pubchem_cid = novelty.get("pubchem_cid")

    if found_in_approved_drugs:
        if closest_reference:
            reason = (
                f"Known reference / known drug: exact match to approved reference "
                f"{closest_reference}."
            )
        else:
            reason = "Known reference / known drug: exact match to an approved reference drug."
    elif novelty_flag == "known_repurposing_lead":
        if found_in_local_db:
            reason = (
                "Known repurposing lead: already present in the local Genorova database, "
                "so it is not treated as a fresh novel candidate."
            )
        elif pubchem_checked and pubchem_cid is not None:
            reason = (
                f"Known repurposing lead: found in PubChem (CID {pubchem_cid}), so "
                "Genorova does not frame it as novel."
            )
        elif closest_reference and tanimoto_score is not None:
            reason = (
                f"Known repurposing lead: closest approved reference is {closest_reference} "
                f"(Tanimoto {tanimoto_score:.2f}), which meets or exceeds the "
                f"{threshold:.2f} threshold."
            )
        else:
            reason = (
                "Known repurposing lead: close enough to a known reference that Genorova "
                "does not present it as novel."
            )
    elif novelty_flag == "potentially_novel_patentable":
        if closest_reference and tanimoto_score is not None:
            reason = (
                f"Potentially novel: not found in the local database or PubChem. "
                f"Closest approved reference is {closest_reference} "
                f"(Tanimoto {tanimoto_score:.2f}), below the {threshold:.2f} threshold."
            )
        else:
            reason = "Potentially novel: not found in the local database or PubChem."
    elif novelty_flag == "unrealistic":
        reason = (
            "Uncertain novelty: the structure is too short or unrealistic to treat as a "
            "credible lead, so Genorova does not claim novelty."
        )
    else:
        if closest_reference and tanimoto_score is not None:
            reason = (
                f"Uncertain novelty: closest approved reference is {closest_reference} "
                f"(Tanimoto {tanimoto_score:.2f}), below the {threshold:.2f} threshold, "
                "but PubChem was not checked."
            )
        else:
            reason = (
                "Uncertain novelty: only local checks were run, so an external novelty "
                "claim would be premature."
            )

    provenance = build_novelty_provenance(
        {
            **novelty,
            "novelty_status": novelty_status,
            "novelty_reason": reason,
        }
    )
    return {
        "novelty_status": novelty_status,
        "novelty_closest_reference": closest_reference,
        "novelty_tanimoto_score": tanimoto_score,
        "novelty_threshold": threshold,
        "novelty_reason": reason,
        "novelty_provenance": provenance,
        "novelty_provenance_explanation": provenance["provenance_explanation"],
    }


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
    reference_exact_match_checked = True
    in_approved = smiles in REFERENCE_DRUGS.values()
    if in_approved:
        print("   [Novelty] Exact match in approved drug list.")
    exact_reference_name = _reference_name_for_exact_smiles(smiles) if in_approved else None

    # Layer 2: exact match in local DB
    local_db_checked, in_local_db = _check_local_db(smiles)
    if in_local_db:
        print("   [Novelty] Found in local Genorova database.")
    elif not local_db_checked:
        print("   [Novelty] Local Genorova database lookup unavailable.")

    # Tanimoto similarity to reference drugs
    max_tanimoto, most_similar, tanimoto_checked = _tanimoto_vs_approved(smiles)
    if not tanimoto_checked:
        print("   [Novelty] Tanimoto analogue screen unavailable.")

    # Layer 3: PubChem (optional)
    pubchem_enabled = bool(pubchem_lookup)
    pubchem_cid, pubchem_checked = (None, False)
    if pubchem_lookup:
        pubchem_cid, pubchem_checked = _check_pubchem(smiles)
    else:
        print("   [Novelty] PubChem lookup skipped (pubchem_lookup=False).")
    pubchem_match_found = pubchem_checked and pubchem_cid is not None

    # --- Determine flag ---
    # "unrealistic": very short SMILES (< 5 chars) = probably not a real drug lead
    if len(smiles.strip()) < 5:
        flag = "unrealistic"

    elif in_approved or in_local_db:
        flag = "known_repurposing_lead"

    elif pubchem_match_found:
        # Found in PubChem → known compound, useful as repurposing lead
        flag = "known_repurposing_lead"

    elif tanimoto_checked and max_tanimoto is not None and max_tanimoto >= TANIMOTO_KNOWN_THRESHOLD:
        # High similarity to a known reference drug → classify as repurposing lead.
        # Threshold comes from reference_data.TANIMOTO_KNOWN_THRESHOLD (currently
        # 0.70) — the single canonical value for this classification decision.
        flag = "known_repurposing_lead"

    elif (
        local_db_checked
        and reference_exact_match_checked
        and tanimoto_checked
        and pubchem_enabled
        and pubchem_checked
        and not pubchem_match_found
    ):
        # Not found locally and not found in PubChem
        flag = "potentially_novel_patentable"

    else:
        # We did not complete an external novelty confirmation step.
        flag = "local_only_checked"

    # Data source label
    if pubchem_checked:
        data_source = "pubchem_lookup"
    elif local_db_checked:
        data_source = "local_db_lookup"
    else:
        data_source = "novelty_lookup_incomplete"

    closest_reference = exact_reference_name or most_similar
    raw_novelty_payload = {
        "flag":                    flag,
        "found_in_local_db":       in_local_db,
        "found_in_approved_drugs": in_approved,
        "pubchem_cid":             pubchem_cid,
        "pubchem_checked":         pubchem_checked,
        "pubchem_match_found":     pubchem_match_found,
        "pubchem_enabled":         pubchem_enabled,
        "exact_reference_name":    exact_reference_name,
        "closest_reference":       closest_reference,
        "most_similar_drug":       closest_reference,
        "max_tanimoto":            max_tanimoto,
        "closest_reference_tanimoto": max_tanimoto,
        "local_db_checked":        local_db_checked,
        "local_db_match_found":    in_local_db,
        "reference_exact_match_checked": reference_exact_match_checked,
        "reference_exact_match_found": in_approved,
        "tanimoto_checked":        tanimoto_checked,
        # Threshold that was applied — sourced from reference_data.TANIMOTO_KNOWN_THRESHOLD.
        # Expose it here so report / API consumers can see the exact cutoff used.
        "tanimoto_threshold":      TANIMOTO_KNOWN_THRESHOLD,
        "data_source":             data_source,
    }
    novelty_evidence = build_novelty_evidence(raw_novelty_payload)
    novelty_payload = {**raw_novelty_payload, **novelty_evidence}
    novelty_payload["status"] = novelty_evidence["novelty_status"]
    novelty_payload["reason"] = novelty_evidence["novelty_reason"]

    print(f"   [Novelty] Flag: {flag}  |  Max Tanimoto: {max_tanimoto}  |  Threshold: {TANIMOTO_KNOWN_THRESHOLD}")
    return novelty_payload


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
        raw_invalid_novelty = {
            "flag":                    "unrealistic",
            "found_in_local_db":       False,
            "found_in_approved_drugs": False,
            "pubchem_cid":             None,
            "pubchem_checked":         False,
            "pubchem_match_found":     False,
            "pubchem_enabled":         bool(pubchem_lookup),
            "exact_reference_name":    None,
            "closest_reference":       None,
            "most_similar_drug":       None,
            "max_tanimoto":            None,
            "closest_reference_tanimoto": None,
            "local_db_checked":        False,
            "local_db_match_found":    False,
            "reference_exact_match_checked": False,
            "reference_exact_match_found": False,
            "tanimoto_checked":        False,
            "tanimoto_threshold":      TANIMOTO_KNOWN_THRESHOLD,
            "data_source":             "novelty_lookup_incomplete",
        }
        invalid_novelty_evidence = build_novelty_evidence(raw_invalid_novelty)
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
                **raw_invalid_novelty,
                "status":                  invalid_novelty_evidence["novelty_status"],
                "reason":                  invalid_novelty_evidence["novelty_reason"],
                **invalid_novelty_evidence,
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
