"""
Genorova AI — Validation: ADMET and Safety Module
==================================================

PURPOSE:
Predict potential adverse effects and pharmacokinetic liabilities for a
generated molecule, at a structural-alert / descriptor level.

PREDICTIONS PROVIDED:
  1. Hepatotoxicity / DILI (Drug-Induced Liver Injury) risk
  2. hERG potassium channel inhibition risk (cardiac safety)
  3. CYP450 enzyme interaction risk (drug-drug interactions)

IMPORTANT — READ BEFORE INTERPRETING RESULTS:
  ALL predictions in this module are HEURISTIC PROXIES derived from:
    a. Known structural alerts published in the literature
    b. Simple molecular descriptor thresholds
    c. Lipophilicity/polarity rules of thumb

  They are NOT validated QSAR models and have NOT been benchmarked against
  experimental assay data within Genorova.  They provide a SCREENING-LEVEL
  signal only.  A "low risk" result does NOT confirm safety.

  Before any decision is made, results must be confirmed by:
    - Established QSAR tools (e.g. pkCSM, SwissADME, ADMETLab)
    - In-vitro assays (e.g. LDH assay for hepatotoxicity, hERG patch-clamp)
    - Regulatory toxicology studies

  Every output is tagged with method="structural_alerts_heuristic" or
  method="rdkit_descriptors_proxy" so downstream code can distinguish this
  from experimentally validated predictions.

PUBLIC API:
  build_admet_evidence(admet_result) -> dict
  run_admet_evaluation(smiles) -> dict  (fields match ADMETResult)

REFERENCES FOR STRUCTURAL ALERTS:
  - Brenk et al. (2008) ChemMedChem — reactive / undesirable groups
  - Walters & Murcko (2002) Drug Disc Today — PAIN/toxicophore rules
  - Redfern et al. (2003) Cardiovasc Res — hERG structural correlates
  - Pelkonen et al. (2008) Drug Metab Rev — CYP450 induction patterns

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

from __future__ import annotations

import contextlib
import io
import re
import warnings
from typing import List, Optional, Tuple

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# Lazy RDKit loader
# ---------------------------------------------------------------------------

_RDKIT_LOADED = None
_Chem         = None
_Descriptors  = None
_Crippen      = None
_AllChem      = None


def _try_load_rdkit() -> bool:
    """Load RDKit once and cache the result."""
    global _RDKIT_LOADED, _Chem, _Descriptors, _Crippen, _AllChem

    if _RDKIT_LOADED is not None:
        return _RDKIT_LOADED

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            from rdkit import Chem as _c
            from rdkit.Chem import Descriptors as _d
            from rdkit.Chem import Crippen as _cr
            from rdkit.Chem import AllChem as _ac
            from rdkit import RDLogger as _rl
            _rl.DisableLog("rdApp.*")

        _Chem        = _c
        _Descriptors = _d
        _Crippen     = _cr
        _AllChem     = _ac
        _RDKIT_LOADED = True
        return True

    except Exception:
        _RDKIT_LOADED = False
        return False


# ---------------------------------------------------------------------------
# Structural alert definitions
# ---------------------------------------------------------------------------

# Each alert is (smarts_or_pattern, description).
# SMARTS patterns are used when RDKit is available.
# Regex fallback patterns are used on the raw SMILES string when RDKit is not.

# --- DILI / hepatotoxicity alerts ---
_DILI_ALERTS_SMARTS = [
    ("[NX3;H0;!$(NC=O)][NX3;H0;!$(NC=O)]",  "Hydrazine / diamine — metabolic activation risk"),
    ("[c][N+](=O)[O-]",                       "Aromatic nitro group — CYP-mediated nitroreduction"),
    ("N(=O)=O",                               "Nitro group — hepatotoxic potential"),
    ("[S;X2][c]",                             "Aryl-sulfide — reactive metabolite risk"),
    ("C(=O)Cl",                               "Acyl chloride — reactive electrophile"),
    ("C(=O)Br",                               "Acyl bromide — reactive electrophile"),
    ("[c]Cl",                                  "Aryl chloride — potential for reactive metabolites"),
    ("O=C1OC(=O)[!#1]1",                      "Anhydride — highly reactive"),
    ("[N;X3;H0](=O)",                          "N-oxide — CYP-mediated toxicity"),
    ("[S;X4](=O)(=O)[OH]",                    "Sulfonic acid — potential irritant"),
]

_DILI_ALERTS_REGEX = [
    (r"N\(=O\)=O",        "Nitro group"),
    (r"\[N\+\]\(=O\)\[O-\]", "Nitro group (charged form)"),
    (r"C\(=O\)Cl",        "Acyl chloride"),
    (r"C\(=O\)Br",        "Acyl bromide"),
    (r"NN",               "Hydrazine-like moiety"),
    (r"O=C1OC\(=O\)",     "Anhydride"),
]

# --- hERG alerts ---
# hERG blockers commonly have: tertiary/secondary amine + aromatic ring(s) + MW > 300
# Based on Redfern et al. and empirical SAR patterns.
_HERG_ALERTS_SMARTS = [
    ("[nX3;H0]",           "Basic aromatic nitrogen — common in hERG blockers"),
    ("[NX3;H0;$(NC~c)]",   "Tertiary amine adjacent to aromatic ring"),
    ("[NX3;H0;$(N(~c)(~c))]", "Diarylamine — hERG risk"),
    ("c1ccccc1",           "Phenyl ring (risk increases with count ≥ 3)"),
]

_HERG_ALERTS_REGEX = [
    (r"N\(C\)\(C\)C",  "Tertiary amine (NMe3-like)"),
    (r"N\(C\)C",       "Secondary/tertiary amine"),
    (r"n\d",           "Aromatic nitrogen in ring"),
]

# --- CYP450 alerts ---
# CYP3A4: many heteroaromatics, large molecules
# CYP2D6: basic nitrogen + aromatic ring at correct geometry
# CYP2C9: acidic group (COOH, SO3H, tetrazole) + aromatic
_CYP_ALERTS_SMARTS = [
    ("[nX3;H0]c",          "Aromatic N in heterocycle — CYP3A4 substrate pattern"),
    ("[NX3;H0]c",          "Amine-aromatic — CYP2D6 substrate pattern"),
    ("[CX3](=O)[OH]",      "Carboxylic acid — CYP2C9 substrate"),
    ("c1cc(F)ccc1",        "Para-fluorophenyl — CYP2C9 substrate"),
    ("O=S(=O)([OH])",      "Sulfonamide acid — CYP2C9 substrate"),
    ("[#7]-[#7]",          "N-N bond — CYP induction potential"),
    ("c1cnc(nc1)",         "Pyrimidine — common CYP3A4 inhibitor scaffold"),
]

_CYP_ALERTS_REGEX = [
    (r"C\(=O\)O",    "Ester/acid — CYP2C9 substrate"),
    (r"c1ccncc1",    "Pyridine — CYP3A4 substrate"),
    (r"c1cnccn1",    "Pyrimidine — CYP3A4 substrate"),
    (r"N\(C\)C",     "Tertiary amine — CYP2D6/3A4 substrate"),
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _check_smarts_alerts(
    mol,
    alerts: List[Tuple[str, str]],
    label: str,
) -> List[str]:
    """
    Match a list of SMARTS patterns against a RDKit mol object.
    Returns a list of human-readable alert descriptions for every match.
    """
    matched = []
    for smarts, description in alerts:
        try:
            pattern = _Chem.MolFromSmarts(smarts)
            if pattern is not None and mol.HasSubstructMatch(pattern):
                matched.append(description)
        except Exception:
            pass
    return matched


def _check_regex_alerts(
    smiles: str,
    alerts: List[Tuple[str, str]],
) -> List[str]:
    """
    Fallback: match patterns against the raw SMILES string using regex.
    Less precise than SMARTS — may produce false positives/negatives.
    """
    matched = []
    for pattern, description in alerts:
        if re.search(pattern, smiles):
            matched.append(f"{description} (regex match — RDKit unavailable)")
    return matched


def _risk_level_from_score(score: float) -> str:
    """Convert a 0–1 risk score to a categorical level."""
    if score < 0.25:
        return "low"
    if score < 0.55:
        return "medium"
    return "high"


def _not_checked_result(reason: str) -> dict:
    """Return a consistent record when an ADMET check could not be completed."""
    return {
        "level": "unknown",
        "score": None,
        "alerts": [reason],
        "method": "not_run_invalid_smiles",
        "checked": False,
    }


# ---------------------------------------------------------------------------
# 1.  Hepatotoxicity / DILI
# ---------------------------------------------------------------------------

def predict_hepatotoxicity(smiles: str) -> dict:
    """
    Predict liver toxicity (DILI) risk from structural alerts and
    lipophilicity-based rules.

    Risk factors considered:
      - Known reactive functional groups (nitro, acyl halides, anhydrides)
      - Very high lipophilicity (LogP > 5) → accumulation in liver
      - Very high molecular weight (> 600 Da) → biliary excretion overload
      - Mitochondrial toxicity patterns (electron-rich aromatics)

    Returns a dict compatible with RiskLevel fields, plus ``method`` clearly
    stating this is a heuristic proxy.
    """
    print(f"   [DILI] Assessing hepatotoxicity for {smiles[:50]}...")

    alerts: List[str] = []
    score = 0.0

    rdkit_ok = _try_load_rdkit()

    if rdkit_ok:
        mol = _Chem.MolFromSmiles(smiles)
        if mol is None:
            return _not_checked_result("Invalid SMILES")

        # Check SMARTS alerts
        alerts.extend(_check_smarts_alerts(mol, _DILI_ALERTS_SMARTS, "DILI"))

        # Lipophilicity rule: very high LogP correlates with DILI incidence
        try:
            logp = _Crippen.MolLogP(mol)
            if logp > 5.0:
                alerts.append(f"Very high LogP ({logp:.1f}) — hepatic accumulation risk")
                score += 0.20
            elif logp > 4.0:
                score += 0.05

            mw = _Descriptors.MolWt(mol)
            if mw > 600:
                alerts.append(f"High MW ({mw:.0f} Da) — biliary excretion / hepatic load")
                score += 0.10

            # Aromatic ring count — poly-aromatics → reactive metabolites
            n_arom = _Descriptors.NumAromaticRings(mol)
            if n_arom >= 4:
                alerts.append(f"Multiple aromatic rings ({n_arom}) — reactive metabolite risk")
                score += 0.15
            elif n_arom >= 3:
                score += 0.05

        except Exception:
            pass

        method = "structural_alerts_heuristic + rdkit_descriptors_proxy"

    else:
        alerts.extend(_check_regex_alerts(smiles, _DILI_ALERTS_REGEX))
        method = "regex_structural_alerts_only (rdkit_unavailable)"

    # Structural alert count → risk score
    score += min(len(alerts) * 0.15, 0.60)
    score  = round(min(1.0, score), 3)
    level  = _risk_level_from_score(score)

    print(f"   [DILI] level={level}, score={score}, alerts={len(alerts)}")
    return {
        "level":   level,
        "score":   score,
        "alerts":  alerts,
        "method":  method,
        "checked": True,
    }


# ---------------------------------------------------------------------------
# 2.  hERG inhibition risk
# ---------------------------------------------------------------------------

def predict_herg_inhibition(smiles: str) -> dict:
    """
    Predict hERG potassium channel inhibition risk.

    hERG inhibitors share a pharmacophore:
      - Lipophilic (LogP typically > 2)
      - Basic nitrogen (pKa > 7 — protonated at physiological pH)
      - Flat aromatic system(s)
      - MW typically 300–700 Da

    Cardiotoxicity risk (QT prolongation → arrhythmia) rises sharply when
    all three features are present simultaneously.

    This prediction uses structural alerts + descriptor rules.  It does NOT
    run a trained hERG QSAR model.  A negative result does NOT guarantee
    cardiac safety.
    """
    print(f"   [hERG] Assessing hERG risk for {smiles[:50]}...")

    alerts: List[str] = []
    score  = 0.0
    rdkit_ok = _try_load_rdkit()

    if rdkit_ok:
        mol = _Chem.MolFromSmiles(smiles)
        if mol is None:
            return _not_checked_result("Invalid SMILES")

        try:
            logp = _Crippen.MolLogP(mol)
            mw   = _Descriptors.MolWt(mol)
            hba  = _Descriptors.NumHAcceptors(mol)
            n_arom = _Descriptors.NumAromaticRings(mol)

            # Count basic nitrogens (proxy: aliphatic/aromatic N that can be protonated)
            n_basic_N = sum(
                1 for atom in mol.GetAtoms()
                if atom.GetSymbol() == "N"
                and atom.GetFormalCharge() >= 0
                and not any(
                    bond.GetBondTypeAsDouble() == 2.0
                    for bond in atom.GetBonds()
                )
            )

            # Core hERG pharmacophore: basic N + aromatic + lipophilic
            if n_basic_N >= 1 and n_arom >= 1 and logp > 2.0:
                score += 0.35
                alerts.append(
                    f"Core hERG pharmacophore: basic N ({n_basic_N}) + "
                    f"aromatics ({n_arom}) + LogP {logp:.1f}"
                )

            # Additional risk from lipophilicity
            if logp > 4.5:
                score += 0.20
                alerts.append(f"Very high LogP ({logp:.1f}) — hERG risk amplified")
            elif logp > 3.5:
                score += 0.08

            # MW in typical hERG blocker range
            if 300 <= mw <= 700:
                score += 0.10
                alerts.append(f"MW {mw:.0f} Da in typical hERG blocker range")

            # Multiple aromatic rings (flat, can intercalate in channel)
            if n_arom >= 3:
                score += 0.15
                alerts.append(f"{n_arom} aromatic rings — can occupy hydrophobic hERG pocket")
            elif n_arom == 2:
                score += 0.05

        except Exception:
            pass

        method = "structural_pharmacophore_heuristic + rdkit_descriptors_proxy"

    else:
        alerts.extend(_check_regex_alerts(smiles, _HERG_ALERTS_REGEX))
        method = "regex_pharmacophore_heuristic (rdkit_unavailable)"

    score  = round(min(1.0, score), 3)
    level  = _risk_level_from_score(score)

    print(f"   [hERG] level={level}, score={score}, alerts={len(alerts)}")
    return {
        "level":  level,
        "score":  score,
        "alerts": alerts,
        "method": method,
        "checked": True,
    }


# ---------------------------------------------------------------------------
# 3.  CYP450 interaction risk
# ---------------------------------------------------------------------------

def predict_cyp_interaction(smiles: str) -> dict:
    """
    Predict the risk of CYP450 enzyme interaction (inhibition or induction).

    Three major CYP isoforms are assessed:
      CYP3A4 : metabolises ~50 % of drugs; heterocyclic N-donors are substrates
      CYP2D6 : metabolises ~25 % of drugs; basic N near aromatic ring
      CYP2C9 : metabolises ~15 % of drugs; acidic groups + aromatic ring

    High CYP interaction risk suggests potential for:
      - Altered drug exposure if given with other medications
      - Metabolic activation to reactive/toxic intermediates

    Returns a composite risk assessment.  Individual isoform notes are
    included in 'alerts'.
    """
    print(f"   [CYP] Assessing CYP450 interaction for {smiles[:50]}...")

    alerts: List[str] = []
    score  = 0.0
    rdkit_ok = _try_load_rdkit()

    if rdkit_ok:
        mol = _Chem.MolFromSmiles(smiles)
        if mol is None:
            return _not_checked_result("Invalid SMILES")

        # SMARTS-based CYP alerts
        cyp_hits = _check_smarts_alerts(mol, _CYP_ALERTS_SMARTS, "CYP")
        alerts.extend(cyp_hits)

        try:
            logp     = _Crippen.MolLogP(mol)
            mw       = _Descriptors.MolWt(mol)
            n_arom   = _Descriptors.NumAromaticRings(mol)
            n_rot    = _Descriptors.NumRotatableBonds(mol)
            n_hetero = _Descriptors.NumHeteroatoms(mol)

            # Large, lipophilic, flexible molecules → CYP3A4 substrate / inhibitor
            if mw > 450 and logp > 3.0 and n_rot > 5:
                score += 0.20
                alerts.append(
                    f"Large ({mw:.0f} Da) lipophilic ({logp:.1f}) flexible molecule — "
                    "typical CYP3A4 substrate pattern"
                )

            # Multiple heteroatoms → many potential coordination sites
            if n_hetero >= 6:
                score += 0.15
                alerts.append(f"{n_hetero} heteroatoms — potential CYP coordination")
            elif n_hetero >= 4:
                score += 0.05

            # Strong heme coordinators: imidazole, pyridine, triazole
            strong_coord_patterns = [
                ("c1ccnc1",  "Pyridine — known CYP3A4 inhibitor motif"),
                ("c1ncc[nH]1", "Imidazole — strong CYP heme coordinator"),
                ("c1nncn1",  "Triazole — strong CYP heme coordinator"),
                ("c1cncn1",  "Imidazole-like — CYP coordination"),
            ]
            for smarts_str, desc in strong_coord_patterns:
                try:
                    pat = _Chem.MolFromSmarts(smarts_str)
                    if pat is not None and mol.HasSubstructMatch(pat):
                        score += 0.25
                        alerts.append(desc)
                        break  # one strong coordinator is enough
                except Exception:
                    pass

        except Exception:
            pass

        method = "structural_alerts_heuristic + rdkit_descriptors_proxy"

    else:
        alerts.extend(_check_regex_alerts(smiles, _CYP_ALERTS_REGEX))
        method = "regex_structural_alerts_only (rdkit_unavailable)"

    score  = round(min(1.0, score), 3)
    level  = _risk_level_from_score(score)

    print(f"   [CYP] level={level}, score={score}, alerts={len(alerts)}")
    return {
        "level":  level,
        "score":  score,
        "alerts": alerts,
        "method": method,
        "checked": True,
    }


# ---------------------------------------------------------------------------
# 4.  Composite safety score and flag
# ---------------------------------------------------------------------------

def _compute_overall_flag(
    dili_level: str,
    herg_level: str,
    cyp_level: str,
) -> Tuple[str, float]:
    """
    Combine three individual risk levels into one overall safety flag.

    Logic:
      - Any HIGH risk     → "likely_unsafe"
      - Any MEDIUM risk   → "caution"
      - All LOW risks     → "likely_safe"
      - Any UNKNOWN       → "unknown" (unless others are HIGH/MEDIUM)

    Returns (flag, safety_score) where safety_score is 0.0–1.0,
    1.0 = completely safe (heuristic).
    """
    level_weight = {"low": 0.0, "medium": 0.5, "high": 1.0, "unknown": 0.3}
    w_dili = level_weight.get(dili_level, 0.3)
    w_herg = level_weight.get(herg_level, 0.3)
    w_cyp  = level_weight.get(cyp_level, 0.3)

    # Weighted average (DILI and hERG weighted slightly higher — more life-threatening)
    composite_risk = 0.40 * w_dili + 0.35 * w_herg + 0.25 * w_cyp
    safety_score   = round(1.0 - composite_risk, 3)

    if "high" in (dili_level, herg_level, cyp_level):
        flag = "likely_unsafe"
    elif "medium" in (dili_level, herg_level, cyp_level):
        flag = "caution"
    elif "unknown" in (dili_level, herg_level, cyp_level):
        flag = "unknown"
    else:
        flag = "likely_safe"

    return flag, safety_score


def _checked_methods(*risks: dict) -> List[str]:
    """Return the methods for ADMET checks that actually ran."""
    return [
        str(risk.get("method", "")).strip()
        for risk in risks
        if risk.get("checked", False)
    ]


def _admet_evidence_level(*risks: dict) -> str:
    """Summarize how strong the current ADMET evidence is."""
    methods = _checked_methods(*risks)
    if not methods or not all(risk.get("checked", False) for risk in risks):
        return "incomplete_heuristic_proxy"
    if any("regex" in method for method in methods):
        return "heuristic_proxy_regex_fallback"
    if any("rdkit" in method for method in methods):
        return "heuristic_proxy_with_rdkit_descriptors"
    return "heuristic_proxy_structural_alerts"


def _overall_safety_method(*risks: dict) -> str:
    """Name the canonical method used for the final safety label."""
    methods = _checked_methods(*risks)
    if not methods or not all(risk.get("checked", False) for risk in risks):
        return "incomplete_heuristic_alert_consensus"
    if any("regex" in method for method in methods):
        return "heuristic_alert_consensus_with_regex_fallback"
    if any("rdkit" in method for method in methods):
        return "heuristic_alert_consensus_with_rdkit_descriptors"
    return "heuristic_alert_consensus"


def _method_for_people(method: str, *, checked: bool) -> str:
    """Turn an internal ADMET method string into simple reviewer-facing language."""
    if not checked or method == "not_run_invalid_smiles":
        return "not run because the SMILES could not be parsed"
    if "regex" in method:
        return "regex fallback structural-alert screen"
    if "rdkit" in method:
        return "structural alerts plus RDKit descriptor proxy"
    if "pharmacophore" in method:
        return "structural pharmacophore heuristic"
    if "structural_alerts" in method:
        return "structural-alert heuristic"
    return method.replace("_", " ")


def _alert_excerpt(alerts: List[str]) -> str:
    """Return a short human-readable excerpt of matched alerts."""
    clean_alerts = [alert for alert in alerts if alert and alert != "Invalid SMILES"]
    if not clean_alerts:
        return ""

    excerpt = "; ".join(clean_alerts[:2])
    if len(clean_alerts) > 2:
        excerpt += f"; +{len(clean_alerts) - 2} more"
    return excerpt


def _flagged_checks(*checks: Tuple[str, dict], levels: tuple[str, ...]) -> List[str]:
    """Return reviewer-friendly summaries for checks at the requested risk levels."""
    flagged = []
    for label, risk in checks:
        if risk.get("level") not in levels:
            continue
        excerpt = _alert_excerpt(list(risk.get("alerts") or []))
        if excerpt:
            flagged.append(f"{label} ({risk.get('level')}: {excerpt})")
        else:
            flagged.append(f"{label} ({risk.get('level')})")
    return flagged


def _overall_safety_reason(
    overall_flag: str,
    hepatotoxicity: dict,
    herg: dict,
    cyp: dict,
) -> str:
    """Create one canonical plain-language reason for the final safety label."""
    checks = (
        ("hepatotoxicity", hepatotoxicity),
        ("hERG", herg),
        ("CYP interaction", cyp),
    )
    missing = [label for label, risk in checks if not risk.get("checked", False)]
    if overall_flag == "unknown" or missing:
        if len(missing) == 3:
            return (
                "Safety interpretation remains unknown because the ADMET checks could not be completed."
            )
        if missing:
            ran = [label for label, risk in checks if risk.get("checked", False)]
            ran_text = ", ".join(ran) if ran else "none of the checks"
            return (
                f"Safety interpretation remains uncertain because {', '.join(missing)} "
                f"was not checked; available heuristic evidence only covers {ran_text}."
            )
        return "Safety interpretation remains uncertain because the available ADMET screen was incomplete."

    high_risk = _flagged_checks(*checks, levels=("high",))
    if overall_flag == "likely_unsafe" and high_risk:
        return (
            "Likely unsafe: at least one ADMET screen raised a high-risk alert, specifically "
            f"{'; '.join(high_risk)}."
        )

    caution_risk = _flagged_checks(*checks, levels=("medium", "high"))
    if overall_flag == "caution" and caution_risk:
        return (
            "Caution: the heuristic ADMET screen raised a non-low alert, specifically "
            f"{'; '.join(caution_risk)}."
        )

    return (
        "Likely safe within this heuristic screen: hepatotoxicity, hERG, and CYP checks ran "
        "without medium- or high-risk alerts."
    )


def _check_explanation(label: str, risk: dict) -> str:
    """Explain whether an individual ADMET check ran and what it found."""
    checked = bool(risk.get("checked", False))
    method = _method_for_people(str(risk.get("method", "")), checked=checked)
    alerts = list(risk.get("alerts") or [])
    score = risk.get("score")
    score_text = f" (score {score:.2f})" if isinstance(score, (int, float)) else ""

    if not checked:
        return f"{label} was not checked because the SMILES could not be parsed."

    clean_alerts = [alert for alert in alerts if alert != "Invalid SMILES"]
    excerpt = _alert_excerpt(clean_alerts)
    if excerpt:
        return (
            f"{label} was checked via {method} and flagged {len(clean_alerts)} "
            f"alert(s){score_text}: {excerpt}."
        )
    return f"{label} was checked via {method} and no alerts were triggered{score_text}."


def build_admet_provenance(admet_result: dict) -> dict:
    """
    Build one canonical ADMET provenance block from the active ADMET result.

    This function is the only place that converts the per-check ADMET outputs
    into reviewer-facing provenance metadata and explanation text.
    """
    hepatotoxicity = dict(admet_result.get("hepatotoxicity_risk") or {})
    herg = dict(admet_result.get("herg_risk") or {})
    cyp = dict(admet_result.get("cyp_risk") or {})

    overall_flag = str(admet_result.get("overall_safety_flag", "unknown"))
    overall_reason = _overall_safety_reason(overall_flag, hepatotoxicity, herg, cyp)
    overall_method = _overall_safety_method(hepatotoxicity, herg, cyp)
    evidence_level = _admet_evidence_level(hepatotoxicity, herg, cyp)

    provenance = {
        "hepatotoxicity_checked": bool(hepatotoxicity.get("checked", False)),
        "hepatotoxicity_method": str(hepatotoxicity.get("method", "")),
        "hepatotoxicity_alerts": list(hepatotoxicity.get("alerts") or []),
        "hepatotoxicity_score": hepatotoxicity.get("score"),
        "herg_checked": bool(herg.get("checked", False)),
        "herg_method": str(herg.get("method", "")),
        "herg_alerts": list(herg.get("alerts") or []),
        "herg_score": herg.get("score"),
        "cyp_checked": bool(cyp.get("checked", False)),
        "cyp_method": str(cyp.get("method", "")),
        "cyp_alerts": list(cyp.get("alerts") or []),
        "overall_safety_method": overall_method,
        "overall_safety_flag": overall_flag,
        "overall_safety_reason": overall_reason,
        "evidence_level": evidence_level,
    }
    provenance["provenance_explanation"] = (
        f"{_check_explanation('Hepatotoxicity', hepatotoxicity)} "
        f"{_check_explanation('hERG', herg)} "
        f"{_check_explanation('CYP interaction', cyp)} "
        f"Evidence level: {evidence_level.replace('_', ' ')}, so this remains a heuristic/proxy screen rather than experimental safety data. "
        f"Final safety label: {overall_flag.replace('_', ' ')} because {overall_reason}"
    )
    return provenance


def build_admet_evidence(admet_result: dict) -> dict:
    """Expose stable ADMET evidence fields for pipeline, API, and report layers."""
    provenance = build_admet_provenance(admet_result)
    return {
        "overall_safety_flag": provenance["overall_safety_flag"],
        "overall_safety_reason": provenance["overall_safety_reason"],
        "overall_safety_method": provenance["overall_safety_method"],
        "admet_evidence_level": provenance["evidence_level"],
        "admet_provenance": provenance,
        "admet_provenance_explanation": provenance["provenance_explanation"],
    }


# ---------------------------------------------------------------------------
# 5.  Main entry point
# ---------------------------------------------------------------------------

def run_admet_evaluation(smiles: str) -> dict:
    """
    Run all ADMET safety checks and return a dict compatible with ADMETResult.

    Callers can cast to the typed model:
        from genorova.src.validation.models import ADMETResult
        result = ADMETResult(**run_admet_evaluation(smiles))

    Args:
        smiles -- SMILES string to evaluate

    Returns:
        dict with keys: hepatotoxicity_risk, herg_risk, cyp_risk,
                        overall_safety_flag, safety_score, disclaimer,
                        rdkit_available, notes
    """
    print(f"\n[ADMET] Starting evaluation for: {smiles[:60]}...")

    rdkit_ok = _try_load_rdkit()
    notes: List[str] = []

    if not rdkit_ok:
        notes.append(
            "RDKit is unavailable. Predictions use regex pattern matching only "
            "and are significantly less reliable than SMARTS-based alerts."
        )

    dili  = predict_hepatotoxicity(smiles)
    herg  = predict_herg_inhibition(smiles)
    cyp   = predict_cyp_interaction(smiles)

    overall_flag, safety_score = _compute_overall_flag(
        dili["level"], herg["level"], cyp["level"]
    )

    print(f"[ADMET] DILI={dili['level']}, hERG={herg['level']}, "
          f"CYP={cyp['level']}, overall={overall_flag}, score={safety_score}")

    disclaimer = (
        "All ADMET predictions are heuristic proxies based on structural alerts "
        "and molecular descriptors.  They have NOT been validated against "
        "experimental assay data and must not be used as the sole basis for any "
        "safety decision.  Confirm with: pkCSM, SwissADME, or in-vitro assays."
    )

    result = {
        "smiles":               smiles,
        "hepatotoxicity_risk":  dili,
        "herg_risk":            herg,
        "cyp_risk":             cyp,
        "overall_safety_flag":  overall_flag,
        "safety_score":         safety_score,
        "disclaimer":           disclaimer,
        "rdkit_available":      rdkit_ok,
        "notes":                notes,
    }
    return {
        **result,
        **build_admet_evidence(result),
    }


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_drugs = {
        "Metformin (low risk expected)":    "CN(C)C(=N)NC(=N)N",
        "Sitagliptin":                      "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
        "Troglitazone (withdrawn — DILI)":  "CC1=C(C)c2cc(CC3SC(=O)NC3=O)ccc2O1",
        "Cisapride (hERG blocker)":         "CCOC1=CC=C(C=C1)NC(=O)C2=CN(C(=N2)N)CC3CCOCC3",
        "Ketoconazole (CYP inhibitor)":     "O=C(N1CCN(CC1)c1ccc(cc1)OCC1COC(Oc2ccc(cc2)Cl)(n2ccnc2)O1)c1ccccc1Cl",
    }

    for name, smiles in test_drugs.items():
        print(f"\n{'='*60}")
        print(f"Molecule: {name}")
        result = run_admet_evaluation(smiles)
        print(f"  DILI={result['hepatotoxicity_risk']['level']}, "
              f"hERG={result['herg_risk']['level']}, "
              f"CYP={result['cyp_risk']['level']}, "
              f"overall={result['overall_safety_flag']}, "
              f"score={result['safety_score']:.2f}")
        if result["hepatotoxicity_risk"]["alerts"]:
            print(f"  DILI alerts: {result['hepatotoxicity_risk']['alerts'][:2]}")
        if result["herg_risk"]["alerts"]:
            print(f"  hERG alerts: {result['herg_risk']['alerts'][:2]}")
