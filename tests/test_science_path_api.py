from __future__ import annotations


def test_score_endpoint_returns_validation_ledger(api_client, api_module, monkeypatch, project_temp_dir):
    monkeypatch.setattr(api_module, "DB_PATH", project_temp_dir / "missing.db")

    response = api_client.post("/score", json={"smiles": "CCO"})

    assert response.status_code == 200
    payload = response.json()

    assert payload["target"] == "bca"
    assert payload["reference_drug"] == "acetazolamide"
    assert payload["clinical_score"] >= 0.0
    assert "model_score" not in payload
    assert "rank_score" not in payload
    assert "validation" in payload
    assert "evidence_ledger" in payload
    assert "final_decision" in payload
    assert "docking_mode" in payload
    assert payload["binding_truth"] == "PREDICTED_OFFLINE"
    assert payload["binding_claim"] == "predicted binding (Vina-validated offline)"
    assert "binding_mode_reason" in payload
    assert "real_docking_status" in payload
    assert "binding_provenance" in payload
    assert "novelty_closest_reference" in payload
    assert "novelty_tanimoto_score" in payload
    assert "novelty_threshold" in payload
    assert "novelty_reason" in payload
    assert "novelty_provenance" in payload
    assert "overall_safety_reason" in payload
    assert "admet_provenance" in payload
    assert "faculty_explanation" in payload
    assert "novelty_reason" in payload["validation"]
    assert "binding_provenance" in payload["validation"]
    assert "novelty_provenance" in payload["validation"]
    assert "overall_safety_reason" in payload["validation"]
    assert "admet_provenance" in payload["validation"]
    assert "faculty_explanation" in payload["validation"]
    assert payload["faculty_explanation"]["overall_summary"]
    assert payload["validation"]["faculty_explanation"]["decision_summary"]["summary"]
    assert payload["faculty_explanation"]["novelty_summary"]["provenance_pointers"]["summary_sources"]
    assert payload["faculty_explanation"]["overall_summary_provenance_pointers"]["summary_sources"]


def test_generate_endpoint_marks_inactive_diabetes_story_honestly(api_client):
    # Diabetes/DPP4 is now the archived path; the active program is infection/bCA.
    response = api_client.post("/generate", json={"disease": "diabetes", "count": 3})

    assert response.status_code == 200
    payload = response.json()

    assert payload["count_returned"] == 0
    assert payload["generation_status"] == "inactive_science_path"
    assert payload["trust"]["validation_status"] == "inactive_science_path"


def test_generate_endpoint_surfaces_real_generation_mode(api_client, api_module, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "_attempt_runtime_generation",
        lambda disease, count: (
            [{"smiles": "CCO"}, {"smiles": "CCN"}],
            {
                "attempted": True,
                "selected_backend": "smilesvae_ar",
                "selected_backend_label": "autoregressive SMILESVAE checkpoint",
                "sample_size": 40,
                "attempts": [],
                "failure_reason": None,
                "disease": disease,
            },
        ),
    )
    monkeypatch.setattr(api_module, "_load_csv", lambda disease: [])
    monkeypatch.setattr(api_module, "_load_db_top", lambda count=10: [])

    def fake_evaluate_candidate_rows(rows, **kwargs):
        return [
            {
                "smiles": "CCO",
                "clinical_score": 0.71,
                "qed_score": 0.44,
                "sa_score": 2.15,
                "molecular_weight": 46.07,
                "logp": -0.01,
                "recommendation": "conditional computational lead",
                "binding_mode": "fallback_proxy",
                "binding_mode_reason": "target docking path blocked",
                "binding_provenance": {"binding_mode": "fallback_proxy"},
                "validation": {},
                "final_decision": "conditional_advance",
                "validation_status": "canonical_selective_candidate_screen",
            }
        ]

    monkeypatch.setattr(api_module, "evaluate_candidate_rows", fake_evaluate_candidate_rows)
    monkeypatch.setattr(api_module, "_store_molecule", lambda *args, **kwargs: None)

    response = api_client.post("/generate", json={"disease": "infection", "count": 3})

    assert response.status_code == 200
    payload = response.json()

    assert payload["generation_mode"] == "real_generation"
    assert payload["generation_truth"] == "REAL"
    assert payload["generation_status"] == "runtime_model_generation"
    assert payload["molecules"][0]["clinical_score"] == 0.71
    assert payload["molecules"][0]["binding_truth"] == "PREDICTED_OFFLINE"
    assert payload["molecules"][0]["binding_claim"] == "predicted binding (Vina-validated offline)"
