from __future__ import annotations

from genorova.src.science_evidence import (
    ACTIVE_PROGRAM_LABEL,
    ACTIVE_REFERENCE_DRUG,
    ACTIVE_TARGET,
    evaluate_candidate,
)


def test_evaluate_candidate_returns_required_evidence_fields():
    payload = evaluate_candidate(
        "CCO",
        result_source="test_case",
        fallback_used=False,
    )

    expected_keys = {
        "smiles",
        "clinical_score",
        "model_score",
        "program_label",
        "target",
        "reference_drug",
        "novelty_status",
        "docking_mode",
        "binding_mode_reason",
        "reference_score",
        "delta_vs_reference",
        "real_docking_status",
        "real_docking_failure",
        "hepatotoxicity_risk",
        "herg_risk",
        "cyp_interaction_risk",
        "final_decision",
        "confidence_level",
        "evidence_level",
        "validation",
        "evidence_ledger",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["program_label"] == ACTIVE_PROGRAM_LABEL
    assert payload["target"] == ACTIVE_TARGET
    assert payload["reference_drug"] == ACTIVE_REFERENCE_DRUG


def test_evaluate_candidate_known_reference_is_not_marketed_as_novel():
    payload = evaluate_candidate(
        "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
        result_source="test_case",
        fallback_used=True,
    )

    assert payload["reference_drug"] == ACTIVE_REFERENCE_DRUG
    assert payload["novelty_status"] == "known"
    assert payload["evidence_ledger"]["known_vs_uncertain_vs_potentially_novel"] == "known"
