from __future__ import annotations


def test_api_stats_returns_expected_keys(api_client, api_module, monkeypatch, project_temp_dir):
    monkeypatch.setattr(api_module, "DB_PATH", project_temp_dir / "missing.db")

    def fake_load_csv(disease: str):
        if disease == "diabetes":
            return [
                {
                    "smiles": "CCO",
                    "clinical_score": "0.71",
                    "molecular_weight": "46.07",
                    "qed_score": "0.44",
                    "sa_score": "2.15",
                }
            ]
        return []

    monkeypatch.setattr(api_module, "_load_csv", fake_load_csv)

    response = api_client.get("/api/stats")

    assert response.status_code == 200
    payload = response.json()

    expected_keys = {
        "total_molecules",
        "best_clinical_score",
        "best_score",
        "best_molecule",
        "best_molecular_weight",
        "avg_qed_score",
        "avg_sa_score",
        "data_source",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["total_molecules"] >= 1
    assert payload["data_source"] == "csv"


def test_compare_payload_exposes_novelty_evidence(api_module):
    first_provenance = {
        "local_db_checked": True,
        "local_db_match_found": False,
        "reference_exact_match_checked": True,
        "reference_exact_match_found": False,
        "tanimoto_checked": True,
        "closest_reference": "metformin",
        "closest_reference_tanimoto": 0.32,
        "tanimoto_threshold": 0.70,
        "pubchem_checked": False,
        "pubchem_match_found": False,
        "pubchem_enabled": False,
        "final_novelty_status": "uncertain",
        "final_novelty_reason": "Uncertain novelty: closest approved reference is metformin (Tanimoto 0.32), below the 0.70 threshold, but PubChem was not checked.",
        "provenance_explanation": "Local database lookup checked, no match. Reference exact-match screen checked, no match. Tanimoto analogue screen checked against metformin (0.32), which is below the 0.70 threshold. PubChem lookup not enabled. Final novelty label: uncertain because Uncertain novelty: closest approved reference is metformin (Tanimoto 0.32), below the 0.70 threshold, but PubChem was not checked.",
    }
    second_provenance = {
        "local_db_checked": True,
        "local_db_match_found": False,
        "reference_exact_match_checked": True,
        "reference_exact_match_found": False,
        "tanimoto_checked": True,
        "closest_reference": "sitagliptin",
        "closest_reference_tanimoto": 0.74,
        "tanimoto_threshold": 0.70,
        "pubchem_checked": False,
        "pubchem_match_found": False,
        "pubchem_enabled": False,
        "final_novelty_status": "known",
        "final_novelty_reason": "Known repurposing lead: closest approved reference is sitagliptin (Tanimoto 0.74), which meets or exceeds the 0.70 threshold.",
        "provenance_explanation": "Local database lookup checked, no match. Reference exact-match screen checked, no match. Tanimoto analogue screen checked against sitagliptin (0.74), which meets or exceeds the 0.70 threshold. PubChem lookup not enabled. Final novelty label: known because Known repurposing lead: closest approved reference is sitagliptin (Tanimoto 0.74), which meets or exceeds the 0.70 threshold.",
    }
    first = {
        "smiles": "CCO",
        "rank_score": 0.71,
        "recommendation": "conditional computational lead",
        "final_decision": "conditional_advance",
        "decision_confidence_tier": "medium",
        "decision_evidence_level": "computed_descriptors_plus_proxy_binding",
        "summary": "Faculty summary for molecule A.",
        "binding_checked": True,
        "binding_mode": "scaffold_proxy",
        "binding_evidence_level": "proxy_screening",
        "final_binding_reason": "Scaffold proxy suggests moderate binding potential (proxy=-7.1). This is a structural estimate only, not a docking result.",
        "binding_provenance": {
            "binding_checked": True,
            "binding_mode": "scaffold_proxy",
            "binding_mode_reason": "Proxy score used because no active target-specific real-docking path is available for this request.",
            "real_docking_status": "unsupported_target",
            "real_docking_probe": {"target_supported": False, "blockers": ["unsupported target"]},
            "real_docking_failure": "unsupported target",
            "receptor_asset_checked": False,
            "receptor_asset_available": False,
            "docking_engine_checked": False,
            "docking_engine_available": False,
            "comparator_name": "sitagliptin",
            "comparator_score": -8.6,
            "candidate_score": -7.1,
            "delta_vs_reference": 1.5,
            "key_interactions_available": False,
            "evidence_level": "proxy_screening",
            "final_binding_reason": "Scaffold proxy suggests moderate binding potential (proxy=-7.1). This is a structural estimate only, not a docking result.",
            "provenance_explanation": "Scaffold proxy path was used intentionally because no active target-specific real-docking path was available.",
        },
        "binding_provenance_explanation": "Scaffold proxy path was used intentionally because no active target-specific real-docking path was available.",
        "delta_vs_reference": 1.5,
        "novelty_status": "uncertain",
        "novelty_closest_reference": "metformin",
        "novelty_tanimoto_score": 0.32,
        "novelty_threshold": 0.70,
        "novelty_reason": "Uncertain novelty: closest approved reference is metformin (Tanimoto 0.32), below the 0.70 threshold, but PubChem was not checked.",
        "novelty_provenance": first_provenance,
        "overall_safety_flag": "likely_safe",
        "overall_safety_reason": "Likely safe within this heuristic screen: hepatotoxicity, hERG, and CYP checks ran without medium- or high-risk alerts.",
        "overall_safety_method": "heuristic_alert_consensus_with_rdkit_descriptors",
        "admet_evidence_level": "heuristic_proxy_with_rdkit_descriptors",
        "admet_provenance": {
            "hepatotoxicity_checked": True,
            "hepatotoxicity_method": "structural_alerts_heuristic + rdkit_descriptors_proxy",
            "hepatotoxicity_alerts": [],
            "hepatotoxicity_score": 0.12,
            "herg_checked": True,
            "herg_method": "structural_pharmacophore_heuristic + rdkit_descriptors_proxy",
            "herg_alerts": [],
            "herg_score": 0.10,
            "cyp_checked": True,
            "cyp_method": "structural_alerts_heuristic + rdkit_descriptors_proxy",
            "cyp_alerts": [],
            "overall_safety_method": "heuristic_alert_consensus_with_rdkit_descriptors",
            "overall_safety_flag": "likely_safe",
            "overall_safety_reason": "Likely safe within this heuristic screen: hepatotoxicity, hERG, and CYP checks ran without medium- or high-risk alerts.",
            "evidence_level": "heuristic_proxy_with_rdkit_descriptors",
            "provenance_explanation": "All three ADMET checks ran with RDKit descriptor support and no alerts were triggered.",
        },
        "admet_provenance_explanation": "All three ADMET checks ran with RDKit descriptor support and no alerts were triggered.",
    }
    second = {
        "smiles": "CCN",
        "rank_score": 0.62,
        "recommendation": "low-priority computational result",
        "final_decision": "reject",
        "decision_confidence_tier": "low",
        "decision_evidence_level": "fallback_proxy",
        "summary": "Faculty summary for molecule B.",
        "binding_checked": True,
        "binding_mode": "fallback_proxy",
        "binding_evidence_level": "fallback_proxy",
        "final_binding_reason": "Only a fallback structural proxy was available (proxy=-5.4). Reason: real docking blocked.",
        "binding_provenance": {
            "binding_checked": True,
            "binding_mode": "fallback_proxy",
            "binding_mode_reason": "Proxy score used because the target has a nominal real-docking path, but it is currently blocked or failed: vina unavailable",
            "real_docking_status": "blocked",
            "real_docking_probe": {"target_supported": True, "blockers": ["vina unavailable"]},
            "real_docking_failure": "vina unavailable",
            "receptor_asset_checked": True,
            "receptor_asset_available": False,
            "docking_engine_checked": True,
            "docking_engine_available": False,
            "comparator_name": "sitagliptin",
            "comparator_score": -8.6,
            "candidate_score": -5.4,
            "delta_vs_reference": 3.2,
            "key_interactions_available": False,
            "evidence_level": "fallback_proxy",
            "final_binding_reason": "Only a fallback structural proxy was available (proxy=-5.4). Reason: real docking blocked.",
            "provenance_explanation": "Fallback proxy path was used because a nominal real-docking path exists but is currently blocked.",
        },
        "binding_provenance_explanation": "Fallback proxy path was used because a nominal real-docking path exists but is currently blocked.",
        "delta_vs_reference": 3.2,
        "novelty_status": "known",
        "novelty_closest_reference": "sitagliptin",
        "novelty_tanimoto_score": 0.74,
        "novelty_threshold": 0.70,
        "novelty_reason": "Known repurposing lead: closest approved reference is sitagliptin (Tanimoto 0.74), which meets or exceeds the 0.70 threshold.",
        "novelty_provenance": second_provenance,
        "overall_safety_flag": "caution",
        "overall_safety_reason": "Caution: the heuristic ADMET screen raised a non-low alert, specifically hERG (medium: Core hERG pharmacophore).",
        "overall_safety_method": "heuristic_alert_consensus_with_rdkit_descriptors",
        "admet_evidence_level": "heuristic_proxy_with_rdkit_descriptors",
        "admet_provenance": {
            "hepatotoxicity_checked": True,
            "hepatotoxicity_method": "structural_alerts_heuristic + rdkit_descriptors_proxy",
            "hepatotoxicity_alerts": [],
            "hepatotoxicity_score": 0.22,
            "herg_checked": True,
            "herg_method": "structural_pharmacophore_heuristic + rdkit_descriptors_proxy",
            "herg_alerts": ["Core hERG pharmacophore"],
            "herg_score": 0.52,
            "cyp_checked": True,
            "cyp_method": "structural_alerts_heuristic + rdkit_descriptors_proxy",
            "cyp_alerts": [],
            "overall_safety_method": "heuristic_alert_consensus_with_rdkit_descriptors",
            "overall_safety_flag": "caution",
            "overall_safety_reason": "Caution: the heuristic ADMET screen raised a non-low alert, specifically hERG (medium: Core hERG pharmacophore).",
            "evidence_level": "heuristic_proxy_with_rdkit_descriptors",
            "provenance_explanation": "All three ADMET checks ran. hERG raised one alert while hepatotoxicity and CYP stayed clear.",
        },
        "admet_provenance_explanation": "All three ADMET checks ran. hERG raised one alert while hepatotoxicity and CYP stayed clear.",
    }

    comparison = api_module._compare_molecules(first, second)

    assert comparison["preferred_novelty_status"] == "uncertain"
    assert comparison["preferred_novelty_reason"].startswith("Uncertain novelty:")
    assert "binding_summary" in comparison
    assert "novelty_summary" in comparison
    assert "safety_summary" in comparison
    assert "admet_summary" in comparison
    assert "decision_summary" in comparison
    assert comparison["molecules"][0]["binding_provenance"]["binding_checked"] is True
    assert comparison["preferred_binding_mode"] == "scaffold_proxy"
    assert comparison["molecules"][0]["novelty_closest_reference"] == "metformin"
    assert comparison["molecules"][0]["novelty_provenance"]["tanimoto_checked"] is True
    assert comparison["molecules"][0]["admet_provenance"]["hepatotoxicity_checked"] is True
    assert comparison["molecules"][0]["summary"] == "Faculty summary for molecule A."
    assert comparison["molecules"][0]["decision_confidence_tier"] == "medium"
    assert comparison["molecules"][1]["decision_confidence_tier"] == "low"
    assert comparison["molecules"][0]["faculty_explanation"]["overall_summary"]
    assert "novelty_provenance.final_novelty_reason" in comparison["molecules"][0]["faculty_explanation"]["overall_summary_provenance_pointers"]["summary_sources"]
    assert comparison["preferred_overall_safety_flag"] == "likely_safe"
    # summary sentences now come from the shared presentation payload
    cp = comparison["comparison_presentation"]
    assert "binding_provenance.binding_mode" in cp["left_candidate_summary"]["faculty_explanation"]["binding_summary"]["provenance_pointers"]["limiting_sources"]
    assert cp["section_summaries"]["novelty"]
    assert cp["section_summaries"]["admet"]
    assert cp["section_summaries"]["binding"]
    assert cp["section_summaries"]["decision"]
    assert cp["score_note"].startswith("Candidate ranked")
    assert comparison["novelty_summary"] == cp["section_summaries"]["novelty"]
    assert comparison["binding_summary"] == cp["section_summaries"]["binding"]
    assert comparison["admet_summary"] == cp["section_summaries"]["admet"]
    assert comparison["safety_summary"] == cp["section_summaries"]["admet"]
    assert comparison["decision_summary"] == cp["section_summaries"]["decision"]
    assert comparison["comparison_score_note"] == cp["score_note"]
    assert "comparison_presentation" in comparison
    assert cp["preferred_candidate"]["label"] == "Molecule A"
    assert cp["preferred_candidate"]["side"] == "left"
    assert cp["preferred_reason"].startswith("Molecule A has the higher evidence-weighted score")
    assert cp["confidence_limits"]
    assert cp["full_comparison_note"].startswith("Molecule A is currently preferred over Molecule B.")
    assert cp["left_candidate_summary"]["candidate_status"] == "conditional_advance"
    assert cp["left_candidate_summary"]["confidence_tier"] == "medium"
    assert cp["left_candidate_summary"]["main_strengths"]
    assert cp["right_candidate_summary"]["main_limitations"]
    assert cp["comparison_sections"]["novelty"]["left_candidate"]["section"]["summary"].startswith("Uncertain novelty:")
    assert cp["comparison_sections"]["binding"]["right_candidate"]["section"]["summary"]
    assert cp["comparison_sections"]["final_decision"]["right_candidate"]["section"]["provenance_pointers"]["summary_sources"]
