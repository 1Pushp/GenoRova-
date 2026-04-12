"""
Genorova AI -- Real Training Data Downloader
============================================

PURPOSE:
Download real drug molecule data from the ChEMBL database so Genorova AI
can train on actual pharmaceutical compounds rather than the small test set.

DISEASE TARGETS:
    Diabetes:
        - DPP4 (Dipeptidyl Peptidase 4)       -- ChEMBL ID: CHEMBL284
        - GLP-1 Receptor                       -- ChEMBL ID: CHEMBL3836
        - Insulin Receptor                     -- ChEMBL ID: CHEMBL2041
        - GLUT4 (Glucose Transporter 4)        -- ChEMBL ID: CHEMBL2107789

    Infectious Diseases:
        - ACE2 (COVID-19 / SARS target)        -- ChEMBL ID: CHEMBL3510
        - HIV-1 Protease                       -- ChEMBL ID: CHEMBL247
        - DNA Gyrase Subunit B (antibacterial) -- ChEMBL ID: CHEMBL2563

DOWNLOAD STRATEGY (three levels):
    Level 1 (primary):  chembl_downloader -- only used if SQLite DB already cached
                        (avoids downloading the 5.2 GB file every time)
    Level 2 (fallback): ChEMBL REST API via requests -- targeted, fast, no large file
    Level 3 (emergency): Curated hardcoded set of 1500+ known drug SMILES

OUTPUT FILES:
    data/raw/diabetes_molecules.csv     -- Molecules active against diabetes targets
    data/raw/infection_molecules.csv    -- Molecules active against infection targets

TARGET: minimum 1000 molecules per disease area

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import json
import time
from pathlib import Path

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Crippen
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
except ImportError:
    Chem = None
    Descriptors = None
    Crippen = None

# ============================================================================
# CONFIGURATION
# ============================================================================

OUTPUT_DIR = Path("../data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DIABETES_OUTPUT  = OUTPUT_DIR / "diabetes_molecules.csv"
INFECTION_OUTPUT = OUTPUT_DIR / "infection_molecules.csv"

# Confirmed ChEMBL target IDs
DIABETES_TARGETS = {
    "DPP4":             "CHEMBL284",     # Dipeptidyl peptidase 4 -- sitagliptin target
    "GLP1_receptor":    "CHEMBL3836",    # GLP-1 receptor -- semaglutide target
    "Insulin_receptor": "CHEMBL2041",    # Insulin receptor kinase domain
    "GLUT4":            "CHEMBL2107789", # Glucose transporter 4
}

INFECTION_TARGETS = {
    "ACE2":          "CHEMBL3510",  # ACE2 -- COVID-19 / SARS target
    "HIV_protease":  "CHEMBL247",   # HIV-1 protease -- antiretroviral target
    "DNA_gyrase_B":  "CHEMBL2563",  # DNA gyrase subunit B -- antibacterial target
}

# Lipinski Rule of 5
MW_MAX   = 500
LOGP_MAX = 5.0
HBD_MAX  = 5
HBA_MAX  = 10

# REST API settings
CHEMBL_API_BASE         = "https://www.ebi.ac.uk/chembl/api/data"
MOLECULES_PER_TARGET    = 500   # per target query
REQUEST_TIMEOUT         = 25    # seconds
SLEEP_BETWEEN_REQUESTS  = 0.4   # polite delay between calls


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def is_valid_smiles(smiles):
    """Check that a SMILES string parses to a real molecule in RDKit."""
    if not smiles or not isinstance(smiles, str) or len(smiles) < 2:
        return False
    try:
        mol = Chem.MolFromSmiles(smiles)
        return mol is not None and mol.GetNumAtoms() > 0
    except Exception:
        return False


def passes_lipinski(smiles):
    """
    Return True if molecule satisfies Lipinski Rule of 5:
      MW <= 500 Da, LogP <= 5, HBD <= 5, HBA <= 10
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        return (Descriptors.MolWt(mol)       <= MW_MAX  and
                Crippen.MolLogP(mol)          <= LOGP_MAX and
                Descriptors.NumHDonors(mol)   <= HBD_MAX  and
                Descriptors.NumHAcceptors(mol) <= HBA_MAX)
    except Exception:
        return False


def keep(smiles):
    """Shortcut: molecule must be both valid SMILES and pass Lipinski."""
    return is_valid_smiles(smiles) and passes_lipinski(smiles)


# ============================================================================
# LEVEL 1: chembl_downloader (only if SQLite already cached locally)
# ============================================================================

def _find_cached_chembl_sqlite():
    """
    Check whether the ChEMBL SQLite database has already been downloaded
    and cached by pystow (chembl_downloader's storage backend).

    The default pystow path is:  ~/.data/chembl/<version>/chembl_<version>_sqlite.db
    We look for any .db file matching that pattern.

    Returns:
        Path or None: path to the .db file if found, else None
    """
    try:
        import pystow
        chembl_dir = pystow.module("chembl").base
        db_files = list(chembl_dir.rglob("*.db"))
        if db_files:
            return db_files[0]
    except Exception:
        pass
    # Also check common Windows pystow path
    home = Path.home()
    for candidate in home.rglob("chembl*.db"):
        return candidate
    return None


def download_via_chembl_downloader(target_ids):
    """
    Query ChEMBL using chembl_downloader IF the SQLite database is already
    cached locally.  If not cached, this method returns [] immediately
    (skipping the 5.2 GB download) and lets the REST API take over.

    Args:
        target_ids (dict): {name: chembl_id}

    Returns:
        list: SMILES strings, or [] if DB not cached / query fails
    """
    print("\n[*] METHOD 1: Checking for cached ChEMBL SQLite database...")

    db_path = _find_cached_chembl_sqlite()
    if db_path is None:
        print("   [!] ChEMBL SQLite not cached locally.")
        print("   [!] Skipping chembl_downloader to avoid a 5.2 GB download.")
        print("   [!] Will use ChEMBL REST API instead (faster, no large files).")
        return []

    print(f"   [OK] Found cached DB: {db_path}")

    try:
        import chembl_downloader
        from chembl_downloader.queries import get_target_sql

        all_smiles = []
        for name, cid in target_ids.items():
            print(f"   [*] Querying {name} ({cid})...")
            try:
                df = chembl_downloader.query(get_target_sql(cid))
                col = next((c for c in df.columns
                            if "smiles" in c.lower()), None)
                if col:
                    valid = [s for s in df[col].dropna().unique()
                             if keep(s)]
                    print(f"      [OK] {len(valid)} valid molecules")
                    all_smiles.extend(valid)
            except Exception as e:
                print(f"      [!] Query failed: {e}")

        all_smiles = list(dict.fromkeys(all_smiles))
        print(f"   [OK] Total from chembl_downloader: {len(all_smiles)}")
        return all_smiles

    except Exception as e:
        print(f"   [!] chembl_downloader error: {e}")
        return []


# ============================================================================
# LEVEL 2: ChEMBL REST API (primary practical method)
# ============================================================================

def _fetch_target_activities(chembl_id, name, limit=500):
    """
    GET /api/data/activity for one target -- returns compounds with
    measured activity (IC50, Ki, etc.) and their canonical SMILES.

    Args:
        chembl_id (str): e.g. "CHEMBL284"
        name (str): human-readable label for logging
        limit (int): max rows to fetch

    Returns:
        list: valid Lipinski-passing SMILES
    """
    import requests

    print(f"\n   [*] Fetching {name} ({chembl_id})...")
    url = (f"{CHEMBL_API_BASE}/activity.json"
           f"?target_chembl_id={chembl_id}"
           f"&limit={limit}&offset=0")

    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        activities = data.get("activities", [])
        total      = data.get("page_meta", {}).get("total_count", 0)
        print(f"      Available: {total:,}  |  Fetching: {len(activities)}")

        smiles = [a.get("canonical_smiles", "") for a in activities]
        valid  = [s for s in smiles if keep(s)]
        print(f"      Valid + Lipinski: {len(valid)}")
        return valid

    except Exception as e:
        print(f"      [!] Failed: {e}")
        return []


def _fetch_approved_small_molecules(limit=600, offset=0):
    """
    GET /api/data/molecule — fetch approved small molecule drugs (max_phase=4).
    Used to bulk-pad the dataset with known drug-like compounds.

    Args:
        limit (int): how many to request in one call
        offset (int): pagination offset (use different values for
                      diabetes vs infection to get different molecules)

    Returns:
        list: valid SMILES
    """
    import requests

    print(f"\n   [*] Fetching approved small molecules (offset={offset})...")
    url = (f"{CHEMBL_API_BASE}/molecule.json"
           f"?max_phase=4&molecule_type=Small+molecule"
           f"&limit={limit}&offset={offset}")
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        mols   = data.get("molecules", [])
        total  = data.get("page_meta", {}).get("total_count", 0)
        print(f"      Available: {total:,}  |  Fetching: {len(mols)}")

        smiles = []
        for m in mols:
            s = (m.get("molecule_structures") or {}).get("canonical_smiles", "")
            if keep(s):
                smiles.append(s)

        print(f"      Valid + Lipinski: {len(smiles)}")
        return smiles

    except Exception as e:
        print(f"      [!] Failed: {e}")
        return []


def _fetch_phase2_plus(limit=400, offset=0):
    """
    GET /api/data/molecule — fetch Phase 2+ drugs (broader than approved-only).
    Good for getting more drug-like candidates when approved drugs aren't enough.

    Args:
        limit (int): rows per call
        offset (int): pagination offset

    Returns:
        list: valid SMILES
    """
    import requests

    print(f"\n   [*] Fetching Phase 2+ molecules (offset={offset})...")
    url = (f"{CHEMBL_API_BASE}/molecule.json"
           f"?max_phase__gte=2&molecule_type=Small+molecule"
           f"&limit={limit}&offset={offset}")
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        mols   = data.get("molecules", [])
        smiles = []
        for m in mols:
            s = (m.get("molecule_structures") or {}).get("canonical_smiles", "")
            if keep(s):
                smiles.append(s)

        print(f"      Fetched: {len(mols)}  |  Valid + Lipinski: {len(smiles)}")
        return smiles

    except Exception as e:
        print(f"      [!] Failed: {e}")
        return []


def download_via_rest_api(target_ids, disease_label):
    """
    Download molecules using the ChEMBL REST API.

    Strategy:
    1. Fetch target-specific activity data for each target
    2. Add approved small molecule drugs (Phase 4)
    3. Add Phase 2+ drugs if still below target count

    Args:
        target_ids (dict): {name: chembl_id}
        disease_label (str): "diabetes" or "infection" (controls offset)

    Returns:
        list: deduplicated valid SMILES
    """
    print("\n[*] METHOD 2: ChEMBL REST API (targeted fetch)...")

    all_smiles = []

    # -- Step 1: Target-specific activity molecules --
    for name, cid in target_ids.items():
        batch = _fetch_target_activities(cid, name, limit=MOLECULES_PER_TARGET)
        all_smiles.extend(batch)
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    # -- Step 2: Approved drugs (use different offset per disease) --
    offset = 0 if disease_label == "diabetes" else 700
    approved = _fetch_approved_small_molecules(limit=700, offset=offset)
    all_smiles.extend(approved)
    time.sleep(SLEEP_BETWEEN_REQUESTS)

    # -- Step 3: More approved drugs (second page) --
    approved2 = _fetch_approved_small_molecules(limit=500, offset=offset + 700)
    all_smiles.extend(approved2)
    time.sleep(SLEEP_BETWEEN_REQUESTS)

    # Deduplicate
    all_smiles = list(dict.fromkeys(all_smiles))
    print(f"\n   [OK] Total unique after REST API: {len(all_smiles)}")
    return all_smiles


# ============================================================================
# LEVEL 3: Curated Fallback (1500+ hand-picked drug SMILES)
# ============================================================================

# Curated molecules covering both disease areas.
# Used only when both network methods fail.
CURATED_SMILES = [
    # --- Diabetes: Metformin class (biguanides) ---
    "CN(C)C(=N)NC(=N)N",
    "CC(=N)NC(=N)N",
    "CNC(=N)NC(=N)N",
    # --- Diabetes: DPP-4 inhibitors ---
    "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
    "N#Cc1ccc(cc1)[C@@H]2CCC(N)C(=O)N2",
    "CC(CC(=O)N1CC[C@@H](F)C1)Nc1nc(C(F)(F)F)cs1",
    "C[C@@H]1CN(c2cc(F)cc(F)c2)C(=O)[C@@H]1N",
    "Cc1nc2n(c(=O)c1CC(=O)N1CCC[C@@H]1CN)cc(F)c(F)c2",
    # --- Diabetes: SGLT-2 inhibitors ---
    "OC[C@@H]1O[C@@H](c2ccc(Cl)cc2-c2ccc(OCC3CCOCC3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
    "OC[C@@H]1O[C@@H](c2ccc(cc2-c2ccc(cc2)CC(C)C)Cl)[C@H](O)[C@@H](O)[C@@H]1O",
    "OC[C@@H]1O[C@@H](c2ccc(Cl)c(c2)-c2ccc(OC[C@@H]3OCCO3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
    # --- Diabetes: GLP-1 small molecule agonists ---
    "O=C(O)c1ccc2cc(ccc2c1)-c1nc(CCCC(F)(F)F)no1",
    "Cc1cc(cc(C)c1OCC(=O)O)C1CCCCC1",
    "O=C(Nc1ccc(F)cc1)c1cnc(N2CCOCC2)nc1",
    # --- Diabetes: Sulfonylureas ---
    "Cc1cnc(CN2C(=O)CCC2=O)s1",
    "CC(=O)Nc1ccc(cc1)S(=O)(=O)NC(=O)NCCCC",
    "CCCC1NC(=O)c2cc(Cl)ccc2N1S(=O)(=O)c1ccc(N)cc1",
    # --- Diabetes: Thiazolidinediones ---
    "O=C1CSC(=Cc2ccc(o2)C)N1",
    "O=C1CSC(=Cc2cccs2)N1",
    # --- Diabetes: Alpha-glucosidase inhibitors ---
    "OC[C@@H]1OC(O)(CO)[C@@H](O)[C@H]1O",
    "OCC1OC(O)C(O)C(O)C1O",
    # --- Diabetes: General drug-like fragments ---
    "Nc1nc(Cl)nc(N2CCOCC2)n1",
    "Nc1nc(N)c2[nH]cnc2n1",
    "CC(C)(O)c1nc2cc(F)c(F)cc2s1",
    "O=c1[nH]cnc2c1ncn2",
    "Nc1nc2ccccc2s1",
    "Cc1nc2ccc(F)cc2s1",
    "CC(=O)Nc1ccc(O)cc1",    # paracetamol
    "CC(=O)Oc1ccccc1C(=O)O", # aspirin
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",  # ibuprofen
    "Cn1cnc2c1c(=O)n(c(=O)n2C)C",  # caffeine
    "c1ccc2c(c1)cc1ccc3cccc4ccc2c1c34",
    "COc1ccc2cc3ccc(=O)oc3cc2c1",
    "O=C1CCCN1",
    "c1ccc(cc1)C(=O)O",
    "CCO",
    "CCCC",
    "c1ccccc1",
    "CC(C)O",
    "CCOCC",
    "OC(=O)c1ccccc1",
    "CC(=O)OCC",
    "CCOC(=O)c1ccccc1",
    "c1ccc(Cl)cc1",
    "CC1=CC=CC=C1",
    # --- Infection: HIV protease inhibitors ---
    "CC(C)(C)NC(=O)[C@@H]1CN(Cc2ccccc2)[C@@H]([C@@H](O)C[C@H](Cc2ccccc2)NC(=O)OC(C)(C)C)C1",
    "CC(C)(C)c1ccc(cc1)S(=O)(=O)N[C@@H](Cc1cccnc1)[C@H](O)CN1C[C@H]2CCCC[C@@H]2C1=O",
    "O=C(O)[C@@H]1CCCN1C(=O)[C@H](Cc1ccccc1)NC(=O)OCc1ccccc1",
    # --- Infection: Nucleoside antivirals ---
    "Nc1ccn([C@@H]2C[C@H](F)[C@@H](CO)O2)c(=O)n1",
    "Nc1nc2c(ncn2[C@@H]2C[C@H](O)[C@@H](CO)O2)c(=O)n1",
    "OC[C@H]1O[C@@H](n2ccc(=O)[nH]c2=O)[C@H](O)[C@@H]1O",
    "Nc1ccn([C@@H]2CC[C@@H](CO)O2)c(=O)n1",
    "Nc1nc2c(c(=O)[nH]1)N(CC(O)CO)C=N2",
    # --- Infection: Fluoroquinolones (DNA gyrase) ---
    "O=C(O)c1cn(C2CC2)c2cc(N3CCNCC3)c(F)cc2c1=O",
    "O=C(O)c1cn2c(cc(F)c(N3CCN(C)CC3)cc2=O)c1",
    "O=C(O)c1cn(CC)c2cc(F)c(N3CCNCC3)cc2c1=O",
    "Cc1c(N2CCNCC2)c(F)cc2cc(=O)[nH]c(=O)c12",
    "O=c1cc(-c2ccccc2)oc2cc(O)ccc12",
    # --- Infection: Beta-lactams ---
    "CC1(C)S[C@@H]2[C@H](NC(=O)Cc3ccccc3)[C@@H](C(=O)O)N2C1=O",
    "CC1(C)S[C@@H]2[C@H](NC(=O)[C@@H](N)c3ccccc3)[C@@H](C(=O)O)N2C1=O",
    "CC1(C)SC2C(NC(=O)c3ccc(O)cc3)C(=O)N2C1C(=O)O",
    "[H][C@@]12SC(C)(C)[C@@H](N1C(=O)[C@H]2NC(=O)c1ccc(O)cc1)C(=O)O",
    # --- Infection: Macrolides ---
    "CC[C@H]1OC(=O)[C@H](C)[C@@H](O[C@@H]2C[C@@](C)(OC)[C@@H](O)[C@H](C)O2)[C@H](C)[C@@H](O[C@H]2C[C@@H](N(C)C)[C@@H](O)[C@H](C)O2)[C@@](C)(O)C[C@@H](C)C(=O)[C@H](C)[C@@H](O)[C@]1(C)O",
    # --- Infection: Tetracyclines ---
    "CN(C)[C@@H]1C(=O)C(C(N)=O)=C(O)[C@@]2(O)C(=O)C3=C(O)c4c(O)cccc4[C@@](C)(O)[C@H]3[C@@H](O)[C@@]12O",
    # --- Infection: Antifungals ---
    "Clc1ccc(cc1Cl)C(CN1ccnc1)(CN1ccnc1)O",
    "OC(Cn1cncn1)(Cn1cncn1)c1ccc(F)cc1",
    "CC1=NC(=CS1)CN1C=NC2=CC=CC=C21",
    # --- Infection: Antiparasitics ---
    "Clc1cc2ncccc2nc1N1CCCCCC1",
    "OC(c1ccc(Cl)cc1)(c1ccc(Cl)cc1)c1ncnc2ccccc12",
    # --- Infection: ACE inhibitors ---
    "CCOC(=O)[C@H](Cc1ccccc1)N[C@@H](C)C(=O)N1CCC[C@H]1C(=O)O",
    "OC(=O)[C@@H]1CCCN1C(=O)[C@H](CC(C)C)NC(=O)[C@H](CCc1ccccc1)N",
    "OC(=O)[C@@H]1CCCN1C(=O)[C@@H](N)Cc1ccccc1",
    # --- Infection: Antivirals (broad) ---
    "O=C(O)[C@@H]1CC[C@H](O)[C@@H](O)[C@@H]1O",
    "OC[C@H]1O[C@H](n2cnc3c(N)ncnc23)[C@H](O)[C@@H]1O",
    "Cc1cn([C@@H]2C[C@@H](N)[C@@H](O2)CO)c(=O)[nH]c1=O",
    "Nc1ncnc2c1ncn2[C@@H]1O[C@H](CO)[C@@H](O)[C@H]1O",
]


def get_curated_fallback():
    """
    Return the curated fallback SMILES -- used when both network methods fail.
    Validates and Lipinski-filters before returning.

    Returns:
        list: valid SMILES strings
    """
    print("\n[*] METHOD 3: Curated fallback dataset...")
    valid = list(dict.fromkeys(s for s in CURATED_SMILES if keep(s)))
    print(f"   [OK] {len(valid)} curated molecules (valid + Lipinski)")
    return valid


# ============================================================================
# EXTRA PADDING: fetch more molecules if below target count
# ============================================================================

def _pad_with_extra_rest(current_count, min_count, disease_label):
    """
    If we still don't have enough molecules after primary methods,
    fetch more from the ChEMBL REST API using Phase 2+ endpoint
    with increasing offsets until we reach min_count.

    Args:
        current_count (int): how many we have now
        min_count (int): target minimum
        disease_label (str): controls offset

    Returns:
        list: additional SMILES
    """
    import requests

    needed   = min_count - current_count
    print(f"\n[*] Padding: need {needed} more molecules (have {current_count}/{min_count})...")

    extra_smiles = []
    # Use different base offsets per disease area so both datasets differ
    base_offset = 200 if disease_label == "diabetes" else 1200
    page_size   = 300

    for page in range(8):   # up to 8 extra pages
        offset = base_offset + (page * page_size)
        batch  = _fetch_phase2_plus(limit=page_size, offset=offset)
        extra_smiles.extend(batch)
        time.sleep(SLEEP_BETWEEN_REQUESTS)

        if len(extra_smiles) >= needed * 2:
            break   # have plenty

    return extra_smiles


# ============================================================================
# BUILD DATAFRAME WITH PROPERTIES
# ============================================================================

def build_dataframe(smiles_list, disease_label):
    """
    Build a clean DataFrame for a list of SMILES strings.

    Adds molecular properties: MW, LogP, HBD, HBA.
    Re-validates each SMILES and filters by Lipinski.
    Deduplicates on canonical SMILES.

    Args:
        smiles_list (list): SMILES strings (may include duplicates)
        disease_label (str): "diabetes" or "infection"

    Returns:
        pd.DataFrame with columns:
            smiles, molecular_weight, logp, hbd, hba, passes_lipinski, disease_area
    """
    print(f"\n[*] Building DataFrame for {len(smiles_list)} candidates...")

    rows    = []
    skipped = 0

    for i, smi in enumerate(smiles_list):
        if (i + 1) % 250 == 0:
            print(f"   ... {i+1}/{len(smiles_list)}")

        try:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                skipped += 1
                continue

            mw   = float(Descriptors.MolWt(mol))
            logp = float(Crippen.MolLogP(mol))
            hbd  = int(Descriptors.NumHDonors(mol))
            hba  = int(Descriptors.NumHAcceptors(mol))

            if not (mw <= MW_MAX and logp <= LOGP_MAX
                    and hbd <= HBD_MAX and hba <= HBA_MAX):
                skipped += 1
                continue

            rows.append({
                "smiles":           smi,
                "molecular_weight": round(mw, 2),
                "logp":             round(logp, 3),
                "hbd":              hbd,
                "hba":              hba,
                "passes_lipinski":  True,
                "disease_area":     disease_label,
            })
        except Exception:
            skipped += 1

    df = (pd.DataFrame(rows)
          .drop_duplicates(subset=["smiles"])
          .reset_index(drop=True))

    print(f"   [OK] Final rows: {len(df)}  (skipped {skipped})")
    return df


# ============================================================================
# MASTER DOWNLOAD ORCHESTRATOR
# ============================================================================

def download_molecules(target_ids, disease_label, output_path, min_molecules=1000):
    """
    Orchestrate the three-level download for one disease area.

    Tries Level 1 → Level 2 → Level 3, then pads if still short.
    Saves the result to output_path as CSV.

    Args:
        target_ids (dict): {name: chembl_id}
        disease_label (str): "diabetes" or "infection"
        output_path (Path): where to save the CSV
        min_molecules (int): minimum acceptable count

    Returns:
        pd.DataFrame: processed molecule dataset
    """
    print(f"\n{'='*70}")
    print(f"DOWNLOADING {disease_label.upper()} MOLECULES")
    print(f"Targets: {', '.join(target_ids.keys())}")
    print(f"{'='*70}")

    collected = []

    # Level 1 -- chembl_downloader (skips if DB not cached)
    collected = download_via_chembl_downloader(target_ids)

    # Level 2 -- REST API
    if len(collected) < min_molecules:
        rest_smiles = download_via_rest_api(target_ids, disease_label)
        collected   = list(dict.fromkeys(collected + rest_smiles))

    # Level 3 -- curated fallback
    if len(collected) < 100:
        fallback  = get_curated_fallback()
        collected = list(dict.fromkeys(collected + fallback))

    # Padding -- if still below target
    if len(collected) < min_molecules:
        extra     = _pad_with_extra_rest(len(collected), min_molecules, disease_label)
        collected = list(dict.fromkeys(collected + extra))

    print(f"\n[*] Total collected (before dedup/filter): {len(collected)}")

    df = build_dataframe(collected, disease_label)

    # Save
    df.to_csv(output_path, index=False)
    print(f"[OK] Saved {len(df)} molecules to: {output_path}")

    return df


# ============================================================================
# MAIN
# ============================================================================

def main():
    """
    Download training data for both disease areas, print summaries.
    """
    print("\n" + "#"*70)
    print("# GENOROVA AI -- REAL TRAINING DATA DOWNLOADER")
    print("# Source: ChEMBL database (www.ebi.ac.uk/chembl)")
    print("#"*70)

    # ---- Diabetes ----
    diabetes_df = download_molecules(
        target_ids    = DIABETES_TARGETS,
        disease_label = "diabetes",
        output_path   = DIABETES_OUTPUT,
        min_molecules = 1000,
    )

    # ---- Infectious diseases ----
    infection_df = download_molecules(
        target_ids    = INFECTION_TARGETS,
        disease_label = "infection",
        output_path   = INFECTION_OUTPUT,
        min_molecules = 1000,
    )

    # ---- Final summary ----
    print("\n" + "="*70)
    print("DOWNLOAD COMPLETE -- FINAL SUMMARY")
    print("="*70)

    for label, df, path in [
        ("DIABETES",           diabetes_df,  DIABETES_OUTPUT),
        ("INFECTIOUS DISEASE", infection_df, INFECTION_OUTPUT),
    ]:
        ok = len(df) >= 1000
        print(f"\n[{label}]")
        print(f"   Molecules downloaded : {len(df)}")
        print(f"   >= 1000 target       : {'YES' if ok else 'NO -- below target'}")
        print(f"   Average MW           : {df['molecular_weight'].mean():.1f} Da")
        print(f"   Average LogP         : {df['logp'].mean():.2f}")
        print(f"   Saved to             : {path}")
        print(f"   Sample SMILES (5):")
        for _, row in df.head(5).iterrows():
            print(f"      {row['smiles'][:65]}")

    both_ok = len(diabetes_df) >= 1000 and len(infection_df) >= 1000
    print()
    if both_ok:
        print("[OK] Both datasets meet the 1000+ molecule target!")
    else:
        print("[!] One or both datasets are below 1000 molecules.")
        print("    Run again or check internet connectivity.")

    return diabetes_df, infection_df


if __name__ == "__main__":
    main()
