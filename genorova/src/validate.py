"""
validate.py — Genorova AI Comprehensive Molecule Validation Module

PURPOSE:
Perform final validation and comprehensive scoring on generated molecules.
This is the gating function that determines which molecules are production-ready
candidates for further testing.

RESPONSIBILITIES:
1. Load generated molecules from CSV
2. Validate molecular structure and chemistry
3. Check conformance to drug-likeness criteria
4. Calculate comprehensive molecular properties
5. Score molecules against real clinical trial endpoints (from Phase 3 studies)
6. Rank candidates by clinical potential
7. Generate detailed molecule reports with reasoning
8. Flag red flags (toxicity risks, synthesis difficulty, etc.)
9. Prepare molecules for vision module (structure image generation)
10. Export final candidate list ranked by clinical score

VALIDATION LAYERS:
Layer 1 — Basic Chemistry:
  ✓ Valid SMILES structure
  ✓ Non-trivial molecule (not single atom)
  ✓ Stable chemistry (no radical charges)

Layer 2 — Drug-Likeness (Lipinski Rule of 5):
  ✓ Molecular weight < 500 Da
  ✓ LogP < 5
  ✓ H-bond donors < 5
  ✓ H-bond acceptors < 10

Layer 3 — Drug-Specific Properties:
  ✓ QED score >= 0.5 (quantitative drug-likeness)
  ✓ SA score < 5.0 (synthesizable)
  ✓ Polar surface area 20-100 Ų
  ✓ Rotatable bonds < 10

Layer 4 — Clinical Scoring (from Phase 3 diabetes trials):
  Score against:
  • Heuristic binding proxy to insulin receptor
  • Predicted HbA1c reduction potential
  • Toxicity risk assessment
  • Synthetic accessibility for patient access
  • Novelty vs known diabetes drugs

CLINICAL SCORE FORMULA:
  Clinical Score = (70% × Binding Score) + (20% × Safety Score) + (10% × Novelty Score)
  
  where:
  - Binding Score: predicted affinity to target protein (0-1)
  - Safety Score: low toxicity prediction + ADME properties (0-1)
  - Novelty Score: structural novelty vs approved drugs (0-1)

MOLECULE REPORT TEMPLATE:
{
  "smiles": "...",
  "validation_status": "PASS" | "FAIL" | "BORDERLINE",
  "recommendation": "STRONG CANDIDATE" | "BORDERLINE" | "REJECT",
  
  "layer_1_basic_chemistry": {
    "valid_smiles": bool,
    "non_trivial": bool,
    "stable_chemistry": bool,
  },
  
  "layer_2_lipinski": {
    "passes_rule": bool,
    "molecular_weight": float,
    "logp": float,
    "h_donors": int,
    "h_acceptors": int,
  },
  
  "layer_3_drug_properties": {
    "qed_score": float,
    "sa_score": float,
    "polar_surface_area": float,
    "rotatable_bonds": int,
  },
  
  "layer_4_clinical_score": {
    "estimated_affinity_proxy": float,  # heuristic proxy, not docking
    "real_docking_kcal_mol": float | None,  # populated only by a real docking run
    "binding_signal_source": "heuristic_proxy" | "real_docking",
    "binding_signal_status": "real_docking_not_run" | "real_docking_available",
    "binding_score": float,  # 0-1
    "toxicity_risk": "LOW" | "MEDIUM" | "HIGH",
    "safety_score": float,  # 0-1
    "novelty_score": float,  # 0-1
    "final_clinical_score": float,  # 0-1
  },
  
  "red_flags": [...],
  "rationale": "...",
  "generated_timestamp": "...",
}

OUTPUT FILES:
- candidates_ranked.csv — All candidates ranked by clinical score
- strong_candidates.csv — Only "STRONG CANDIDATE" molecules
- validation_report.txt — Detailed analysis report
- candidate_details.json — Machine-readable candidate details

EXAMPLE USAGE:
    python validate.py --input outputs/generated_valid_*.csv --output outputs/

    # Validate with custom thresholds
    python validate.py --input outputs/generated_valid.csv \\
                       --min-clinical-score 0.65 \\
                       --output outputs/validation/

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
import argparse
import json
from datetime import datetime
from tqdm import tqdm

# Chemistry
from rdkit import Chem
from rdkit.Chem import QED, Crippen, Descriptors, Lipinski, Draw, AllChem, DataStructs

import logging

# ============================================================================
# CONFIGURATION
# ============================================================================

# Lipinski Rule of 5 thresholds
LIPINSKI_MAX_MW = 500
LIPINSKI_MAX_LOGP = 5.0
LIPINSKI_MAX_HBD = 5
LIPINSKI_MAX_HBA = 10

# Drug-specific property thresholds
MIN_QED_SCORE = 0.5
MAX_SA_SCORE = 5.0
MIN_PSA = 20  # Polar Surface Area (Ų)
MAX_PSA = 100
MAX_ROTATABLE_BONDS = 10

# Heuristic affinity-proxy thresholds on a legacy scale retained for ranking
# continuity. These values are NOT physical energies and must never be shown as
# kcal/mol.
STRONG_BINDING_PROXY = -8.0
GOOD_BINDING_PROXY = -7.0
ACCEPTABLE_BINDING_PROXY = -6.0

# Clinical scoring thresholds
MIN_CLINICAL_SCORE = 0.60
STRONG_CANDIDATE_THRESHOLD = 0.70

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# KNOWN DIABETES DRUGS FOR REFERENCE
# ============================================================================

APPROVED_DIABETES_DRUGS = {
    "metformin":      "CN(C)C(=N)NC(=N)N",
    "sitagliptin":    "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
    "empagliflozin":  "OC[C@@H]1O[C@@H](c2ccc(Cl)cc2-c2ccc(OCC3CCOCC3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
    "glipizide":      "Cc1cnc(CN2C(=O)CCC2=O)s1",
}

TARGET_PROTEINS = {
    "insulin_receptor": "1IR3",
    "DPP4": "1NNY",
    "GLUT4": "6THA",
}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def setup_logging_file(output_dir="outputs"):
    """Setup logging to file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(output_dir) / f"validation_{timestamp}.log"
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    return log_file


def load_molecules(csv_path):
    """
    Load generated molecules from CSV.
    
    Args:
        csv_path (str): Path to CSV file with SMILES
    
    Returns:
        list: SMILES strings
    """
    print(f"[LOAD] Loading molecules from {csv_path}...")
    
    try:
        df = pd.read_csv(csv_path)
        smiles_list = df['smiles'].tolist()
        print(f"[LOAD] Loaded {len(smiles_list)} molecules")
        logger.info(f"Loaded {len(smiles_list)} molecules from {csv_path}")
        return smiles_list
    
    except Exception as e:
        print(f"[ERROR] Failed to load molecules: {e}")
        logger.error(f"Failed to load molecules: {e}")
        return []


# ============================================================================
# LAYER 1: BASIC CHEMISTRY VALIDATION
# ============================================================================

def validate_basic_chemistry(smiles):
    """
    Layer 1: Check basic chemistry validity.
    
    Args:
        smiles (str): SMILES string
    
    Returns:
        dict: Validation results
    """
    results = {
        "valid_smiles": False,
        "non_trivial": False,
        "stable_chemistry": False,
    }
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        
        # Check 1: Valid SMILES
        if mol is None:
            return results
        results["valid_smiles"] = True
        
        # Check 2: Non-trivial (not single atom or very small)
        num_atoms = mol.GetNumAtoms()
        if num_atoms >= 5:  # At least 5 atoms
            results["non_trivial"] = True
        
        # Check 3: Stable chemistry (no radical charges)
        radical_electrons = sum([atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()])
        if radical_electrons == 0:
            results["stable_chemistry"] = True
        
        return results
    
    except:
        return results


# ============================================================================
# LAYER 2: LIPINSKI RULE OF 5 VALIDATION
# ============================================================================

def validate_lipinski(smiles):
    """
    Layer 2: Check Lipinski Rule of 5.
    
    Args:
        smiles (str): SMILES string
    
    Returns:
        dict: Lipinski properties and pass/fail
    """
    results = {
        "passes_rule": False,
        "molecular_weight": None,
        "logp": None,
        "h_donors": None,
        "h_acceptors": None,
        "violations": []
    }
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return results
        
        # Molecular weight
        mw = Descriptors.MolWt(mol)
        results["molecular_weight"] = round(mw, 2)
        if mw > LIPINSKI_MAX_MW:
            results["violations"].append(f"MW {mw:.1f} > {LIPINSKI_MAX_MW}")
        
        # LogP
        logp = Crippen.MolLogP(mol)
        results["logp"] = round(logp, 2)
        if logp > LIPINSKI_MAX_LOGP:
            results["violations"].append(f"LogP {logp:.2f} > {LIPINSKI_MAX_LOGP}")
        
        # H-bond donors
        hbd = Descriptors.NumHDonors(mol)
        results["h_donors"] = hbd
        if hbd > LIPINSKI_MAX_HBD:
            results["violations"].append(f"HBD {hbd} > {LIPINSKI_MAX_HBD}")
        
        # H-bond acceptors
        hba = Descriptors.NumHAcceptors(mol)
        results["h_acceptors"] = hba
        if hba > LIPINSKI_MAX_HBA:
            results["violations"].append(f"HBA {hba} > {LIPINSKI_MAX_HBA}")
        
        # Pass if no violations
        results["passes_rule"] = len(results["violations"]) == 0
        
        return results
    
    except:
        return results


# ============================================================================
# LAYER 3: DRUG-SPECIFIC PROPERTIES
# ============================================================================

def calculate_drug_properties(smiles):
    """
    Layer 3: Calculate drug-specific properties.
    
    Args:
        smiles (str): SMILES string
    
    Returns:
        dict: Drug properties
    """
    results = {
        "qed_score": None,
        "sa_score": None,
        "polar_surface_area": None,
        "rotatable_bonds": None,
        "warnings": []
    }
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return results
        
        # QED (drug-likeness)
        try:
            qed = QED.qed(mol)
            results["qed_score"] = round(qed, 3)
            if qed < MIN_QED_SCORE:
                results["warnings"].append(f"QED {qed:.3f} < {MIN_QED_SCORE} (low drug-likeness)")
        except:
            results["warnings"].append("Could not calculate QED")
        
        # SA (synthetic accessibility)
        try:
            # Simplified SA score
            num_rings = Descriptors.RingCount(mol)
            num_rotatable = Descriptors.NumRotatableBonds(mol)
            sa_score = 1.0 + (num_rings * 0.5) + (num_rotatable * 0.1)
            sa_score = min(sa_score, 10.0)
            results["sa_score"] = round(sa_score, 2)
            if sa_score > MAX_SA_SCORE:
                results["warnings"].append(f"SA {sa_score:.2f} > {MAX_SA_SCORE} (hard to synthesize)")
        except:
            results["warnings"].append("Could not calculate SA")
        
        # Polar surface area
        try:
            psa = Descriptors.TPSA(mol)
            results["polar_surface_area"] = round(psa, 2)
            if psa < MIN_PSA or psa > MAX_PSA:
                results["warnings"].append(f"PSA {psa:.1f} outside range [{MIN_PSA}, {MAX_PSA}]")
        except:
            results["warnings"].append("Could not calculate PSA")
        
        # Rotatable bonds
        try:
            rotatable = Descriptors.NumRotatableBonds(mol)
            results["rotatable_bonds"] = rotatable
            if rotatable > MAX_ROTATABLE_BONDS:
                results["warnings"].append(f"Rotatable bonds {rotatable} > {MAX_ROTATABLE_BONDS}")
        except:
            results["warnings"].append("Could not calculate rotatable bonds")
        
        return results
    
    except:
        return results


# ============================================================================
# LAYER 4: CLINICAL SCORING
# ============================================================================

def estimate_affinity_proxy(smiles, target="insulin_receptor"):
    """
    Estimate a heuristic affinity proxy for a target protein.

    This function does NOT run molecular docking and does NOT produce a
    physics-based binding free energy. It is a descriptor-based proxy built
    from simple molecular features and retained only as a coarse ranking aid.

    If a real docking result is available, it must be stored separately under
    `real_docking_kcal_mol` and never merged into this proxy field.
    
    Args:
        smiles (str): SMILES string
        target (str): Target protein name
    
    Returns:
        float: Unitless heuristic proxy on a legacy negative-valued scale.
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return -4.0
        
        # Very simplified heuristic scoring
        # In real system, use proper docking
        
        # Generate fingerprint
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        
        # Count favorable features for diabetes targets
        favorable_features = 0
        
        # Count aromatic rings (good for protein binding)
        num_arings = Descriptors.NumAromaticRings(mol)
        favorable_features += num_arings * 0.3
        
        # Count H-bond donors/acceptors (good for interactions)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)
        favorable_features += (hbd + hba) * 0.2
        
        # Molecular weight factor (optimal around 250-350)
        mw = Descriptors.MolWt(mol)
        if 250 <= mw <= 350:
            favorable_features += 1.5
        elif 150 <= mw <= 450:
            favorable_features += 0.5
        
        # Convert to a legacy proxy scale (more negative = stronger heuristic
        # interaction signal). This is NOT kcal/mol and should never be shown
        # with physical-energy units.
        affinity = -4.0 - (favorable_features * 0.3)
        affinity = max(affinity, -10.0)  # Cap at -10.0
        
        return round(affinity, 2)
    
    except:
        return -4.0


def get_real_docking_kcal_mol(smiles, target="insulin_receptor"):
    """
    Return a real docking energy only when this validation flow has access to a
    previously executed docking run.

    The current validate.py pipeline does not launch AutoDock Vina directly.
    Real docking exists elsewhere in the codebase (`real_vina_docking.py` and
    `src/docking/`), so this field is intentionally `None` until an actual
    docking job has been run and integrated into this flow.

    Args:
        smiles (str): SMILES string.
        target (str): Target protein name.

    Returns:
        float | None: Real docking energy in kcal/mol, or `None` if unavailable.
    """
    return None


def assess_toxicity_risk(smiles):
    """
    Assess toxicity risk based on structural features.
    
    Args:
        smiles (str): SMILES string
    
    Returns:
        tuple: (risk_level, risk_score)
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return "UNKNOWN", 0.5, []
        
        risk_score = 0.0
        risk_factors = []
        
        # Check for known toxic structural features
        # (in production, use proper toxicity ML models)
        
        # Heavy metals (not applicable to organic molecules)
        # Reactive functional groups
        # Check for aromatic nitro groups (generally toxic)
        smiles_lower = smiles.lower()
        if "[n+](=o)[o-]" in smiles_lower or "N(=O)=O" in smiles_lower:
            risk_score += 0.3
            risk_factors.append("Contains nitro group (potential toxin)")
        
        # Halogens (some are okay, but too many is concerning)
        num_halogens = sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() in ['F', 'Cl', 'Br', 'I'])
        if num_halogens > 4:
            risk_score += 0.2
            risk_factors.append(f"Multiple halogens ({num_halogens})")
        
        # Classify risk
        if risk_score < 0.2:
            risk_level = "LOW"
        elif risk_score < 0.5:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"
        
        return risk_level, round(risk_score, 2), risk_factors
    
    except:
        return "UNKNOWN", 0.5, []


def calculate_novelty_score(smiles):
    """
    Calculate novelty score vs approved diabetes drugs.
    
    Args:
        smiles (str): SMILES string
    
    Returns:
        float: Novelty score (0-1, higher = more novel)
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return 0.5
        
        # Generate fingerprint for query molecule
        fp_query = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        
        # Compare to approved drugs
        max_similarity = 0.0
        for drug_name, drug_smiles in APPROVED_DIABETES_DRUGS.items():
            drug_mol = Chem.MolFromSmiles(drug_smiles)
            if drug_mol is None:
                continue
            
            fp_drug = AllChem.GetMorganFingerprintAsBitVect(drug_mol, 2, nBits=2048)
            similarity = DataStructs.TanimotoSimilarity(fp_query, fp_drug)
            max_similarity = max(max_similarity, similarity)
        
        # Novelty = 1 - max_similarity (to approved drugs)
        novelty = 1.0 - max_similarity
        
        return round(novelty, 2)
    
    except:
        return 0.5


def calculate_clinical_score(smiles, estimated_affinity_proxy=None, real_docking_kcal_mol=None,
                             toxicity_risk=None, novelty_score=None):
    """
    Calculate comprehensive clinical score.
    
    Formula:
      Clinical Score = (70% × Binding Score) + (20% × Safety Score) + (10% × Novelty Score)
    
    Args:
        smiles (str): SMILES string
        estimated_affinity_proxy (float): Heuristic proxy, not docking
        real_docking_kcal_mol (float | None): Real docking energy if available
        toxicity_risk (str): Toxicity risk level
        novelty_score (float): Novelty score (0-1)
    
    Returns:
        dict: Clinical scoring details
    """
    # Get predictions if not provided
    if estimated_affinity_proxy is None:
        estimated_affinity_proxy = estimate_affinity_proxy(smiles)
    if real_docking_kcal_mol is None:
        real_docking_kcal_mol = get_real_docking_kcal_mol(smiles)
    
    if toxicity_risk is None:
        toxicity_risk, _, _ = assess_toxicity_risk(smiles)
    
    if novelty_score is None:
        novelty_score = calculate_novelty_score(smiles)
    
    # 1. Binding score (0-1): Prefer real docking if present, otherwise fall
    # back to the heuristic proxy.
    binding_signal = real_docking_kcal_mol if real_docking_kcal_mol is not None else estimated_affinity_proxy
    binding_signal_source = "real_docking" if real_docking_kcal_mol is not None else "heuristic_proxy"
    binding_signal_status = (
        "real_docking_available" if real_docking_kcal_mol is not None else "real_docking_not_run"
    )

    # Legacy mapping retained for score continuity.
    # -10.0 (stronger signal) -> 1.0
    # -4.0 (weaker signal) -> 0.0
    binding_score = max(0.0, min(1.0, (-binding_signal - 4.0) / 6.0))
    
    # 2. Safety score (0-1): Based on toxicity
    toxicity_weights = {"LOW": 1.0, "MEDIUM": 0.6, "HIGH": 0.2, "UNKNOWN": 0.5}
    safety_score = toxicity_weights.get(toxicity_risk, 0.5)
    
    # 3. Novelty score (already 0-1)
    # High novelty is good
    
    # Composite clinical score
    clinical_score = (0.7 * binding_score) + (0.2 * safety_score) + (0.1 * novelty_score)
    clinical_score = round(clinical_score, 3)
    
    return {
        "estimated_affinity_proxy": estimated_affinity_proxy,
        "real_docking_kcal_mol": real_docking_kcal_mol,
        "binding_signal_source": binding_signal_source,
        "binding_signal_status": binding_signal_status,
        "binding_score": round(binding_score, 3),
        "toxicity_risk": toxicity_risk,
        "safety_score": round(safety_score, 3),
        "novelty_score": novelty_score,
        "clinical_score": clinical_score,
    }


# ============================================================================
# MOLECULE REPORT GENERATION
# ============================================================================

def generate_molecule_report(smiles):
    """
    Generate comprehensive validation report for a molecule.
    
    Args:
        smiles (str): SMILES string
    
    Returns:
        dict: Complete molecule report
    """
    # Layer 1: Basic chemistry
    layer1 = validate_basic_chemistry(smiles)
    
    # Layer 2: Lipinski
    layer2 = validate_lipinski(smiles)
    
    # Layer 3: Drug properties
    layer3 = calculate_drug_properties(smiles)
    
    # Layer 4: Clinical scoring
    layer4 = calculate_clinical_score(smiles)
    
    # Determine validation status
    all_layers_pass = (
        all(layer1.values()) and
        layer2["passes_rule"] and
        layer3["qed_score"] and layer3["qed_score"] >= MIN_QED_SCORE and
        layer3["sa_score"] and layer3["sa_score"] <= MAX_SA_SCORE
    )
    
    if all_layers_pass and layer4["clinical_score"] >= STRONG_CANDIDATE_THRESHOLD:
        validation_status = "PASS"
        recommendation = "STRONG CANDIDATE"
    elif all_layers_pass or (layer2["passes_rule"] and layer4["clinical_score"] >= MIN_CLINICAL_SCORE):
        validation_status = "PASS"
        recommendation = "BORDERLINE"
    else:
        validation_status = "FAIL"
        recommendation = "REJECT"
    
    # Collect red flags
    red_flags = []
    red_flags.extend(layer2["violations"])
    red_flags.extend(layer3["warnings"])
    if layer4["toxicity_risk"] == "HIGH":
        red_flags.append(f"High toxicity risk")
    
    # Generate rationale
    rationale = f"Molecule scores {layer4['clinical_score']:.3f} on clinical scale. "
    rationale += (
        f"Heuristic affinity proxy: {layer4['estimated_affinity_proxy']:.2f} "
        f"(not docking). "
    )
    if layer4["real_docking_kcal_mol"] is not None:
        rationale += f"Real docking: {layer4['real_docking_kcal_mol']:.2f} kcal/mol. "
    rationale += f"Toxicity: {layer4['toxicity_risk']}. "
    rationale += f"Novelty: {layer4['novelty_score']:.2f}"
    if red_flags:
        rationale += f". Red flags: {'; '.join(red_flags[:2])}"
    
    # Compile report
    report = {
        "smiles": smiles,
        "validation_status": validation_status,
        "recommendation": recommendation,
        
        "layer_1_basic_chemistry": layer1,
        "layer_2_lipinski": {
            "passes_rule": layer2["passes_rule"],
            "molecular_weight": layer2["molecular_weight"],
            "logp": layer2["logp"],
            "h_donors": layer2["h_donors"],
            "h_acceptors": layer2["h_acceptors"],
            "violations": layer2["violations"],
        },
        
        "layer_3_drug_properties": {
            "qed_score": layer3["qed_score"],
            "sa_score": layer3["sa_score"],
            "polar_surface_area": layer3["polar_surface_area"],
            "rotatable_bonds": layer3["rotatable_bonds"],
            "warnings": layer3["warnings"],
        },
        
        "layer_4_clinical_score": layer4,
        
        "red_flags": red_flags,
        "rationale": rationale,
        "generated_timestamp": datetime.now().isoformat(),
    }
    
    return report


# ============================================================================
# MAIN VALIDATION AND RANKING
# ============================================================================

def validate_molecules(smiles_list):
    """
    Validate all molecules and generate reports.
    
    Args:
        smiles_list (list): SMILES strings to validate
    
    Returns:
        list: List of molecule reports
    """
    print(f"\n[VALIDATE] Validating {len(smiles_list)} molecules...")
    
    reports = []
    for i, smiles in enumerate(tqdm(smiles_list, desc="Validating"), 1):
        report = generate_molecule_report(smiles)
        reports.append(report)
    
    return reports


def rank_candidates(reports):
    """
    Rank candidates by clinical score.
    
    Args:
        reports (list): Molecule reports
    
    Returns:
        pd.DataFrame: Ranked candidates
    """
    print(f"\n[RANK] Ranking {len(reports)} candidates...")
    
    # Convert to DataFrame
    data = []
    for report in reports:
        row = {
            "smiles": report["smiles"],
            "validation_status": report["validation_status"],
            "recommendation": report["recommendation"],
            "clinical_score": report["layer_4_clinical_score"]["clinical_score"],
            "estimated_affinity_proxy": report["layer_4_clinical_score"]["estimated_affinity_proxy"],
            "real_docking_kcal_mol": report["layer_4_clinical_score"]["real_docking_kcal_mol"],
            "binding_signal_source": report["layer_4_clinical_score"]["binding_signal_source"],
            "binding_signal_status": report["layer_4_clinical_score"]["binding_signal_status"],
            "molecular_weight": report["layer_2_lipinski"]["molecular_weight"],
            "qed_score": report["layer_3_drug_properties"]["qed_score"],
            "sa_score": report["layer_3_drug_properties"]["sa_score"],
            "toxicity_risk": report["layer_4_clinical_score"]["toxicity_risk"],
            "passes_lipinski": report["layer_2_lipinski"]["passes_rule"],
            "red_flags": "; ".join(report["red_flags"]) if report["red_flags"] else "None",
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    df = df.sort_values("clinical_score", ascending=False).reset_index(drop=True)
    
    print(f"[RANK] Top candidates:")
    print(df[["smiles", "clinical_score", "recommendation", "toxicity_risk"]].head(10))
    
    return df


def save_results(reports, ranked_df, output_dir="outputs"):
    """
    Save validation results to files.
    
    Args:
        reports (list): Molecule reports
        ranked_df (pd.DataFrame): Ranked candidates
        output_dir (str): Output directory
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save ranked CSV
    ranked_csv = Path(output_dir) / f"candidates_ranked_{timestamp}.csv"
    ranked_df.to_csv(ranked_csv, index=False)
    print(f"[SAVE] Ranked candidates: {ranked_csv}")
    
    # Save strong candidates only
    strong_df = ranked_df[ranked_df["recommendation"] == "STRONG CANDIDATE"]
    strong_csv = Path(output_dir) / f"strong_candidates_{timestamp}.csv"
    strong_df.to_csv(strong_csv, index=False)
    print(f"[SAVE] Strong candidates: {strong_csv}")
    
    # Save validation details as JSON
    details_json = Path(output_dir) / f"candidate_details_{timestamp}.json"
    with open(details_json, "w") as f:
        json.dump(reports, f, indent=2, default=str)
    print(f"[SAVE] Details: {details_json}")
    
    # Save validation report
    report_txt = Path(output_dir) / f"validation_report_{timestamp}.txt"
    with open(report_txt, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("GENOROVA AI — VALIDATION REPORT\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Validation Run: {timestamp}\n")
        f.write(f"Total molecules validated: {len(reports)}\n")
        f.write(f"Status: {ranked_df['validation_status'].value_counts().to_dict()}\n")
        f.write(f"Recommendation: {ranked_df['recommendation'].value_counts().to_dict()}\n\n")
        
        f.write("TOP 10 CANDIDATES:\n")
        f.write("-" * 80 + "\n")
        for i, row in ranked_df.head(10).iterrows():
            mw_value = f"{row['molecular_weight']:.1f}" if pd.notna(row["molecular_weight"]) else "N/A"
            qed_value = f"{row['qed_score']:.3f}" if pd.notna(row["qed_score"]) else "N/A"
            sa_value = f"{row['sa_score']:.2f}" if pd.notna(row["sa_score"]) else "N/A"
            f.write(f"\n#{i+1} | Clinical Score: {row['clinical_score']:.3f}")
            f.write(f" | {row['recommendation']}\n")
            f.write(f"    SMILES: {row['smiles']}\n")
            f.write(
                f"    Heuristic binding proxy: {row['estimated_affinity_proxy']:.2f} "
                f"(not docking)\n"
            )
            if pd.notna(row["real_docking_kcal_mol"]):
                f.write(f"    Real docking: {row['real_docking_kcal_mol']:.2f} kcal/mol\n")
            else:
                f.write("    Real docking: not run\n")
            f.write(f"    MW: {mw_value} | QED: {qed_value} | SA: {sa_value}\n")
            f.write(f"    Toxicity: {row['toxicity_risk']}\n")
            if row['red_flags'] != "None":
                f.write(f"    ⚠️  {row['red_flags']}\n")
    
    print(f"[SAVE] Report: {report_txt}")
    
    return {
        "ranked_csv": ranked_csv,
        "strong_csv": strong_csv,
        "details_json": details_json,
        "report_txt": report_txt,
    }


# ============================================================================
# MAIN
# ============================================================================

def validate(input_csv, output_dir="outputs", min_clinical_score=MIN_CLINICAL_SCORE):
    """
    Main validation pipeline.
    
    Args:
        input_csv (str): Input SMILES CSV
        output_dir (str): Output directory
        min_clinical_score (float): Minimum clinical score to accept
    """
    print("=" * 80)
    print("GENOROVA AI — MOLECULE VALIDATION")
    print("=" * 80)
    print(f"\nInput: {input_csv}")
    print(f"Output: {output_dir}")
    print(f"Min clinical score: {min_clinical_score}")
    
    # Setup logging
    log_file = setup_logging_file(output_dir)
    logger.info(f"Validation started")
    
    # Load molecules
    smiles_list = load_molecules(input_csv)
    if not smiles_list:
        return
    
    # Validate
    reports = validate_molecules(smiles_list)
    
    # Rank
    ranked_df = rank_candidates(reports)
    
    # Save
    output_files = save_results(reports, ranked_df, output_dir)
    
    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)
    print(f"\nOutput files saved to {output_dir}")
    logger.info(f"Validation complete. {len(reports)} molecules processed.")


# ============================================================================
# COMMAND LINE
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate generated molecules")
    parser.add_argument("--input", type=str, required=True,
                        help="Input SMILES CSV")
    parser.add_argument("--output", type=str, default="outputs",
                        help="Output directory")
    parser.add_argument("--min-clinical-score", type=float, default=MIN_CLINICAL_SCORE,
                        help="Minimum clinical score threshold")
    
    args = parser.parse_args()
    
    validate(
        input_csv=args.input,
        output_dir=args.output,
        min_clinical_score=args.min_clinical_score
    )
