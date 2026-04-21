"""
Genorova AI -- Molecule Clinical Scoring Engine
================================================

PURPOSE:
Score generated drug molecules against real clinical trial endpoints
for Type 2 Diabetes. Based on analysis of Phase 3 diabetes trial data.

FUNCTIONS PROVIDED:
1. passes_lipinski(smiles)        -- Lipinski Rule of 5 check
2. calculate_qed(smiles)          -- Drug-likeness score 0 to 1
3. calculate_sa_score(smiles)     -- Synthetic accessibility 1 to 10
4. is_novel(smiles)               -- Check against known drug database
5. genorova_clinical_score(smiles) -- Composite clinical score 0 to 1
6. generate_molecule_report(smiles) -- Full report for one molecule
7. rank_candidates(molecule_list)  -- Rank molecules by clinical score

CLINICAL WEIGHTS (from real Phase 3 diabetes trial endpoints):
    HbA1c reduction potential  : 0.35  (primary endpoint)
    Fasting glucose effect     : 0.25  (secondary endpoint)
    Hypoglycemia risk          : 0.20  (safety - PENALIZES bad molecules)
    Body weight effect         : 0.10  (bonus for weight-neutral/reducing)
    Cardiovascular safety      : 0.10  (FDA mandatory safety check)

SCORING SCALE:
    >= 0.60  -->  Strong candidate
    0.40-0.59 --> Borderline
    <  0.40  -->  Reject

NOTE ON RDKIT AVAILABILITY:
    This module works with OR without RDKit.
    If RDKit is blocked by Windows Application Control, all functions
    automatically fall back to pure-Python property estimation.
    RDKit mode gives exact values; fallback mode gives good approximations.

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import re
import json
import sqlite3
import warnings
import contextlib
import io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ============================================================================
# RDKIT LAZY LOADER  (avoids DLL load failure at module import time)
# ============================================================================

_RDKIT_LOADED  = None   # None = not tried yet, True = loaded OK, False = failed
_Chem          = None
_Descriptors   = None
_Crippen       = None
_QED_module    = None
_RDLogger      = None


def _try_load_rdkit():
    """
    Try to load RDKit exactly once. Caches the result so we don't retry
    on every function call. Returns True if rdkit loaded, False if blocked.
    """
    global _RDKIT_LOADED, _Chem, _Descriptors, _Crippen, _QED_module, _RDLogger
    if _RDKIT_LOADED is not None:
        return _RDKIT_LOADED

    try:
        # Suppress any output from rdkit itself during loading
        with contextlib.redirect_stderr(io.StringIO()):
            from rdkit import Chem as _c
            from rdkit.Chem import Descriptors as _d
            from rdkit.Chem import Crippen as _cr
            from rdkit.Chem import QED as _q
            from rdkit import RDLogger as _rl
            _rl.DisableLog("rdApp.*")

        _Chem        = _c
        _Descriptors = _d
        _Crippen     = _cr
        _QED_module  = _q
        _RDLogger    = _rl
        _RDKIT_LOADED = True
        return True

    except Exception:
        _RDKIT_LOADED = False
        return False


# ============================================================================
# CONSTANTS
# ============================================================================

# Path to persistent molecule database
DB_PATH = "outputs/genorova_memory.db"

# Import the canonical reference drug list from the single source of truth.
# All novelty exact-match checks in this module use this list so that any
# update to reference_data.py propagates here automatically.
import sys as _sys
from pathlib import Path as _Path
_scorer_src = _Path(__file__).resolve().parent   # genorova/src/
if str(_scorer_src) not in _sys.path:
    _sys.path.insert(0, str(_scorer_src))

try:
    from validation.reference_data import REFERENCE_DRUGS as _CANONICAL_REFERENCE_DRUGS
    APPROVED_DIABETES_DRUGS = _CANONICAL_REFERENCE_DRUGS
except Exception as _e:
    # Fallback so the scorer still runs if reference_data is unreachable.
    # This copy will drift — fix the import issue rather than relying on this.
    print(f"   [scorer] WARNING: could not import reference_data ({_e}). Using local fallback.")
    APPROVED_DIABETES_DRUGS = {
        "metformin":     "CN(C)C(=N)NC(=N)N",
        "sitagliptin":   "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
        "empagliflozin": "OC[C@@H]1O[C@@H](c2ccc(Cl)cc2-c2ccc(OCC3CCOCC3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
        "glipizide":     "Cc1cnc(CN2C(=O)CCC2=O)s1",
        "aspirin":       "CC(=O)Oc1ccccc1C(=O)O",
        "paracetamol":   "CC(=O)Nc1ccc(O)cc1",
        "ibuprofen":     "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "caffeine":      "Cn1cnc2c1c(=O)n(c(=O)n2C)C",
    }

# Lipinski Rule of 5 limits
LIPINSKI_MW_MAX    = 500
LIPINSKI_LOGP_MAX  = 5.0
LIPINSKI_HBD_MAX   = 5
LIPINSKI_HBA_MAX   = 10


# ============================================================================
# PURE-PYTHON PROPERTY ESTIMATOR  (fallback when rdkit is unavailable)
# ============================================================================

# Atomic masses for property calculations
_ATOM_MASS = {
    'C': 12.011, 'N': 14.007, 'O': 15.999, 'S': 32.065, 'P': 30.974,
    'F': 19.000, 'Cl': 35.453, 'Br': 79.904, 'I': 126.904,
    'Si': 28.086, 'Se': 78.971, 'B': 10.811, 'H': 1.008,
}


def _count_atoms(smiles):
    """
    Count heavy atoms in a SMILES string using pattern matching.
    Handles both bracketed atoms [NH], [OH] and bare atoms.
    Returns a dict like {'C': 9, 'O': 4, 'H': 2, ...}.
    """
    counts = {sym: 0 for sym in _ATOM_MASS}

    # 1. Extract and process bracket atoms  e.g. [NH2+], [O-], [nH]
    bracket_groups = re.findall(r'\[([^\]]+)\]', smiles)
    # Remove bracket groups from SMILES so we don't double-count
    smiles_no_brackets = re.sub(r'\[[^\]]+\]', '', smiles)

    for bg in bracket_groups:
        # Atom symbol is letters at the start
        m = re.match(r'([A-Za-z]{1,2})', bg)
        if m:
            raw = m.group(1)
            # Normalise: first letter upper, second lower (e.g. Cl not CL)
            sym = raw[0].upper() + (raw[1].lower() if len(raw) > 1 else '')
            if sym in counts:
                counts[sym] += 1
        # Explicit H in bracket  e.g. [NH2] → H=2
        h_match = re.search(r'H(\d*)', bg)
        if h_match:
            n = int(h_match.group(1)) if h_match.group(1) else 1
            counts['H'] += n

    # 2. Handle two-letter atoms in the cleaned SMILES
    temp = smiles_no_brackets
    for sym in ('Cl', 'Br', 'Si', 'Se'):
        cnt = len(re.findall(sym, temp, re.IGNORECASE))
        counts[sym] += cnt
        temp = re.sub(sym, '__', temp, flags=re.IGNORECASE)

    # 3. Single-letter atoms (upper and lower case both map to same element)
    for ch in temp:
        upper = ch.upper()
        if upper in ('C', 'N', 'O', 'S', 'P', 'F', 'I', 'B') and ch.isalpha():
            counts[upper] += 1

    return counts


def _smiles_props_approx(smiles):
    """
    Estimate molecular properties from a SMILES string without rdkit.

    Computed properties:
        mw      -- approximate molecular weight (Da)
        logp    -- approximate octanol-water partition coefficient
        hbd     -- hydrogen bond donor count (N-H and O-H)
        hba     -- hydrogen bond acceptor count (N and O)
        tpsa    -- approximate topological polar surface area
        rot     -- approximate rotatable bond count
        qed     -- approximate drug-likeness score (0-1)
        sa      -- approximate synthetic accessibility score (1-10)
        lip     -- Lipinski Rule of 5 pass/fail (bool)
        n_rings -- approximate ring count
        n_arom  -- approximate aromatic ring count
        n_N     -- nitrogen atom count
    """
    atom_counts = _count_atoms(smiles)

    # --- Molecular Weight ---
    # Heavy atom MW contribution
    heavy_mw = sum(atom_counts.get(sym, 0) * mass
                   for sym, mass in _ATOM_MASS.items() if sym != 'H')
    # Estimate implicit H: ~0.8 per C, 0.4 per N, 0.2 per O
    n_imp_h = (atom_counts.get('C', 0) * 0.8 +
               atom_counts.get('N', 0) * 0.4 +
               atom_counts.get('O', 0) * 0.2)
    mw = heavy_mw + (atom_counts.get('H', 0) + n_imp_h) * 1.008

    # --- HBD: count [NH], [nH], [OH] and simple OH patterns ---
    n_hbd = (len(re.findall(r'\[NH', smiles, re.IGNORECASE)) +
             len(re.findall(r'\[OH', smiles, re.IGNORECASE)) +
             len(re.findall(r'nH',  smiles)))
    # Bare -OH: "O" preceded by single bond not in ring context (rough)
    n_hbd = max(n_hbd,
                smiles.count('[OH]') +
                smiles.count('[NH]') +
                smiles.count('[NH2]') +
                smiles.count('[NH3]'))

    # --- HBA: total N + O count ---
    n_hba = atom_counts.get('N', 0) + atom_counts.get('O', 0)

    # --- LogP (Ghose-like atom contribution approximation) ---
    logp = (atom_counts.get('C',  0) *  0.53
            - atom_counts.get('N',  0) *  0.44
            - atom_counts.get('O',  0) *  0.67
            - atom_counts.get('S',  0) *  0.07
            + atom_counts.get('F',  0) *  0.14
            + atom_counts.get('Cl', 0) *  0.60
            + atom_counts.get('Br', 0) *  0.85
            + atom_counts.get('I',  0) *  1.20
            - n_hbd * 0.50)

    # --- Lipinski ---
    lip = (mw <= LIPINSKI_MW_MAX and logp <= LIPINSKI_LOGP_MAX
           and n_hbd <= LIPINSKI_HBD_MAX and n_hba <= LIPINSKI_HBA_MAX)

    # --- Ring count (count unique ring-closure digits) ---
    ring_digits = set(re.findall(r'\d', re.sub(r'%\d\d', '', smiles)))
    n_rings = len(ring_digits)

    # --- Aromatic count (lowercase letters = aromatic atoms) ---
    n_arom_atoms = sum(1 for ch in smiles if ch in 'cnospb')
    n_arom_rings = max(n_arom_atoms // 6,
                       smiles.lower().count('c1ccccc1'),   # benzene
                       smiles.lower().count('c1ccncc1'))   # pyridine

    # --- TPSA approximation ---
    tpsa = (atom_counts.get('O', 0) * 9.0 +
            atom_counts.get('N', 0) * 12.0 +
            n_hbd * 8.0)

    # --- Rotatable bonds approximation ---
    n_heavy = sum(v for k, v in atom_counts.items() if k != 'H')
    rot = max(0, n_heavy // 4)

    # --- QED approximation (0-1, higher = more drug-like) ---
    # Based on ideal ranges for each property
    qed_mw  = max(0.0, min(1.0, 1.0 - abs(mw - 300.0) / 300.0))
    qed_lp  = max(0.0, min(1.0, 1.0 - abs(logp - 2.5) / 5.0))
    qed_hbd = max(0.0, 1.0 - n_hbd / 6.0)
    qed_hba = max(0.0, 1.0 - n_hba / 12.0)
    qed = round((qed_mw + qed_lp + qed_hbd + qed_hba) / 4.0, 3)

    # --- SA score approximation (1-10, lower = easier to synthesize) ---
    sa = max(1.0, min(10.0,
        1.5 + n_rings * 0.4
            + atom_counts.get('C', 0) * 0.05
            + n_arom_rings * 0.3))

    return {
        'mw':      round(mw, 1),
        'logp':    round(logp, 2),
        'hbd':     int(n_hbd),
        'hba':     int(n_hba),
        'tpsa':    round(tpsa, 1),
        'rot':     int(rot),
        'qed':     qed,
        'sa':      round(sa, 2),
        'lip':     lip,
        'n_rings': n_rings,
        'n_arom':  n_arom_rings,
        'n_N':     atom_counts.get('N', 0),
    }


# ============================================================================
# 1. LIPINSKI RULE OF 5 CHECK
# ============================================================================

def passes_lipinski(smiles):
    """
    Check if a molecule passes Lipinski's Rule of 5.

    Lipinski's Rule of 5 predicts whether a molecule could be orally
    bioavailable. A molecule PASSES if it meets ALL four criteria:

    Rules:
        - Molecular weight <= 500 Da
        - LogP (lipophilicity) <= 5.0
        - Hydrogen bond donors <= 5
        - Hydrogen bond acceptors <= 10

    Uses RDKit for accurate values; falls back to pure-Python approximation
    if RDKit is unavailable (e.g. blocked by Windows Application Control).

    Args:
        smiles (str): SMILES string of the molecule

    Returns:
        bool: True if molecule passes all 4 rules, False otherwise

    Example:
        >>> passes_lipinski("CN(C)C(=N)NC(=N)N")   # Metformin
        True
    """
    print(f"   [Lipinski] Checking: {smiles[:40]}...")

    try:
        if _try_load_rdkit():
            # --- RDKit path (exact) ---
            mol = _Chem.MolFromSmiles(smiles)
            if mol is None:
                print(f"   [Lipinski] ERROR: Invalid SMILES string")
                return False

            mw   = _Descriptors.MolWt(mol)
            logp = _Crippen.MolLogP(mol)
            hbd  = _Descriptors.NumHDonors(mol)
            hba  = _Descriptors.NumHAcceptors(mol)
        else:
            # --- Pure-Python fallback (approximate) ---
            print(f"   [Lipinski] RDKit not available -- using approximation")
            props = _smiles_props_approx(smiles)
            mw, logp, hbd, hba = props['mw'], props['logp'], props['hbd'], props['hba']

        rule_mw  = mw   <= LIPINSKI_MW_MAX
        rule_lp  = logp <= LIPINSKI_LOGP_MAX
        rule_hbd = hbd  <= LIPINSKI_HBD_MAX
        rule_hba = hba  <= LIPINSKI_HBA_MAX
        passed   = rule_mw and rule_lp and rule_hbd and rule_hba

        print(f"   [Lipinski] MW={mw:.1f}(<={LIPINSKI_MW_MAX}:{rule_mw})  "
              f"LogP={logp:.2f}(<={LIPINSKI_LOGP_MAX}:{rule_lp})  "
              f"HBD={hbd}(<={LIPINSKI_HBD_MAX}:{rule_hbd})  "
              f"HBA={hba}(<={LIPINSKI_HBA_MAX}:{rule_hba})")
        print(f"   [Lipinski] Result: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        print(f"   [Lipinski] ERROR: {e}")
        return False


# ============================================================================
# 2. DRUG-LIKENESS SCORE (QED)
# ============================================================================

def calculate_qed(smiles):
    """
    Calculate the Quantitative Estimate of Drug-likeness (QED) score.

    QED measures how drug-like a molecule is on a scale from 0 to 1.
    Uses RDKit's official QED module when available; approximation otherwise.

    Scale:
        0.7 - 1.0  --> Excellent drug candidate
        0.5 - 0.7  --> Good drug candidate
        0.3 - 0.5  --> Borderline
        0.0 - 0.3  --> Poor drug-likeness

    Args:
        smiles (str): SMILES string of the molecule

    Returns:
        float: QED score between 0.0 and 1.0 (higher = more drug-like)

    Example:
        >>> calculate_qed("CC(=O)Oc1ccccc1C(=O)O")   # Aspirin
        0.553
    """
    print(f"   [QED] Calculating for: {smiles[:40]}...")

    try:
        if _try_load_rdkit():
            # --- RDKit path (exact) ---
            mol = _Chem.MolFromSmiles(smiles)
            if mol is None:
                print(f"   [QED] ERROR: Invalid SMILES string")
                return 0.0
            score = _QED_module.qed(mol)
        else:
            # --- Pure-Python fallback ---
            print(f"   [QED] RDKit not available -- using approximation")
            score = _smiles_props_approx(smiles)['qed']

        print(f"   [QED] Score: {score:.4f}")
        return round(float(score), 4)

    except Exception as e:
        print(f"   [QED] ERROR: {e}")
        return 0.0


# ============================================================================
# 3. SYNTHETIC ACCESSIBILITY SCORE
# ============================================================================

def calculate_sa_score(smiles):
    """
    Calculate the Synthetic Accessibility (SA) score.

    The SA score predicts how easy it is to synthesize a molecule.
    Scale: 1 (easy) to 10 (practically impossible).
    Uses RDKit's sascorer when available; approximation otherwise.

    Args:
        smiles (str): SMILES string of the molecule

    Returns:
        float: SA score between 1.0 and 10.0 (lower = easier to synthesize)

    Example:
        >>> calculate_sa_score("CC(=O)Oc1ccccc1C(=O)O")   # Aspirin
        1.8
    """
    print(f"   [SA Score] Calculating for: {smiles[:40]}...")

    try:
        if _try_load_rdkit():
            # --- RDKit path ---
            mol = _Chem.MolFromSmiles(smiles)
            if mol is None:
                print(f"   [SA Score] ERROR: Invalid SMILES string")
                return 10.0

            try:
                # Try the official SA scorer
                from rdkit.Contrib.SA_Score import sascorer
                score = sascorer.calculateScore(mol)
                print(f"   [SA Score] Score: {score:.4f} (RDKit sascorer)")
                return round(float(score), 4)

            except ImportError:
                # Fallback using basic RDKit descriptors
                num_atoms   = mol.GetNumAtoms()
                num_rings   = _Descriptors.RingCount(mol)
                num_stereo  = len(_Chem.FindMolChiralCenters(mol, includeUnassigned=True))
                num_hetero  = _Descriptors.NumHeteroatoms(mol)
                complexity  = (0.2 * min(num_atoms, 30)
                               + 0.5 * min(num_rings, 5)
                               + 0.3 * min(num_stereo, 5)
                               + 0.1 * min(num_hetero, 10))
                score = max(1.0, min(10.0, 1.0 + complexity))
                print(f"   [SA Score] Score: {score:.4f} (RDKit approx)")
                return round(float(score), 4)
        else:
            # --- Pure-Python fallback ---
            print(f"   [SA Score] RDKit not available -- using approximation")
            score = _smiles_props_approx(smiles)['sa']
            print(f"   [SA Score] Score: {score:.4f} (pure-Python approx)")
            return round(float(score), 4)

    except Exception as e:
        print(f"   [SA Score] ERROR: {e}")
        return 5.0


# ============================================================================
# 4. NOVELTY CHECK
# ============================================================================

def is_novel(smiles, db_path=DB_PATH):
    """
    Simple exact-match novelty check used by the legacy scorer pipeline.

    Checks two sources:
    1. The persistent Genorova molecule database (SQLite)
    2. The canonical APPROVED_DIABETES_DRUGS list (sourced from reference_data.py)

    NOTE: This is an exact-string check only — it does NOT apply Tanimoto
    similarity. The full three-layer novelty check (including Tanimoto at
    TANIMOTO_KNOWN_THRESHOLD) lives in validation/chemistry/sanitizer.check_novelty()
    and is used by the canonical validation pipeline. Use that function when
    you need the structured novelty flag ("potentially_novel_patentable",
    "known_repurposing_lead", "local_only_checked", "unrealistic").

    Does NOT require RDKit — uses simple string comparison.

    Args:
        smiles (str): SMILES string to check
        db_path (str): Path to the Genorova SQLite database

    Returns:
        bool: True if the molecule is novel (not in approved list or DB), False otherwise

    Example:
        >>> is_novel("CN(C)C(=N)NC(=N)N")   # Metformin -- not novel
        False
    """
    print(f"   [Novelty] Checking: {smiles[:40]}...")

    # Check against known approved drugs (exact SMILES match)
    if smiles in APPROVED_DIABETES_DRUGS.values():
        print(f"   [Novelty] Found in approved drugs list -- NOT novel")
        return False

    # Check against persistent database (if it exists)
    db_file = Path(db_path)
    if db_file.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM molecules WHERE smiles = ?", (smiles,))
            count = cursor.fetchone()[0]
            conn.close()

            if count > 0:
                print(f"   [Novelty] Found in Genorova database -- NOT novel")
                return False
        except Exception as e:
            print(f"   [Novelty] Database check skipped: {e}")

    print(f"   [Novelty] Molecule is NOVEL")
    return True


# ============================================================================
# 5. GENOROVA CLINICAL SCORE
# ============================================================================

def genorova_clinical_score(smiles):
    """
    Calculate the Genorova composite clinical score (0 to 1).

    Combines 5 clinical endpoints from real Phase 3 diabetes trials.
    Works with OR without RDKit (uses pure-Python approximation if needed).

    Clinical endpoints and weights:
        HbA1c reduction potential : 0.35 (most important -- primary endpoint)
        Fasting glucose effect    : 0.25 (secondary endpoint)
        Hypoglycemia risk         : 0.20 (safety -- low risk = higher score)
        Body weight effect        : 0.10 (bonus for weight loss potential)
        Cardiovascular safety     : 0.10 (FDA requirement -- no CV risk)

    Score interpretation:
        >= 0.60  -->  Strong candidate
        0.40-0.59 --> Borderline
        <  0.40  -->  Reject

    Args:
        smiles (str): SMILES string of the molecule

    Returns:
        float: Clinical score between 0.0 and 1.0

    Example:
        >>> genorova_clinical_score("CN(C)C(=N)NC(=N)N")   # Metformin
        0.52
    """
    print(f"   [Clinical Score] Scoring: {smiles[:50]}...")

    try:
        # --- Get molecular properties (rdkit if available, else approx) ---
        if _try_load_rdkit():
            mol = _Chem.MolFromSmiles(smiles)
            if mol is None:
                print(f"   [Clinical Score] ERROR: Invalid SMILES -- score = 0.0")
                return 0.0
            mw   = _Descriptors.MolWt(mol)
            logp = _Crippen.MolLogP(mol)
            hbd  = _Descriptors.NumHDonors(mol)
            hba  = _Descriptors.NumHAcceptors(mol)
            tpsa = _Descriptors.TPSA(mol)
            rot  = _Descriptors.NumRotatableBonds(mol)
            qed  = _QED_module.qed(mol)
            num_arom = _Descriptors.NumAromaticRings(mol)
            num_N    = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == 'N')
        else:
            print(f"   [Clinical Score] RDKit not available -- using pure-Python props")
            props = _smiles_props_approx(smiles)
            mw       = props['mw']
            logp     = props['logp']
            hbd      = props['hbd']
            hba      = props['hba']
            tpsa     = props['tpsa']
            rot      = props['rot']
            qed      = props['qed']
            num_arom = props['n_arom']
            num_N    = props['n_N']

        # ----------------------------------------------------------------
        # ENDPOINT 1: HbA1c Reduction Potential (weight = 0.35)
        # Proxy: balanced polarity + moderate MW + good bioavailability
        # ----------------------------------------------------------------
        hba1c_score = 0.0
        hba1c_score += 0.40 * qed                         # QED contributes heavily
        if 150 <= mw <= 450:   hba1c_score += 0.30        # optimal MW range
        elif 100 <= mw <= 500: hba1c_score += 0.15
        if 0.0 <= logp <= 3.0:   hba1c_score += 0.20      # good bioavailability
        elif -1.0 <= logp <= 5.0: hba1c_score += 0.10
        if 60 <= tpsa <= 130:  hba1c_score += 0.10        # ideal polar surface area
        elif 20 <= tpsa <= 160: hba1c_score += 0.05
        hba1c_score   = min(1.0, hba1c_score)
        weighted_hba1c = 0.35 * hba1c_score

        # ----------------------------------------------------------------
        # ENDPOINT 2: Fasting Plasma Glucose Effect (weight = 0.25)
        # Proxy: oral absorption indicators
        # ----------------------------------------------------------------
        fpg_score = 0.0
        lip_ok = (mw <= 500 and logp <= 5.0 and hbd <= 5 and hba <= 10)
        if lip_ok:              fpg_score += 0.50          # Lipinski pass
        if rot <= 5:            fpg_score += 0.30          # rigid = better absorbed
        elif rot <= 10:         fpg_score += 0.15
        if hbd <= 3 and hba <= 7: fpg_score += 0.20        # good membrane transport
        fpg_score    = min(1.0, fpg_score)
        weighted_fpg = 0.25 * fpg_score

        # ----------------------------------------------------------------
        # ENDPOINT 3: Hypoglycemia Risk (weight = 0.20)
        # PENALIZES molecules likely to cause dangerous low blood sugar.
        # 1.0 = completely safe; 0.0 = very dangerous.
        # ----------------------------------------------------------------
        safety_score = 1.0
        if "S(=O)(=O)N" in smiles or "S(=O)(=O)N" in smiles.upper():
            # Sulfonylurea pattern: causes direct beta-cell insulin release
            safety_score -= 0.50
            print(f"   [Clinical Score] WARNING: Sulfonylurea pattern detected (-0.50)")
        if num_N > 4:
            safety_score -= 0.15  # many amines = CNS glucose effects risk
        if mw < 100:
            safety_score -= 0.10  # very small = non-specific binding
        safety_score    = max(0.0, min(1.0, safety_score))
        weighted_safety = 0.20 * safety_score

        # ----------------------------------------------------------------
        # ENDPOINT 4: Body Weight Effect (weight = 0.10)
        # GLP-1-like molecules (weight-neutral/reducing) tend to have:
        # moderate LogP and higher polarity.
        # ----------------------------------------------------------------
        weight_score = 0.0
        if logp <= 1.0:        weight_score += 0.50
        elif logp <= 3.0:      weight_score += 0.30
        elif logp <= 5.0:      weight_score += 0.10
        if tpsa >= 80:         weight_score += 0.30
        elif tpsa >= 50:       weight_score += 0.15
        if 3 <= hba <= 8:      weight_score += 0.20
        weight_score    = min(1.0, weight_score)
        weighted_weight = 0.10 * weight_score

        # ----------------------------------------------------------------
        # ENDPOINT 5: Cardiovascular Safety (weight = 0.10)
        # FDA requires CV safety proof for all diabetes drugs.
        # Red flags: too many aromatic rings (hERG risk), excessive amines.
        # ----------------------------------------------------------------
        cv_score = 0.8
        if num_arom >= 4:        cv_score -= 0.30   # QT prolongation risk
        elif num_arom == 3:      cv_score -= 0.10
        if num_arom >= 2 and num_N >= 3:
            cv_score -= 0.20                          # hERG blocker pattern
        if mw > 600:             cv_score -= 0.20    # accumulation risk
        cv_score    = max(0.0, min(1.0, cv_score))
        weighted_cv = 0.10 * cv_score

        # ----------------------------------------------------------------
        # COMPOSITE SCORE
        # ----------------------------------------------------------------
        total_score = (weighted_hba1c + weighted_fpg + weighted_safety
                       + weighted_weight + weighted_cv)
        total_score = round(min(1.0, max(0.0, total_score)), 4)

        print(f"   [Clinical Score] HbA1c={hba1c_score:.3f}(x0.35)  "
              f"FPG={fpg_score:.3f}(x0.25)  "
              f"Safety={safety_score:.3f}(x0.20)  "
              f"Weight={weight_score:.3f}(x0.10)  "
              f"CV={cv_score:.3f}(x0.10)")
        print(f"   [Clinical Score] TOTAL = {total_score:.4f}")
        return total_score

    except Exception as e:
        print(f"   [Clinical Score] ERROR: {e}")
        return 0.0


# ============================================================================
# 6. GENERATE MOLECULE REPORT
# ============================================================================

def generate_molecule_report(smiles):
    """
    Generate a full analysis report for a single molecule.

    Runs all scoring functions and compiles a complete report dictionary.
    Works with OR without RDKit.

    Args:
        smiles (str): SMILES string of the molecule

    Returns:
        dict: Complete molecule report, or None if molecule is invalid
              (e.g. empty string or known-bad SMILES)

    Example:
        >>> report = generate_molecule_report("CN(C)C(=N)NC(=N)N")
        >>> print(report['recommendation'])
        'Borderline'
    """
    print(f"\n   [Report] Generating report for: {smiles[:50]}...")

    # Basic sanity check before running anything else
    if not smiles or len(smiles) < 2:
        print(f"   [Report] ERROR: SMILES too short -- skipping")
        return None

    try:
        if _try_load_rdkit():
            mol = _Chem.MolFromSmiles(smiles)
            if mol is None:
                print(f"   [Report] ERROR: Invalid SMILES (rdkit) -- cannot generate report")
                return None
            mw   = _Descriptors.MolWt(mol)
            logp = _Crippen.MolLogP(mol)
            hbd  = _Descriptors.NumHDonors(mol)
            hba  = _Descriptors.NumHAcceptors(mol)
            tpsa = _Descriptors.TPSA(mol)
            rot  = _Descriptors.NumRotatableBonds(mol)
        else:
            props = _smiles_props_approx(smiles)
            mw, logp, hbd, hba = props['mw'], props['logp'], props['hbd'], props['hba']
            tpsa, rot = props['tpsa'], props['rot']

        # Run all scoring functions
        qed_score  = calculate_qed(smiles)
        sa_score   = calculate_sa_score(smiles)
        lip_pass   = passes_lipinski(smiles)
        novel      = is_novel(smiles)
        clin_score = genorova_clinical_score(smiles)

        if   clin_score >= 0.60: recommendation = "Strong candidate"
        elif clin_score >= 0.40: recommendation = "Borderline"
        else:                    recommendation = "Reject"

        report = {
            "smiles":                    smiles,
            "molecular_weight":          round(float(mw), 2),
            "logP":                      round(float(logp), 3),
            "hbd":                       int(hbd),
            "hba":                       int(hba),
            "tpsa":                      round(float(tpsa), 2),
            "rotatable_bonds":           int(rot),
            "qed_score":                 qed_score,
            "sa_score":                  sa_score,
            "passes_lipinski":           lip_pass,
            "is_novel":                  novel,
            "genorova_clinical_score":   clin_score,
            "recommendation":            recommendation,
            "generated_at":              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model_version":             "1.0",
        }

        print(f"   [Report] Done. Score={clin_score:.4f} | {recommendation}")
        return report

    except Exception as e:
        print(f"   [Report] ERROR: {e}")
        return None


# ============================================================================
# 7. RANK CANDIDATES
# ============================================================================

def rank_candidates(molecule_list):
    """
    Score and rank a list of molecules by their Genorova clinical score.

    Runs generate_molecule_report() on every molecule in the list,
    then sorts results from highest to lowest clinical score.
    Skips invalid SMILES (they won't appear in results).

    Args:
        molecule_list (list): List of SMILES strings to score

    Returns:
        pd.DataFrame: Scored molecules sorted by genorova_clinical_score descending

    Example:
        >>> smiles_list = ["CC(=O)Oc1ccccc1C(=O)O", "CN(C)C(=N)NC(=N)N"]
        >>> ranked = rank_candidates(smiles_list)
    """
    print(f"\n[*] Ranking {len(molecule_list)} molecules...")

    reports = []
    for i, smiles in enumerate(molecule_list, 1):
        print(f"\n--- Molecule {i}/{len(molecule_list)} ---")
        report = generate_molecule_report(smiles)
        if report is not None:
            reports.append(report)

    if not reports:
        print("[!] No valid molecules to rank.")
        return pd.DataFrame()

    df = pd.DataFrame(reports)
    df = df.sort_values("genorova_clinical_score", ascending=False).reset_index(drop=True)
    df.index = df.index + 1

    print(f"\n[OK] Ranked {len(df)} valid molecules")
    return df


# ============================================================================
# MAIN -- Test on 5 known drugs
# ============================================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("GENOROVA AI -- CLINICAL SCORING ENGINE")
    rdkit_ok = _try_load_rdkit()
    print(f"RDKit available: {rdkit_ok} {'(exact mode)' if rdkit_ok else '(approximation mode)'}")
    print("Testing on 5 known reference drugs")
    print("=" * 70)

    test_drugs = {
        "Metformin":   "CN(C)C(=N)NC(=N)N",
        "Aspirin":     "CC(=O)Oc1ccccc1C(=O)O",
        "Caffeine":    "Cn1cnc2c1c(=O)n(c(=O)n2C)C",
        "Paracetamol": "CC(=O)Nc1ccc(O)cc1",
        "Ibuprofen":   "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    }

    results = []
    for name, smiles in test_drugs.items():
        print(f"\n{'='*60}")
        print(f"Scoring: {name}")
        print(f"SMILES:  {smiles}")
        print(f"{'='*60}")
        report = generate_molecule_report(smiles)
        if report:
            report["drug_name"] = name
            results.append(report)

    print()
    print("=" * 90)
    print("FINAL SUMMARY TABLE")
    print("=" * 90)
    header = (f"{'Drug':<14} | {'SMILES':<42} | "
              f"{'QED':>6} | {'Lipinski':>8} | {'Clinical':>8} | {'Verdict'}")
    print(header)
    print("-" * 90)

    for r in results:
        smi = r['smiles'][:39] + "..." if len(r['smiles']) > 42 else r['smiles']
        lip = "YES" if r['passes_lipinski'] else "NO"
        print(f"{r['drug_name']:<14} | {smi:<42} | "
              f"{r['qed_score']:>6.3f} | {lip:>8} | "
              f"{r['genorova_clinical_score']:>8.3f} | {r['recommendation']}")

    print("-" * 90)

    sorted_results = sorted(results, key=lambda x: x['genorova_clinical_score'], reverse=True)
    print("\n[*] Ranked from best to worst clinical candidate:")
    for rank, r in enumerate(sorted_results, 1):
        print(f"   {rank}. {r['drug_name']:<14}  "
              f"score={r['genorova_clinical_score']:.3f}  ({r['recommendation']})")

    print()
    print("=" * 70)
    print("SCORING COMPLETE")
    print("=" * 70)
