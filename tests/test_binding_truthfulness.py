from __future__ import annotations

from validation.binding import target_binder
from validation.clinical.clinical_evaluator import run_clinical_evaluation
from validation.ranking import best_candidate_label


def test_binding_fallback_proxy_surfaces_blocker_context(monkeypatch):
    monkeypatch.setattr(target_binder, "_try_load_rdkit", lambda: True)
    monkeypatch.setattr(
        target_binder,
        "_build_real_docking_probe",
        lambda target_key: {
            "target_key": target_key,
            "target_supported": True,
            "rdkit_available": True,
            "vina_executable": "vina",
            "vina_available": True,
            "docking_import_ok": True,
            "dock_molecule_available": False,
            "receptor_asset": None,
            "status": "blocked",
            "blockers": ["dock_molecule missing for active DPP4 path"],
        },
    )
    monkeypatch.setattr(
        target_binder,
        "_scaffold_proxy_score",
        lambda smiles, target_key: (-7.2, "proxy explanation"),
    )

    result = target_binder.run_binding_evaluation("CCO", "dpp4")

    assert result["mode"] == "fallback_proxy"
    assert result["real_docking_status"] == "blocked"
    assert result["real_docking_failure"] == "dock_molecule missing for active DPP4 path"
    assert "dock_molecule missing" in result["mode_reason"]
    assert result["real_docking_probe"]["blockers"] == ["dock_molecule missing for active DPP4 path"]


def test_proxy_only_known_lead_is_capped_to_conditional_advance():
    chemistry_result = {
        "valid_smiles": True,
        "sa_score": 2.4,
        "sa_flag": "synthesizable",
        "sa_score_source": "rdkit_computed",
        "is_pains": False,
        "novelty": {
            "flag": "known_repurposing_lead",
            "pubchem_checked": False,
        },
        "rdkit_available": True,
    }
    binding_result = {
        "mode": "fallback_proxy",
        "docking_score": -8.9,
        "reference_score": -8.1,
        "delta_vs_reference": -0.8,
        "mode_reason": "real docking helper is missing",
        "real_docking_failure": "dock_molecule missing",
    }
    admet_result = {
        "overall_safety_flag": "likely_safe",
        "safety_score": 0.92,
        "hepatotoxicity_risk": {"level": "low"},
        "herg_risk": {"level": "low"},
        "cyp_risk": {"level": "low"},
    }

    result = run_clinical_evaluation(
        smiles="CCO",
        target="dpp4",
        disease="diabetes",
        reference_drug="sitagliptin",
        chemistry_result=chemistry_result,
        binding_result=binding_result,
        admet_result=admet_result,
        qed_score=0.82,
        passes_lipinski=True,
    )

    assert result["decision"] == "conditional_advance"
    assert any("known or repurposing lead" in item for item in result["conditions"])
    assert any("fallback proxy binding evidence" in item for item in result["conditions"])


def test_ranking_requires_real_docking_for_provisional_best_candidate():
    candidate = {
        "final_decision": "advance",
        "rank_score": 0.91,
        "clinical_score": 0.91,
        "overall_safety_flag": "likely_safe",
        "is_pains": False,
        "docking_mode": "fallback_proxy",
        "confidence_level": "medium",
    }

    assert best_candidate_label(candidate) == "conditional computational lead"
