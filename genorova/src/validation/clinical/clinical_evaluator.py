"""
Genorova AI - Validation: Clinical Utility Module
=================================================

PURPOSE:
Synthesize the upstream chemistry, binding, and ADMET stages into a single
clinical-style screening verdict:

    advance
    conditional_advance
    reject

This module is intentionally conservative. Proxy-only binding evidence can
help prioritize molecules, but it should not read like confirmed target
engagement.
"""

from __future__ import annotations

from typing import Dict, List, Optional


SCORE_WEIGHTS: Dict[str, float] = {
    "binding": 0.35,
    "safety": 0.30,
    "novelty": 0.15,
    "synthesizability": 0.10,
    "drug_likeness": 0.10,
}

ADVANCE_THRESHOLD = 0.65
CONDITIONAL_ADVANCE_THRESHOLD = 0.45

_DISEASE_REFERENCE_DRUGS: Dict[str, Dict[str, str]] = {
    "diabetes": {
        "first_line": "metformin",
        "second_line": "sitagliptin",
        "sglt2": "empagliflozin",
    },
    "infection": {
        "first_line": "azithromycin",
        "hiv": "lopinavir",
        "covid": "remdesivir",
    },
}


def _binding_mode_label(mode: str) -> str:
    labels = {
        "real_docking": "AutoDock Vina (kcal/mol)",
        "scaffold_proxy": "scaffold proxy (screening estimate)",
        "fallback_proxy": "fallback proxy (real docking blocked)",
        "unavailable": "binding unavailable",
    }
    return labels.get(mode, mode.replace("_", " "))


def _binding_requires_confirmation(binding_result: Dict) -> bool:
    return binding_result.get("mode", "unavailable") != "real_docking"


def _binding_component(binding_result: Dict) -> float:
    """
    Convert binding result to a 0-1 component score.

    real_docking:   score based on delta vs reference
    scaffold_proxy: modest screening credit only
    fallback_proxy: very limited screening credit only
    unavailable:    0.0
    """
    mode = binding_result.get("mode", "unavailable")
    score = binding_result.get("docking_score")
    delta = binding_result.get("delta_vs_reference")

    if mode == "unavailable" or score is None:
        return 0.0

    if mode == "real_docking":
        if delta is None:
            return max(0.0, min(1.0, (-score - 5.0) / 4.0))
        component = max(0.0, min(1.0, 0.7 - delta * 0.15))
        return round(component, 3)

    if mode == "scaffold_proxy":
        component = max(0.0, min(0.45, (-score - 5.0) / 4.0 * 0.45))
        return round(component, 3)

    if mode == "fallback_proxy":
        component = max(0.0, min(0.25, (-score - 5.0) / 4.0 * 0.25))
        return round(component, 3)

    return 0.0


def _safety_component(admet_result: Dict) -> float:
    flag = admet_result.get("overall_safety_flag", "unknown")
    score = admet_result.get("safety_score", 0.5)
    if flag == "likely_unsafe":
        return min(score, 0.20)
    return float(score)


def _novelty_component(chemistry_result: Dict) -> float:
    novelty = chemistry_result.get("novelty", {})
    flag = novelty.get("flag", "local_only_checked")

    if flag == "potentially_novel_patentable":
        return 1.0
    if flag == "local_only_checked":
        return 0.55
    if flag == "known_repurposing_lead":
        return 0.35
    if flag == "unrealistic":
        return 0.0
    return 0.5


def _synthesizability_component(chemistry_result: Dict) -> float:
    sa_flag = chemistry_result.get("sa_flag", "difficult")
    sa_score = chemistry_result.get("sa_score")

    if sa_flag == "synthesizable":
        return 1.0
    if sa_flag == "difficult":
        if sa_score is not None:
            return round(max(0.0, 1.0 - (sa_score - 4.0) / 3.0), 3)
        return 0.5
    return 0.0


def _drug_likeness_component(
    qed_score: Optional[float],
    passes_lipinski: Optional[bool],
) -> float:
    parts = []

    if qed_score is not None:
        parts.append(max(0.0, min(1.0, (qed_score - 0.3) / 0.5)))

    if passes_lipinski is not None:
        parts.append(1.0 if passes_lipinski else 0.0)

    if not parts:
        return 0.5
    return round(sum(parts) / len(parts), 3)


def _build_comparisons(
    binding_result: Dict,
    admet_result: Dict,
    chemistry_result: Dict,
    qed_score: Optional[float],
    reference_drug: str,
) -> List[Dict]:
    comparisons = []

    cand_score = binding_result.get("docking_score")
    ref_score = binding_result.get("reference_score")
    mode = binding_result.get("mode", "unavailable")

    if cand_score is not None:
        units = "kcal/mol" if mode == "real_docking" else "(proxy screening estimate)"
        better = (cand_score < ref_score) if ref_score is not None else None
        if mode == "real_docking":
            note = "More negative = better binding. Real docking."
        elif mode == "fallback_proxy":
            note = (
                "Fallback proxy estimate only. The declared real-docking path is blocked or failed, "
                "so this is not docking evidence."
            )
        else:
            note = (
                "Proxy estimate only. No active target-specific real-docking path was used, "
                "so interpret this as screening guidance."
            )
        comparisons.append(
            {
                "metric": f"Binding score {units}",
                "candidate_value": cand_score,
                "reference_value": ref_score,
                "better": better,
                "note": note,
            }
        )

    dili = admet_result.get("hepatotoxicity_risk", {})
    comparisons.append(
        {
            "metric": "Hepatotoxicity (DILI) risk",
            "candidate_value": dili.get("level", "unknown"),
            "reference_value": "low",
            "better": dili.get("level") == "low",
            "note": "Heuristic proxy; confirm with in-vitro assay.",
        }
    )

    herg = admet_result.get("herg_risk", {})
    comparisons.append(
        {
            "metric": "hERG inhibition risk",
            "candidate_value": herg.get("level", "unknown"),
            "reference_value": "low",
            "better": herg.get("level") == "low",
            "note": "Heuristic proxy; confirm with patch-clamp assay.",
        }
    )

    sa_score = chemistry_result.get("sa_score")
    comparisons.append(
        {
            "metric": "Synthetic accessibility (SA, 1=easy, 10=hard)",
            "candidate_value": sa_score,
            "reference_value": "<= 3 (typical approved drugs)",
            "better": (sa_score <= 4.0) if sa_score is not None else None,
            "note": (
                "RDKit computed"
                if chemistry_result.get("sa_score_source") == "rdkit_computed"
                else "Heuristic estimate"
            ),
        }
    )

    if qed_score is not None:
        comparisons.append(
            {
                "metric": "Drug-likeness (QED, 0-1)",
                "candidate_value": qed_score,
                "reference_value": "0.55+ (typical approved drugs)",
                "better": qed_score >= 0.55,
                "note": "Computed by RDKit QED module.",
            }
        )

    is_pains = chemistry_result.get("is_pains", False)
    comparisons.append(
        {
            "metric": "PAINS structural alerts",
            "candidate_value": "yes" if is_pains else "none",
            "reference_value": "none",
            "better": not is_pains,
            "note": "PAINS hits may cause assay interference.",
        }
    )

    return comparisons


def _check_hard_rejects(
    chemistry_result: Dict,
    admet_result: Dict,
    binding_result: Dict,
) -> List[str]:
    reasons = []

    if not chemistry_result.get("valid_smiles", True):
        reasons.append("SMILES is invalid; molecule cannot be characterized.")

    if admet_result.get("overall_safety_flag") == "likely_unsafe":
        reasons.append(
            "At least one ADMET risk is rated HIGH. Safety overrides potency at this stage."
        )

    if chemistry_result.get("sa_flag") == "impractical":
        sa = chemistry_result.get("sa_score", "unknown")
        cand_score = binding_result.get("docking_score")
        mode = binding_result.get("mode", "unavailable")
        if mode == "real_docking" and cand_score is not None and cand_score <= -9.0:
            pass
        else:
            reasons.append(
                f"SA score {sa} > 6 indicates synthesis is impractical in most labs."
            )

    return reasons


def _write_explanation(
    decision: str,
    decision_score: float,
    binding_result: Dict,
    admet_result: Dict,
    chemistry_result: Dict,
    qed_score: Optional[float],
    target: str,
    disease: str,
    reference_drug: str,
    conditions: List[str],
    rejection_reasons: List[str],
    potency_vs_toxicity: str,
) -> str:
    lines = []

    decision_labels = {
        "advance": "ADVANCE to the next stage",
        "conditional_advance": "CONDITIONAL ADVANCE (see conditions below)",
        "reject": "REJECT at this stage",
    }
    lines.append(
        f"Clinical Utility Decision: {decision_labels.get(decision, decision.upper())} "
        f"(composite score: {decision_score:.2f} / 1.00)"
    )
    lines.append("")

    mode = binding_result.get("mode", "unavailable")
    score = binding_result.get("docking_score")
    ref = binding_result.get("reference_score")
    delta = binding_result.get("delta_vs_reference")
    if score is not None:
        lines.append(f"Target binding [{_binding_mode_label(mode)}]:")
        lines.append(
            f"  Candidate: {score:.2f}  |  Reference ({reference_drug}): "
            + (f"{ref:.2f}" if ref is not None else "N/A")
        )
        if delta is not None:
            better_worse = "BETTER than" if delta < 0 else ("similar to" if abs(delta) < 0.5 else "WEAKER than")
            lines.append(f"  -> Candidate scores {abs(delta):.2f} units {better_worse} the reference drug.")
        if mode != "real_docking":
            lines.append(
                "  WARNING: This is not a completed docking result. Treat it as computational screening guidance only."
            )
            mode_reason = binding_result.get("mode_reason", "")
            if mode_reason:
                lines.append(f"  Reason: {mode_reason}")
    else:
        lines.append("Target binding: Could not be estimated.")
    lines.append("")

    dili = admet_result.get("hepatotoxicity_risk", {}).get("level", "unknown")
    herg = admet_result.get("herg_risk", {}).get("level", "unknown")
    cyp = admet_result.get("cyp_risk", {}).get("level", "unknown")
    safety_flag = admet_result.get("overall_safety_flag", "unknown")

    lines.append("Safety profile (heuristic estimates, not assay-validated):")
    lines.append(f"  Liver (DILI):   {dili.upper()}")
    lines.append(f"  Cardiac (hERG): {herg.upper()}")
    lines.append(f"  Drug interaction (CYP450): {cyp.upper()}")
    lines.append(f"  -> Overall safety flag: {safety_flag.upper()}")
    lines.append("")

    sa_flag = chemistry_result.get("sa_flag", "unknown")
    is_pains = chemistry_result.get("is_pains", False)
    novelty = chemistry_result.get("novelty", {}).get("flag", "local_only_checked")

    lines.append("Chemical properties:")
    lines.append(f"  Synthesis difficulty: {sa_flag} (SA = {chemistry_result.get('sa_score', 'N/A')})")
    lines.append(f"  PAINS alerts: {'YES - investigate further' if is_pains else 'None detected'}")
    lines.append(f"  Novelty: {novelty.replace('_', ' ')}")
    if qed_score is not None:
        lines.append(f"  Drug-likeness (QED): {qed_score:.3f}")
    lines.append("")

    if potency_vs_toxicity:
        lines.append("Potency-safety trade-off:")
        lines.append(f"  {potency_vs_toxicity}")
        lines.append("")

    if decision == "advance":
        lines.append(
            "Rationale: The molecule meets thresholds across binding, safety, synthesizability, and novelty. "
            "Recommended for deeper computational follow-up and experimental planning."
        )
    elif decision == "conditional_advance":
        lines.append("Rationale: The molecule shows screening value, but specific concerns must be addressed:")
        for condition in conditions:
            lines.append(f"  - {condition}")
    else:
        lines.append("Rationale: Rejected due to the following critical issues:")
        for reason in rejection_reasons:
            lines.append(f"  - {reason}")

    lines.append("")
    lines.append(
        "IMPORTANT: This assessment is a computational screening aid only. "
        "It is not clinical validation, experimental proof, or a treatment recommendation."
    )
    return "\n".join(lines)


def _potency_toxicity_note(binding_result: Dict, admet_result: Dict) -> str:
    mode = binding_result.get("mode", "unavailable")
    score = binding_result.get("docking_score")
    dili = admet_result.get("hepatotoxicity_risk", {}).get("level", "unknown")
    herg = admet_result.get("herg_risk", {}).get("level", "unknown")
    safety_flag = admet_result.get("overall_safety_flag", "unknown")

    if score is None:
        return "Binding score unavailable; cannot assess potency-safety trade-off."

    if mode == "fallback_proxy":
        reason = binding_result.get("mode_reason", "real docking is blocked")
        return (
            "Binding remains uncertain because the system is using a fallback proxy rather than a completed docking run. "
            f"Reason: {reason}"
        )

    if mode == "scaffold_proxy":
        return (
            "Binding remains uncertain because the current score is a scaffold proxy only. "
            "Treat this as a prioritization hint, not potency evidence."
        )

    good_binding = mode == "real_docking" and score <= -7.0

    if good_binding and safety_flag == "likely_safe":
        return (
            "Promising profile: predicted binding is strong and safety flags are low. "
            "The potency-toxicity balance appears favorable at this early stage."
        )
    if good_binding and safety_flag == "caution":
        return (
            "Potency appears promising, but medium-level safety concerns "
            f"(DILI={dili}, hERG={herg}) partially offset this."
        )
    if good_binding and safety_flag == "likely_unsafe":
        return (
            "Despite predicted binding activity, high safety flags override the potency advantage. "
            f"DILI={dili}, hERG={herg}."
        )
    if safety_flag == "likely_safe":
        return (
            "Safety profile is relatively clean, but predicted binding is weak. "
            "This may still be useful as a scaffold for optimization."
        )
    return f"Both binding ({score:.1f}) and safety ({safety_flag}) need improvement."


def run_clinical_evaluation(
    smiles: str,
    target: str,
    disease: str,
    reference_drug: str,
    chemistry_result: Dict,
    binding_result: Dict,
    admet_result: Dict,
    qed_score: Optional[float] = None,
    passes_lipinski: Optional[bool] = None,
) -> dict:
    print(f"\n[ClinicalEval] Evaluating {smiles[:50]} for {disease}/{target}...")

    notes: List[str] = []
    hard_rejects = _check_hard_rejects(chemistry_result, admet_result, binding_result)

    bc = _binding_component(binding_result)
    sc = _safety_component(admet_result)
    nc = _novelty_component(chemistry_result)
    syc = _synthesizability_component(chemistry_result)
    dlc = _drug_likeness_component(qed_score, passes_lipinski)

    decision_score = (
        SCORE_WEIGHTS["binding"] * bc
        + SCORE_WEIGHTS["safety"] * sc
        + SCORE_WEIGHTS["novelty"] * nc
        + SCORE_WEIGHTS["synthesizability"] * syc
        + SCORE_WEIGHTS["drug_likeness"] * dlc
    )
    decision_score = round(min(1.0, max(0.0, decision_score)), 4)

    print(
        f"   [Clinical] Components: binding={bc:.2f}, safety={sc:.2f}, "
        f"novelty={nc:.2f}, synth={syc:.2f}, dl={dlc:.2f}"
    )
    print(f"   [Clinical] Decision score: {decision_score:.4f}")

    conditions: List[str] = []
    rejection_reasons: List[str] = list(hard_rejects)
    mode = binding_result.get("mode", "unavailable")
    proxy_only_binding = _binding_requires_confirmation(binding_result)
    novelty_flag = chemistry_result.get("novelty", {}).get("flag", "local_only_checked")
    known_repurposing = novelty_flag == "known_repurposing_lead"
    mode_reason = binding_result.get("mode_reason") or binding_result.get("real_docking_failure")

    if hard_rejects:
        decision = "reject"
    elif decision_score >= ADVANCE_THRESHOLD:
        decision = "advance"
    elif decision_score >= CONDITIONAL_ADVANCE_THRESHOLD:
        decision = "conditional_advance"
    else:
        decision = "reject"

    if decision != "reject" and proxy_only_binding:
        if decision == "advance":
            decision = "conditional_advance"
        if mode == "fallback_proxy":
            condition = (
                "The active target is still running on fallback proxy binding evidence because the real docking path is blocked. "
                "Do not present this as confirmed target engagement."
            )
        else:
            condition = (
                "Binding evidence is a scaffold proxy only. Use it for screening, not as proof of target engagement."
            )
        if mode_reason:
            condition = f"{condition} Reason: {mode_reason}"
        conditions.append(condition)

    if decision != "reject" and known_repurposing and proxy_only_binding:
        decision = "conditional_advance"
        conditions.append(
            "This molecule is a known or repurposing lead. With proxy-only binding evidence, it should not be framed as a validated advance candidate."
        )

    if decision == "conditional_advance":
        if bc < 0.5:
            conditions.append(
                f"Run or restore real molecular docking before treating the binding result as decision-grade evidence. "
                f"Current binding component is {bc:.2f} in {mode} mode."
            )
        if sc < 0.7:
            safety_flag = admet_result.get("overall_safety_flag", "unknown")
            conditions.append(
                f"Safety flag is '{safety_flag}'. Confirm with in-vitro ADMET assays before advancing."
            )
        if chemistry_result.get("is_pains"):
            conditions.append(
                "PAINS alert detected. Verify the molecule does not interfere with assays before biological testing."
            )
        if not chemistry_result.get("novelty", {}).get("pubchem_checked"):
            conditions.append(
                "PubChem novelty check was not performed. Run with pubchem_lookup=True before making novelty claims."
            )
        conditions = list(dict.fromkeys(conditions))

    if decision == "reject" and not hard_rejects:
        rejection_reasons.append(
            f"Composite decision score ({decision_score:.2f}) is below the minimum threshold of {CONDITIONAL_ADVANCE_THRESHOLD:.2f}."
        )
        if bc < 0.3:
            rejection_reasons.append("Predicted binding is too weak or too uncertain to be competitive.")
        if sc < 0.4:
            rejection_reasons.append("Safety profile is too concerning for further study.")
        if syc == 0.0:
            rejection_reasons.append("SA score indicates synthesis is impractical.")

    comparisons = _build_comparisons(
        binding_result, admet_result, chemistry_result, qed_score, reference_drug
    )
    pt_note = _potency_toxicity_note(binding_result, admet_result)

    if mode == "fallback_proxy":
        recommended = (
            "Fix the active DPP4 docking path, then rerun validation before treating this molecule as a lead candidate."
        )
    elif decision == "advance" and mode != "real_docking":
        recommended = (
            "Run AutoDock Vina docking against the target to confirm binding, then rerun ADMET with stronger external tools."
        )
    elif decision == "advance":
        recommended = "Proceed to fragment optimization and an in-vitro binding assay such as ITC or SPR."
    elif decision == "conditional_advance":
        recommended = "Address the conditions listed above, then resubmit for validation."
    else:
        recommended = (
            "Do not advance this molecule as-is. Consider scaffold redesign or SAR analysis instead."
        )

    explanation = _write_explanation(
        decision,
        decision_score,
        binding_result,
        admet_result,
        chemistry_result,
        qed_score,
        target,
        disease,
        reference_drug,
        conditions,
        rejection_reasons,
        pt_note,
    )

    print(f"[ClinicalEval] Decision: {decision} (score={decision_score:.3f})")

    return {
        "smiles": smiles,
        "target": target,
        "disease": disease,
        "reference_drug": reference_drug,
        "decision": decision,
        "decision_score": decision_score,
        "explanation": explanation,
        "conditions": conditions,
        "rejection_reasons": rejection_reasons,
        "comparisons": comparisons,
        "potency_vs_toxicity_note": pt_note,
        "recommended_next_step": recommended,
        "notes": notes,
        "rdkit_available": chemistry_result.get("rdkit_available", True),
    }


if __name__ == "__main__":
    sample_chemistry = {
        "smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "valid_smiles": True,
        "sa_score": 2.8,
        "sa_score_source": "rdkit_computed",
        "sa_flag": "synthesizable",
        "is_pains": False,
        "pains_matches": [],
        "novelty": {
            "flag": "local_only_checked",
            "found_in_local_db": False,
            "found_in_approved_drugs": False,
            "pubchem_cid": None,
            "pubchem_checked": False,
            "most_similar_drug": "paracetamol",
            "max_tanimoto": 0.42,
            "data_source": "local_db_lookup",
        },
        "passes_sanity": True,
        "rdkit_available": True,
        "notes": [],
    }
    sample_binding = {
        "smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "target": "insulin_receptor",
        "reference_drug": "staurosporine",
        "docking_score": -6.3,
        "reference_score": -9.2,
        "delta_vs_reference": 2.9,
        "key_h_bonds": [],
        "key_hydrophobic": [],
        "mode": "fallback_proxy",
        "confidence": "low",
        "data_source": "heuristic_proxy",
        "interpretation": "Proxy score is moderate.",
        "mode_reason": "Real docking helper is missing.",
        "real_docking_failure": "dock_molecule is not implemented.",
        "rdkit_available": True,
        "notes": ["FALLBACK PROXY MODE"],
    }
    sample_admet = {
        "smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "hepatotoxicity_risk": {"level": "low", "score": 0.1, "alerts": [], "method": "heuristic"},
        "herg_risk": {"level": "low", "score": 0.05, "alerts": [], "method": "heuristic"},
        "cyp_risk": {"level": "medium", "score": 0.45, "alerts": ["Amine near aromatic"], "method": "heuristic"},
        "overall_safety_flag": "caution",
        "safety_score": 0.72,
        "disclaimer": "...",
        "rdkit_available": True,
        "notes": [],
    }

    result = run_clinical_evaluation(
        smiles="Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        target="insulin_receptor",
        disease="diabetes",
        reference_drug="staurosporine",
        chemistry_result=sample_chemistry,
        binding_result=sample_binding,
        admet_result=sample_admet,
        qed_score=0.62,
        passes_lipinski=True,
    )

    print(f"\n{'=' * 60}")
    print(f"Decision: {result['decision']} (score={result['decision_score']:.3f})")
    print(f"\nExplanation:\n{result['explanation']}")
