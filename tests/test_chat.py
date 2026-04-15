from __future__ import annotations


def test_api_chat_returns_structured_payload(api_client, api_module, monkeypatch):
    monkeypatch.setattr(api_module, "_parse_chat_intent", lambda message: "score")

    def fake_score_smiles_payload(smiles: str):
        return {
            "smiles": smiles,
            "molecular_weight": 46.07,
            "logp": -0.1,
            "h_bond_donors": 1,
            "h_bond_acceptors": 1,
            "tpsa": 20.2,
            "qed_score": 0.44,
            "sa_score": 2.1,
            "passes_lipinski": True,
            "lipinski_violations": 0,
            "clinical_score": 0.71,
            "recommendation": "Strong candidate",
            "rotatable_bonds": 0,
            "ring_count": 0,
            "fraction_csp3": 1.0,
        }

    monkeypatch.setattr(api_module, "_score_smiles_payload", fake_score_smiles_payload)

    response = api_client.post(
        "/api/chat",
        json={
            "message": 'score "CCO"',
            "mode": "scientific",
            "history": [],
            "conversation_state": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["intent"] == "score"
    assert "summary" in payload and isinstance(payload["summary"], str)
    assert "candidate" in payload and payload["candidate"]["smiles"] == "CCO"
    assert "session_id" in payload
    assert "conversation_state" in payload
