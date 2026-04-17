from __future__ import annotations


def test_score_endpoint_returns_validation_ledger(api_client, api_module, monkeypatch, project_temp_dir):
    monkeypatch.setattr(api_module, "DB_PATH", project_temp_dir / "missing.db")

    response = api_client.post("/score", json={"smiles": "CCO"})

    assert response.status_code == 200
    payload = response.json()

    assert payload["target"] == "dpp4"
    assert payload["reference_drug"] == "sitagliptin"
    assert "validation" in payload
    assert "evidence_ledger" in payload
    assert "final_decision" in payload
    assert "docking_mode" in payload
    assert "binding_mode_reason" in payload
    assert "real_docking_status" in payload


def test_generate_endpoint_marks_inactive_infection_story_honestly(api_client):
    response = api_client.post("/generate", json={"disease": "infection", "count": 3})

    assert response.status_code == 200
    payload = response.json()

    assert payload["count_returned"] == 0
    assert payload["generation_status"] == "inactive_science_path"
    assert payload["trust"]["validation_status"] == "inactive_science_path"
