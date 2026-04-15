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
