"""
Canonical science-policy helpers for the active Genorova product path.

This module standardizes the live scientific story around one active workflow:

- disease program: diabetes
- target narrative: DPP4 inhibition
- comparator strategy: sitagliptin as the canonical reference drug

It also builds a per-candidate evidence ledger so API, chat, and reporting
surfaces can present the same facts with the same caveats.
"""

from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any

# Ensure validation package is importable from anywhere
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import the canonical ranking module — the single source of truth for
# score adjustment, sort key, labels, and rationale generation.
from validation.ranking import (
    evidence_rank_score,
    sort_key        as canonical_sort_key,
    best_candidate_label,
    rank_batch,
    best_candidate_rationale,
)

ACTIVE_DISEASE = "diabetes"
ACTIVE_TARGET = "dpp4"
ACTIVE_REFERENCE_DRUG = "sitagliptin"
ACTIVE_PROGRAM_ID = "diabetes_dpp4_sitagliptin_v1"
ACTIVE_PROGRAM_LABEL = "Diabetes / DPP4 comparator workflow"
ACTIVE_PROGRAM_SUMMARY = (
    "Active Genorova lead-evaluation path: diabetes / DPP4 target / "
    "sitagliptin comparator."
)
ACTIVE_SCOPE_NOTE = (
    "The live Genorova scientific path is currently standardized to the "
    "diabetes / DPP4 / sitagliptin comparator workflow. Other target stories "
    "remain outside the active demo path."
)

COMPUTED_FIELD_NAMES = [
    "SMILES validity",
    "molecular weight",
    "LogP",
    "QED",
    "SA score",
    "Lipinski pass/fail",
    "PAINS check",
]

HEURISTIC_FIELD_NAMES = [
    "novelty status without PubChem confirmation",
    "binding proxy or docking fallback mode",
    "hepatotoxicity risk",
    "hERG risk",
    "CYP interaction risk",
    "final decision score",
]

DECISION_PRIORITY = {
    "advance": 2,
    "conditional_advance": 1,
    "reject": 0,
}

CONFIDENCE_PRIORITY = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


@dataclass(frozen=True)
class CandidateConfidence:
    level: str
    evidence_level: str
    note: str


def _descriptor_payload(smiles: str) -> dict[str, Any]:
    """Compute stable RDKit descriptor fields for a valid SMILES string."""
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, QED

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Invalid SMILES string")

    mw = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)
    tpsa = Descriptors.TPSA(mol)
    qed = QED.qed(mol)
    rotatable_bonds = Descriptors.NumRotatableBonds(mol)
    rings = Descriptors.RingCount(mol)
    fraction_csp3 = Descriptors.FractionCSP3(mol)
    lipinski_violations = int(mw > 500) + int(logp > 5) + int(hbd > 5) + int(hba > 10)

    return {
        "smiles": smiles,
        "molecular_weight": round(mw, 2),
        "logp": round(logp, 3),
        "h_bond_donors": hbd,
        "h_bond_acceptors": hba,
        "tpsa": round(tpsa, 2),
        "qed_score": round(qed, 4),
        "passes_lipinski": lipinski_violations == 0,
        "lipinski_violations": lipinski_violations,
        "rotatable_bonds": rotatable_bonds,
        "ring_count": rings,
        "fraction_csp3": round(fraction_csp3, 3),
    }


def _legacy_score(smiles: str) -> float | None:
    """Return the legacy Genorova score when it is available."""
    try:
        from scorer import genorova_clinical_score

        return round(float(genorova_clinical_score(smiles)), 4)
    except Exception:
        return None


def _novelty_bucket(novelty_flag: str) -> str:
    if novelty_flag == "known_repurposing_lead":
        return "known"
    if novelty_flag == "potentially_novel_patentable":
        return "potentially_novel"
    return "uncertain"


def _major_risks(validation: dict[str, Any], *, fallback_used: bool, result_source: str) -> list[str]:
    chem = validation.get("chemistry", {})
    bind = validation.get("binding", {})
    admet = validation.get("admet", {})
    novelty = chem.get("novelty", {})

    risks: list[str] = []
    novelty_flag = novelty.get("flag", "local_only_checked")
    novelty_bucket = _novelty_bucket(novelty_flag)

    if novelty_bucket == "known":
        risks.append("Candidate appears to be a known or repurposing lead, not a novel discovery.")
    elif novelty_bucket == "uncertain":
        risks.append("Novelty is still uncertain because the active path does not confirm PubChem status by default.")

    if chem.get("is_pains"):
        risks.append("PAINS structural alert detected; assay interference risk needs follow-up.")

    binding_mode = bind.get("mode")
    binding_reason = bind.get("mode_reason") or bind.get("real_docking_failure")
    if binding_mode == "fallback_proxy":
        risks.append(
            "Binding evidence is fallback-proxy only because the real docking path is blocked or failed."
        )
        if binding_reason:
            risks.append(f"Docking blocker: {binding_reason}")
    elif binding_mode != "real_docking":
        risks.append("Binding evidence is proxy-based rather than a completed real-docking result.")

    hepatotoxicity = admet.get("hepatotoxicity_risk", {}).get("level")
    if hepatotoxicity in {"medium", "high"}:
        risks.append(f"Hepatotoxicity risk is flagged as {hepatotoxicity}.")

    herg = admet.get("herg_risk", {}).get("level")
    if herg in {"medium", "high"}:
        risks.append(f"hERG risk is flagged as {herg}.")

    cyp = admet.get("cyp_risk", {}).get("level")
    if cyp in {"medium", "high"}:
        risks.append(f"CYP interaction risk is flagged as {cyp}.")

    if fallback_used:
        risks.append("This candidate came through a fallback path rather than a fresh trusted generation run.")

    if result_source == "known_reference_fallback":
        risks.append("This molecule is being shown as a comparator reference, not as a newly discovered lead.")

    return risks


def _confidence_metadata(
    validation: dict[str, Any],
    *,
    fallback_used: bool,
    result_source: str,
) -> CandidateConfidence:
    """Summarize confidence and evidence level conservatively."""
    chemistry = validation.get("chemistry", {})
    binding = validation.get("binding", {})
    admet = validation.get("admet", {})
    novelty = chemistry.get("novelty", {})

    docking_mode = binding.get("mode", "unavailable")
    novelty_flag = novelty.get("flag", "local_only_checked")
    safety_flag = admet.get("overall_safety_flag", "unknown")

    if docking_mode == "real_docking" and novelty.get("pubchem_checked") and safety_flag == "likely_safe":
        return CandidateConfidence(
            level="high",
            evidence_level="computed_descriptors_plus_real_docking",
            note="Higher-confidence computational evidence: descriptors are computed and binding includes a real docking result.",
        )

    if docking_mode == "scaffold_proxy":
        note = "Moderate-confidence screening evidence: descriptors are computed, but binding remains a scaffold proxy."
        if novelty_flag == "local_only_checked":
            note += " Novelty remains uncertain without external lookup."
        return CandidateConfidence(
            level="medium",
            evidence_level="computed_descriptors_plus_proxy_binding",
            note=note,
        )

    if docking_mode == "fallback_proxy":
        note = (
            "Low-confidence screening evidence: descriptors are computed, but the real docking path is blocked "
            "and the system is using fallback proxy binding."
        )
        if novelty_flag == "local_only_checked":
            note += " Novelty also remains uncertain without external lookup."
        return CandidateConfidence(
            level="low",
            evidence_level="computed_descriptors_plus_fallback_proxy",
            note=note,
        )

    note = "Low-confidence evidence: no real docking result is available and the candidate should be treated as a screening-only result."
    if fallback_used or result_source == "known_reference_fallback":
        note += " The molecule also came from a fallback/comparator path."
    return CandidateConfidence(
        level="low",
        evidence_level="screening_only",
        note=note,
    )


def _adjusted_model_score(
    validation: dict[str, Any],
    *,
    fallback_used: bool,
    result_source: str,
) -> float:
    """
    Compute the evidence-weighted rank score for a candidate.

    Delegates entirely to validation.ranking.evidence_rank_score so that
    the penalty logic lives in exactly one place.  The 'validation' dict is
    supplemented with source-quality fields before scoring.
    """
    # Build a flat candidate dict that ranking.evidence_rank_score can read
    chemistry = validation.get("chemistry", {})
    binding   = validation.get("binding", {})
    admet     = validation.get("admet", {})
    clinical  = validation.get("clinical", {})

    flat = {
        "decision_score":       clinical.get("decision_score", 0.0),
        "final_decision":       clinical.get("decision", "reject"),
        "novelty_status":       _novelty_bucket(
                                    chemistry.get("novelty", {}).get("flag", "local_only_checked")
                                ),
        "novelty_flag":         chemistry.get("novelty", {}).get("flag", "local_only_checked"),
        "is_pains":             chemistry.get("is_pains", False),
        "docking_mode":         binding.get("mode", "unavailable"),
        "overall_safety_flag":  admet.get("overall_safety_flag", "unknown"),
        "hepatotoxicity_risk":  admet.get("hepatotoxicity_risk", {}),
        "herg_risk":            admet.get("herg_risk", {}),
        "cyp_interaction_risk": admet.get("cyp_risk", {}),
        "confidence_level":     (
                                    "high"
                                    if binding.get("mode") == "real_docking"
                                    else ("medium" if binding.get("mode") == "scaffold_proxy" else "low")
                                ),
        "fallback_used":        fallback_used,
        "result_source":        result_source,
        "pipeline_warnings":    validation.get("pipeline_warnings", []),
    }

    score, _ = evidence_rank_score(flat)
    return score


def _recommendation(adjusted_score: float, decision: str, candidate: dict | None = None) -> str:
    """
    Return a human-readable recommendation string.

    Delegates label logic to ranking.best_candidate_label when a full candidate
    dict is available; falls back to a simple tier map otherwise.
    """
    if candidate is not None:
        return best_candidate_label(candidate)
    if decision == "reject":
        return "rejected by evidence screen"
    if decision == "advance":
        return "provisional best candidate"
    if adjusted_score >= 0.60:
        return "conditional computational lead"
    return "low-priority computational result"


def evaluate_candidate(
    smiles: str,
    *,
    result_source: str,
    fallback_used: bool = False,
    validation_status: str | None = None,
    confidence_note: str | None = None,
    limitations: list[str] | None = None,
    recommended_next_step: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate a single candidate under the canonical active Genorova science path.

    The returned payload is intentionally API-friendly: it preserves legacy
    fields like `clinical_score` for frontend compatibility while adding a
    richer evidence ledger and validation snapshot.
    """
    from validation.pipeline import validate_molecule
    from validation.chemistry.sanitizer import calculate_sa_score

    descriptor_payload = _descriptor_payload(smiles)
    validation = validate_molecule(
        smiles=smiles,
        target=ACTIVE_TARGET,
        disease=ACTIVE_DISEASE,
        reference_drug=ACTIVE_REFERENCE_DRUG,
        pubchem_lookup=False,
    )

    chemistry = validation["chemistry"]
    binding = validation["binding"]
    admet = validation["admet"]
    clinical = validation["clinical"]
    confidence = _confidence_metadata(
        validation,
        fallback_used=fallback_used,
        result_source=result_source,
    )
    adjusted_score = _adjusted_model_score(
        validation,
        fallback_used=fallback_used,
        result_source=result_source,
    )
    novelty_flag = chemistry.get("novelty", {}).get("flag", "local_only_checked")
    novelty_status = _novelty_bucket(novelty_flag)
    legacy_score = _legacy_score(smiles)
    sa_score, sa_source = calculate_sa_score(smiles)
    major_risks = _major_risks(
        validation,
        fallback_used=fallback_used,
        result_source=result_source,
    )

    notes = list(validation.get("binding", {}).get("notes", []))
    notes.extend(validation.get("chemistry", {}).get("notes", []))
    notes.extend(validation.get("admet", {}).get("notes", []))

    default_limitations = [
        ACTIVE_SCOPE_NOTE,
        "Outputs combine exact descriptor calculations with heuristic or proxy screening signals.",
        "This result is not experimental proof or clinical validation.",
    ]
    if binding.get("mode") == "fallback_proxy":
        default_limitations.append(
            "Binding evidence is fallback-proxy only because the real docking path is currently blocked."
        )
    elif binding.get("mode") != "real_docking":
        default_limitations.append("Binding evidence is proxy-based unless real docking is explicitly available.")
    if novelty_status == "uncertain":
        default_limitations.append("Novelty remains uncertain because the active path does not run external novelty lookup by default.")

    confidence_text = confidence_note or confidence.note

    # --- Canonical rank score and breakdown (from ranking module) ---
    # Build a minimal candidate-like dict so ranking.evidence_rank_score can score it
    _rank_input = {
        "decision_score":       clinical.get("decision_score", 0.0),
        "final_decision":       clinical.get("decision", "reject"),
        "novelty_status":       novelty_status,
        "novelty_flag":         novelty_flag,
        "is_pains":             chemistry.get("is_pains", False),
        "docking_mode":         binding.get("mode", "unavailable"),
        "overall_safety_flag":  admet.get("overall_safety_flag", "unknown"),
        "hepatotoxicity_risk":  admet.get("hepatotoxicity_risk", {}),
        "herg_risk":            admet.get("herg_risk", {}),
        "cyp_interaction_risk": admet.get("cyp_risk", {}),
        "confidence_level":     confidence.level,
        "fallback_used":        fallback_used,
        "result_source":        result_source,
        "pipeline_warnings":    validation.get("pipeline_warnings", []),
    }
    rank_score, rank_bd = evidence_rank_score(_rank_input)
    rank_label = best_candidate_label({**_rank_input, "rank_score": rank_score})

    evidence_ledger = {
        "program_id": ACTIVE_PROGRAM_ID,
        "program_label": ACTIVE_PROGRAM_LABEL,
        "target": ACTIVE_TARGET,
        "disease": ACTIVE_DISEASE,
        "reference_drug": ACTIVE_REFERENCE_DRUG,
        "reference_strategy": "Single canonical comparator against sitagliptin in the DPP4 workflow.",
        "known_vs_uncertain_vs_potentially_novel": novelty_status,
        "novelty_flag": novelty_flag,
        "proxy_vs_real_docking": binding.get("mode"),
        "binding_mode_reason": binding.get("mode_reason"),
        "binding_score": binding.get("docking_score"),
        "reference_score": binding.get("reference_score"),
        "delta_vs_reference": binding.get("delta_vs_reference"),
        "real_docking_status": binding.get("real_docking_status"),
        "real_docking_failure": binding.get("real_docking_failure"),
        "real_docking_probe_blockers": list((binding.get("real_docking_probe") or {}).get("blockers") or []),
        "computed_fields": COMPUTED_FIELD_NAMES,
        "heuristic_fields": HEURISTIC_FIELD_NAMES,
        "major_risks": major_risks,
        "final_decision": clinical.get("decision"),
        "decision_score": clinical.get("decision_score"),
        "rank_score": rank_score,
        "rank_breakdown": rank_bd.to_dict(),
        "rank_label": rank_label,
        "confidence_level": confidence.level,
        "evidence_level": confidence.evidence_level,
        "recommendation_rationale": validation.get("summary"),
    }

    validation_snapshot = {
        "sa_score": round(float(sa_score), 4),
        "sa_score_source": sa_source,
        "novelty_status": novelty_status,
        "novelty_flag": novelty_flag,
        "is_pains": chemistry.get("is_pains"),
        "pains_matches": chemistry.get("pains_matches", []),
        "docking_mode": binding.get("mode"),
        "binding_mode_reason": binding.get("mode_reason"),
        "binding_score": binding.get("docking_score"),
        "reference_score": binding.get("reference_score"),
        "delta_vs_reference": binding.get("delta_vs_reference"),
        "real_docking_status": binding.get("real_docking_status"),
        "real_docking_failure": binding.get("real_docking_failure"),
        "real_docking_probe_blockers": list((binding.get("real_docking_probe") or {}).get("blockers") or []),
        "hepatotoxicity_risk": admet.get("hepatotoxicity_risk", {}).get("level"),
        "hERG_risk": admet.get("herg_risk", {}).get("level"),
        "cyp_interaction_risk": admet.get("cyp_risk", {}).get("level"),
        "final_decision": clinical.get("decision"),
        "decision_score": clinical.get("decision_score"),
        "rank_score": rank_score,
        "rank_label": rank_label,
        "confidence_level": confidence.level,
        "evidence_level": confidence.evidence_level,
    }

    return {
        **descriptor_payload,
        "smiles": smiles,
        "sa_score": round(float(sa_score), 4),
        # canonical rank_score is the authoritative ordering field
        "rank_score": rank_score,
        "rank_breakdown": rank_bd.to_dict(),
        "rank_label": rank_label,
        # clinical_score kept for backward compat with API / frontend
        "clinical_score": rank_score,
        "model_score": rank_score,
        "legacy_clinical_score": legacy_score,
        "recommendation": rank_label,
        "program_id": ACTIVE_PROGRAM_ID,
        "program_label": ACTIVE_PROGRAM_LABEL,
        "target": ACTIVE_TARGET,
        "target_label": ACTIVE_PROGRAM_LABEL,
        "target_disease": ACTIVE_DISEASE,
        "reference_drug": ACTIVE_REFERENCE_DRUG,
        "novelty_status": novelty_status,
        "novelty_flag": novelty_flag,
        "is_pains": chemistry.get("is_pains"),
        "pains_matches": chemistry.get("pains_matches", []),
        "docking_mode": binding.get("mode"),
        "binding_mode_reason": binding.get("mode_reason"),
        "binding_score": binding.get("docking_score"),
        "reference_score": binding.get("reference_score"),
        "delta_vs_reference": binding.get("delta_vs_reference"),
        "real_docking_status": binding.get("real_docking_status"),
        "real_docking_failure": binding.get("real_docking_failure"),
        "hepatotoxicity_risk": admet.get("hepatotoxicity_risk", {}).get("level"),
        "herg_risk": admet.get("herg_risk", {}).get("level"),
        "cyp_interaction_risk": admet.get("cyp_risk", {}).get("level"),
        "final_decision": clinical.get("decision"),
        "decision_score": clinical.get("decision_score"),
        "evidence_level": confidence.evidence_level,
        "confidence_level": confidence.level,
        "validation_status": validation_status or "canonical_validation_complete",
        "confidence_note": confidence_text,
        "limitations": limitations or default_limitations,
        "recommended_next_step": recommended_next_step or clinical.get("recommended_next_step"),
        "result_source": result_source,
        "fallback_used": fallback_used,
        "major_risks": major_risks,
        "summary": validation.get("summary"),
        "notes": notes,
        "validation": validation_snapshot,
        "evidence_ledger": evidence_ledger,
    }


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, float, int]:
    """
    Sort key for evaluated candidates — delegates to the canonical ranking module.

    Kept for backward compatibility with any external callers.
    All internal code should use `validation.ranking.sort_key` directly.
    """
    return canonical_sort_key(candidate)


def evaluate_candidate_rows(
    rows: list[dict[str, Any]],
    *,
    result_source: str,
    fallback_used: bool,
    max_candidates: int,
    confidence_note: str,
    validation_status: str,
    limitations: list[str],
    recommended_next_step: str,
) -> list[dict[str, Any]]:
    """
    Re-evaluate a ranked source row list under the canonical active workflow.

    Only a bounded pool is evaluated to keep the live path practical.
    """
    unique_smiles: list[str] = []
    seen: set[str] = set()
    for row in rows:
        smiles = str(row.get("smiles") or "").strip()
        if not smiles or smiles in seen:
            continue
        seen.add(smiles)
        unique_smiles.append(smiles)

    pool_size = max(max_candidates, min(max_candidates * 3, 24))
    evaluated: list[dict[str, Any]] = []
    for smiles in unique_smiles[:pool_size]:
        try:
            evaluated.append(
                evaluate_candidate(
                    smiles,
                    result_source=result_source,
                    fallback_used=fallback_used,
                    validation_status=validation_status,
                    confidence_note=confidence_note,
                    limitations=limitations,
                    recommended_next_step=recommended_next_step,
                )
            )
        except Exception:
            continue

    # Use the canonical rank_batch so rank_score, rank_label, and rank are
    # set consistently regardless of which consumer calls this function.
    evaluated = rank_batch(evaluated)
    preferred = [c for c in evaluated if c.get("final_decision") != "reject"]
    result = preferred[:max_candidates] if preferred else evaluated[:max_candidates]
    return result
