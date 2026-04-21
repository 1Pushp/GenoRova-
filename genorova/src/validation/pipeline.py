"""
Genorova AI - Second-Stage Validation Pipeline Orchestrator
===========================================================

PURPOSE:
Run the four active validation stages in sequence for a single molecule:

  A. Chemical Sanity
  B. Target Engagement
  C. ADMET Safety
  D. Clinical Utility

This is the single entry point used by downstream API, chat, and reporting
surfaces. The output is intentionally conservative and exposes which parts of
the result are computed, heuristic, proxy-based, or unavailable.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from science_evidence import build_faculty_explanation_stack
from validation.admet.admet_predictor import build_admet_evidence, run_admet_evaluation
from validation.binding.target_binder import build_binding_evidence, run_binding_evaluation
from validation.chemistry.sanitizer import (
    build_novelty_evidence,
    novelty_status_from_flag,
    run_chemistry_sanity,
)
from validation.clinical.clinical_evaluator import run_clinical_evaluation
from validation.reference_data import (
    ACCEPTABLE_DELTA_VS_REFERENCE,
    BETTER_THAN_REFERENCE_DELTA,
    CANONICAL_DISEASE,
    CANONICAL_TARGET,
    validate_disease_target_pair,
)


def _get_qed_and_lipinski(smiles: str):
    """Fetch QED and Lipinski status from scorer.py without blocking the pipeline."""
    try:
        from scorer import calculate_qed, passes_lipinski  # noqa: PLC0415

        return calculate_qed(smiles), passes_lipinski(smiles)
    except Exception:
        return None, None


def _binding_summary(binding: dict) -> str:
    mode = binding.get("mode", "unavailable")
    score = binding.get("docking_score")
    reason = binding.get("mode_reason", "")

    if score is None:
        return f"Binding could not be estimated. Reason: {reason or 'no usable docking or proxy result was available'}."

    if mode == "real_docking":
        return f"Real docking score {score:.2f} kcal/mol."

    qualifier = "fallback proxy" if mode == "fallback_proxy" else "proxy"
    detail = f"Binding score {score:.2f} ({qualifier})."
    if reason:
        detail += f" Reason: {reason}"
    return detail


def _build_summary(
    final_decision: str,
    chemistry: dict,
    binding: dict,
    admet: dict,
    clinical: dict,
) -> str:
    decision_phrases = {
        "advance": "is recommended to advance to the next stage",
        "conditional_advance": "may advance conditionally",
        "reject": "is rejected at this stage",
    }
    action = decision_phrases.get(final_decision, final_decision)

    sa = chemistry.get("sa_score", "N/A")
    sa_flag = chemistry.get("sa_flag", "unknown")
    novelty_evidence = build_novelty_evidence(chemistry.get("novelty", {}))
    binding_evidence = build_binding_evidence(binding)
    novelty_reason = novelty_evidence.get("novelty_reason", "Uncertain novelty: only local checks were run.")
    provenance_explanation = novelty_evidence.get(
        "novelty_provenance",
        {},
    ).get("provenance_explanation", novelty_reason)
    admet_evidence = build_admet_evidence(admet)
    admet_reason = admet_evidence.get(
        "overall_safety_reason",
        "Safety interpretation remains uncertain because the ADMET screen was incomplete.",
    )
    admet_provenance_explanation = admet_evidence.get(
        "admet_provenance_explanation",
        admet_reason,
    )
    pains = "PAINS alert detected." if chemistry.get("is_pains") else "No PAINS alerts."

    safety = admet.get("overall_safety_flag", "unknown").replace("_", " ")
    dili = admet.get("hepatotoxicity_risk", {}).get("level", "?")
    herg = admet.get("herg_risk", {}).get("level", "?")
    cyp = admet.get("cyp_risk", {}).get("level", "?")
    score = clinical.get("decision_score", 0.0)

    return (
        f"This molecule {action} with a composite decision score of {score:.2f}/1.00. "
        f"Chemical sanity: SA score {sa} ({sa_flag}); {pains}; novelty assessment: {novelty_reason} "
        f"Novelty provenance: {provenance_explanation} "
        f"Target engagement: {_binding_summary(binding)} "
        f"Binding provenance: {binding_evidence.get('binding_provenance_explanation', binding_evidence.get('final_binding_reason', 'Binding provenance not available.'))} "
        f"Safety profile (heuristic): overall {safety} (DILI={dili}, hERG={herg}, CYP={cyp}). "
        f"{admet_reason} ADMET provenance: {admet_provenance_explanation} "
        f"Proxy, fallback, and heuristic fields are screening signals only and are not experimental proof."
    )


def _five_questions(
    chemistry: dict,
    binding: dict,
    admet: dict,
    clinical: dict,
) -> dict:
    sa_flag = chemistry.get("sa_flag")
    can_synth = {
        "synthesizable": True,
        "difficult": None,
        "impractical": False,
    }.get(sa_flag)

    novelty_flag = chemistry.get("novelty", {}).get("flag", "local_only_checked")
    likely_novel = {
        "potentially_novel_patentable": True,
        "known_repurposing_lead": False,
        "unrealistic": False,
        "local_only_checked": None,
    }.get(novelty_flag)

    mode = binding.get("mode", "unavailable")
    delta = binding.get("delta_vs_reference")
    score = binding.get("docking_score")

    if mode == "real_docking" and score is not None:
        binds_well = delta is not None and delta <= ACCEPTABLE_DELTA_VS_REFERENCE
    else:
        binds_well = None

    safety_flag = admet.get("overall_safety_flag", "unknown")
    likely_safe = {
        "likely_safe": True,
        "caution": None,
        "likely_unsafe": False,
        "unknown": None,
    }.get(safety_flag)

    decision = clinical.get("decision", "reject")
    worth_pursuing = decision in ("advance", "conditional_advance")

    return {
        "can_be_synthesized": can_synth,
        "likely_novel": likely_novel,
        "binds_well_vs_standard": binds_well,
        "likely_safe_to_investigate": likely_safe,
        "clinically_worth_pursuing": worth_pursuing,
    }


def _binding_evidence_level(binding_mode: str) -> str:
    return {
        "real_docking": "real_docking",
        "scaffold_proxy": "heuristic_proxy",
        "fallback_proxy": "fallback_proxy",
        "unavailable": "unavailable",
    }.get(binding_mode, "unavailable")


def _build_evidence_ledger(
    chemistry: dict,
    binding: dict,
    admet: dict,
    clinical: dict,
    dt_warnings: list,
) -> dict:
    novelty_data = chemistry.get("novelty", {})
    novelty_flag = novelty_data.get("flag", "local_only_checked")
    novelty_evidence = build_novelty_evidence(novelty_data)
    novelty_level = novelty_status_from_flag(novelty_flag)
    novelty_provenance = novelty_evidence["novelty_provenance"]
    binding_evidence_details = build_binding_evidence(binding)
    binding_provenance = binding_evidence_details["binding_provenance"]
    admet_evidence = build_admet_evidence(admet)
    admet_provenance = admet_evidence["admet_provenance"]

    sa_source = chemistry.get("sa_score_source", "heuristic_proxy")
    sa_evidence = "computed" if sa_source == "rdkit_computed" else "heuristic"

    binding_mode = binding.get("mode", "unavailable")
    docking_score = binding.get("docking_score")
    delta = binding.get("delta_vs_reference")
    ref_score = binding.get("reference_score")
    ref_drug = binding.get("reference_drug", "unknown")
    binding_reason = binding.get("mode_reason", "")
    real_docking_status = binding.get("real_docking_status", "blocked")
    real_docking_failure = binding.get("real_docking_failure")
    probe_blockers = list((binding.get("real_docking_probe") or {}).get("blockers") or [])
    binding_evidence = _binding_evidence_level(binding_mode)

    if docking_score is not None and ref_score is not None:
        if binding_mode == "real_docking":
            binding_comparator_note = (
                f"Vina: {docking_score:.2f} kcal/mol vs {ref_drug} {ref_score:.2f} kcal/mol "
                f"(delta={delta:+.2f})"
            )
        else:
            binding_comparator_note = (
                f"Proxy estimate: {docking_score:.2f} vs {ref_drug} anchor {ref_score:.2f} "
                f"(delta={delta:+.2f}). Reason: {binding_reason or 'proxy-only path'}"
            )
    else:
        binding_comparator_note = binding_reason or "unavailable"

    hep = admet.get("hepatotoxicity_risk", {})
    herg = admet.get("herg_risk", {})
    cyp = admet.get("cyp_risk", {})
    admet_method = admet_evidence.get("overall_safety_method", "heuristic_alert_consensus")
    admet_evidence_level = admet_evidence.get("admet_evidence_level", "incomplete_heuristic_proxy")

    major_risks = []
    if binding_mode == "fallback_proxy":
        major_risks.append(
            f"Binding relies on fallback proxy evidence because the real docking path is blocked ({binding_reason or real_docking_failure or 'unspecified blocker'})."
        )
    elif binding_mode == "scaffold_proxy":
        major_risks.append("Binding relies on scaffold proxy evidence rather than a completed docking run.")
    elif not binding_evidence_details.get("binding_checked", False):
        major_risks.append("Binding was not checked because the input could not be evaluated by the active binding path.")
    elif binding_mode == "unavailable":
        major_risks.append("Binding checks ran but no usable docking or proxy score was available.")

    if hep.get("level") in ("medium", "high"):
        major_risks.append(f"Hepatotoxicity risk: {hep['level']} ({admet_evidence_level})")
    if herg.get("level") in ("medium", "high"):
        major_risks.append(f"hERG risk: {herg['level']} ({admet_evidence_level})")
    if cyp.get("level") in ("medium", "high"):
        major_risks.append(f"CYP interaction risk: {cyp['level']} ({admet_evidence_level})")
    missing_checks = [
        label
        for label, checked in (
            ("hepatotoxicity", admet_provenance.get("hepatotoxicity_checked")),
            ("hERG", admet_provenance.get("herg_checked")),
            ("CYP interaction", admet_provenance.get("cyp_checked")),
        )
        if not checked
    ]
    if missing_checks:
        major_risks.append(
            f"ADMET screen incomplete: {', '.join(missing_checks)} not checked."
        )
    if chemistry.get("is_pains"):
        pains_names = [item.get("alert_name", "unknown") for item in chemistry.get("pains_matches", [])]
        major_risks.append(f"PAINS alert(s): {', '.join(pains_names)}")

    decision_score = clinical.get("decision_score", 0.0)
    decision = clinical.get("decision", "reject")

    rationale_parts = []
    rationale_parts.append(novelty_evidence["novelty_reason"])

    if binding_mode == "real_docking":
        rationale_parts.append(f"binding assessed by real docking ({binding_comparator_note})")
    else:
        rationale_parts.append(f"binding is proxy-only ({binding_comparator_note})")
    rationale_parts.append(admet_evidence["overall_safety_reason"])

    if major_risks:
        rationale_parts.append(f"key risks flagged: {'; '.join(major_risks)}")
    else:
        rationale_parts.append("no major structural risk flags detected")

    rationale = ". ".join(rationale_parts).capitalize() + "."

    if binding_mode == "real_docking" and sa_evidence == "computed":
        confidence_tier = "tier_2_medium"
        confidence_note = (
            "Binding includes a real docking result, while novelty and safety still require additional confirmation."
        )
    elif binding_mode == "scaffold_proxy" and sa_evidence == "computed":
        confidence_tier = "tier_2_medium"
        confidence_note = "Descriptors are computed, but binding remains a scaffold proxy. Use for screening only."
    else:
        confidence_tier = "tier_3_low"
        confidence_note = (
            "Binding is unavailable or fallback-only, so this result should be treated as a low-confidence computational screen."
        )

    if chemistry.get("is_pains") or dt_warnings:
        confidence_tier = "tier_3_low"
        confidence_note += " Confidence is downgraded further by PAINS or disease-target consistency warnings."

    return {
        "novelty": {
            "status": novelty_level,
            "flag": novelty_flag,
            "found_in_db": novelty_data.get("found_in_local_db", False),
            "found_in_drugs": novelty_data.get("found_in_approved_drugs", False),
            "pubchem_checked": novelty_data.get("pubchem_checked", False),
            "evidence_level": "computed" if novelty_data.get("pubchem_checked") else "heuristic",
            "closest_reference": novelty_evidence["novelty_closest_reference"],
            "tanimoto_score": novelty_evidence["novelty_tanimoto_score"],
            "threshold": novelty_evidence["novelty_threshold"],
            "reason": novelty_evidence["novelty_reason"],
            "provenance": novelty_provenance,
        },
        "sa_score": {
            "value": chemistry.get("sa_score"),
            "flag": chemistry.get("sa_flag", "unknown"),
            "evidence_level": sa_evidence,
        },
        "pains": {
            "detected": chemistry.get("is_pains", False),
            "alerts": [item.get("alert_name") for item in chemistry.get("pains_matches", [])],
            "evidence_level": "computed" if chemistry.get("pains_source") == "rdkit_computed" else "heuristic",
        },
        "binding": {
            "mode": binding_mode,
            "binding_checked": binding_evidence_details["binding_checked"],
            "score": docking_score,
            "reference_drug": ref_drug,
            "reference_score": ref_score,
            "delta": delta,
            "comparator_note": binding_comparator_note,
            "evidence_level": binding_evidence_details["binding_evidence_level"],
            "final_binding_reason": binding_evidence_details["final_binding_reason"],
            "provenance": binding_provenance,
            "provenance_explanation": binding_evidence_details["binding_provenance_explanation"],
            "mode_reason": binding_reason,
            "real_docking_status": real_docking_status,
            "real_docking_failure": real_docking_failure,
            "probe_blockers": probe_blockers,
        },
        "admet": {
            "hepatotoxicity": hep.get("level", "unknown"),
            "herg": herg.get("level", "unknown"),
            "cyp": cyp.get("level", "unknown"),
            "overall_safety": admet.get("overall_safety_flag", "unknown"),
            "overall_safety_reason": admet_evidence["overall_safety_reason"],
            "evidence_level": admet_evidence_level,
            "method": admet_method,
            "provenance": admet_provenance,
            "provenance_explanation": admet_evidence["admet_provenance_explanation"],
        },
        "clinical": {
            "decision": decision,
            "decision_score": round(decision_score, 4),
            "evidence_level": "heuristic",
            "decision_provenance": clinical.get("decision_provenance"),
            "final_decision_reason": (clinical.get("decision_provenance") or {}).get("final_decision_reason"),
        },
        "major_risks": major_risks,
        "confidence_tier": confidence_tier,
        "confidence_note": confidence_note,
        "recommendation_rationale": rationale,
        "dt_warnings": dt_warnings,
    }


def validate_molecule(
    smiles: str,
    target: str = "dpp4",
    disease: str = "diabetes",
    reference_drug: Optional[str] = None,
    pubchem_lookup: bool = False,
) -> dict:
    print("\n" + "=" * 70)
    print("GENOROVA VALIDATION PIPELINE v2.1")
    print(f"SMILES  : {smiles[:60]}")
    print(f"Target  : {target}")
    print(f"Disease : {disease}")
    print("=" * 70)

    dt_warnings = validate_disease_target_pair(target, disease)
    if dt_warnings:
        for warning in dt_warnings:
            print(f"\n[WARNING] Disease-target mismatch: {warning}")
        print(
            f"[INFO] Canonical path is target='{CANONICAL_TARGET}', disease='{CANONICAL_DISEASE}'. "
            "Proceeding with supplied values."
        )

    print("\n[Stage A] Chemical Sanity...")
    chemistry = run_chemistry_sanity(smiles, pubchem_lookup=pubchem_lookup)

    print("\n[Stage B] Target Engagement...")
    binding = run_binding_evaluation(smiles, target, reference_drug=reference_drug)
    resolved_reference = binding.get("reference_drug", reference_drug or "reference")

    print("\n[Stage C] ADMET Safety...")
    admet = run_admet_evaluation(smiles)

    print("\n[Clinical prep] Fetching QED and Lipinski from scorer...")
    qed_score, passes_lipinski = _get_qed_and_lipinski(smiles)

    print("\n[Stage D] Clinical Utility...")
    clinical = run_clinical_evaluation(
        smiles=smiles,
        target=target,
        disease=disease,
        reference_drug=resolved_reference,
        chemistry_result=chemistry,
        binding_result=binding,
        admet_result=admet,
        qed_score=qed_score,
        passes_lipinski=passes_lipinski,
    )

    final_decision = clinical["decision"]
    core_questions = _five_questions(chemistry, binding, admet, clinical)
    evidence_ledger = _build_evidence_ledger(chemistry, binding, admet, clinical, dt_warnings)
    binding_evidence = build_binding_evidence(binding)
    novelty_evidence = build_novelty_evidence(chemistry.get("novelty", {}))
    admet_evidence = build_admet_evidence(admet)

    decision_provenance = clinical.get("decision_provenance") or {}
    faculty_explanation = build_faculty_explanation_stack(
        {
            "reference_drug": resolved_reference,
            "novelty_status": novelty_evidence.get("novelty_status"),
            "novelty_closest_reference": novelty_evidence.get("novelty_closest_reference"),
            "novelty_tanimoto_score": novelty_evidence.get("novelty_tanimoto_score"),
            "novelty_threshold": novelty_evidence.get("novelty_threshold"),
            "novelty_reason": novelty_evidence.get("novelty_reason"),
            "novelty_provenance": novelty_evidence.get("novelty_provenance"),
            "binding_checked": binding_evidence.get("binding_checked"),
            "binding_state": binding_evidence.get("binding_state"),
            "binding_mode": binding_evidence.get("binding_mode"),
            "binding_score": binding.get("docking_score"),
            "reference_score": binding.get("reference_score"),
            "delta_vs_reference": binding.get("delta_vs_reference"),
            "real_docking_status": binding.get("real_docking_status"),
            "real_docking_failure": binding.get("real_docking_failure"),
            "final_binding_reason": binding_evidence.get("final_binding_reason"),
            "binding_provenance": binding_evidence.get("binding_provenance"),
            "overall_safety_flag": admet.get("overall_safety_flag"),
            "overall_safety_reason": admet_evidence.get("overall_safety_reason"),
            "admet_evidence_level": admet_evidence.get("admet_evidence_level"),
            "admet_provenance": admet_evidence.get("admet_provenance"),
            "hepatotoxicity_risk": admet.get("hepatotoxicity_risk", {}).get("level"),
            "herg_risk": admet.get("herg_risk", {}).get("level"),
            "cyp_interaction_risk": admet.get("cyp_risk", {}).get("level"),
            "final_decision": clinical.get("decision"),
            "decision_score": clinical.get("decision_score"),
            "decision_confidence_tier": decision_provenance.get("confidence_tier"),
            "decision_evidence_level": decision_provenance.get("evidence_level"),
            "final_decision_reason": decision_provenance.get("final_decision_reason"),
            "decision_provenance": decision_provenance,
        }
    )
    summary = faculty_explanation["overall_summary"]
    evidence_ledger["faculty_explanation"] = faculty_explanation

    result = {
        "smiles": smiles,
        "target": target,
        "disease": disease,
        "reference_drug": resolved_reference,
        "chemistry": chemistry,
        "binding": binding,
        "admet": admet,
        "clinical": clinical,
        "final_decision": final_decision,
        **binding_evidence,
        **novelty_evidence,
        **admet_evidence,
        "summary": summary,
        "faculty_explanation": faculty_explanation,
        "evidence_ledger": evidence_ledger,
        "pipeline_warnings": dt_warnings,
        "pipeline_version": "2.1",
        **core_questions,
        "decision_provenance": decision_provenance,
        "decision_provenance_explanation": decision_provenance.get("provenance_explanation"),
        "final_decision_reason": (decision_provenance or {}).get("final_decision_reason"),
        "decision_confidence_tier": (decision_provenance or {}).get("confidence_tier"),
        "decision_evidence_level": (decision_provenance or {}).get("evidence_level"),
    }

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETE - Decision: {final_decision.upper()}")
    print(f"Summary: {summary[:160]}...")
    print("=" * 70)
    return result


def validate_batch(
    smiles_list: list,
    target: str = "dpp4",
    disease: str = "diabetes",
    reference_drug: Optional[str] = None,
    pubchem_lookup: bool = False,
) -> list:
    results = []
    for index, smiles in enumerate(smiles_list, 1):
        print(f"\n[Batch] Molecule {index}/{len(smiles_list)}")
        result = validate_molecule(
            smiles,
            target=target,
            disease=disease,
            reference_drug=reference_drug,
            pubchem_lookup=pubchem_lookup,
        )
        results.append(result)

    results.sort(key=lambda item: item.get("clinical", {}).get("decision_score", 0.0), reverse=True)
    return results


if __name__ == "__main__":
    import json

    test_smiles = sys.argv[1] if len(sys.argv) > 1 else "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1"
    test_target = sys.argv[2] if len(sys.argv) > 2 else "insulin_receptor"
    test_disease = sys.argv[3] if len(sys.argv) > 3 else "diabetes"

    result = validate_molecule(
        smiles=test_smiles,
        target=test_target,
        disease=test_disease,
        pubchem_lookup=False,
    )

    print("\n" + "=" * 70)
    print("VALIDATION RESULT SUMMARY")
    print("=" * 70)
    print(f"Final decision : {result['final_decision'].upper()}")
    print(f"Decision score : {result['clinical']['decision_score']:.4f}")
    print()
    print("Core questions:")
    for question, answer in [
        ("Can it be synthesized?", result["can_be_synthesized"]),
        ("Is it likely novel?", result["likely_novel"]),
        ("Does it bind well vs standard?", result["binds_well_vs_standard"]),
        ("Is it likely safe to investigate?", result["likely_safe_to_investigate"]),
        ("Is it clinically worth pursuing?", result["clinically_worth_pursuing"]),
    ]:
        label = "YES" if answer is True else ("NO" if answer is False else "UNCERTAIN")
        print(f"  {question:<42} {label}")
    print()
    print("Full summary:")
    print(result["summary"])
    print()
    if result["clinical"]["explanation"]:
        print("Clinical evaluation explanation:")
        print(result["clinical"]["explanation"])
    print()
    print("Evidence ledger:")
    print(json.dumps(result["evidence_ledger"], indent=2))
