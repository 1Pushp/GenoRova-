from __future__ import annotations

from genorova.src.data_loader import load_smiles_dataset


def test_load_smiles_dataset_returns_non_empty_smiles():
    dataset = load_smiles_dataset("moses", max_samples=20)

    smiles_list = dataset["smiles"].tolist()

    assert smiles_list
    assert all(isinstance(smiles, str) for smiles in smiles_list)
    assert all(smiles.strip() for smiles in smiles_list)
    assert all(smiles.lower() != "nan" for smiles in smiles_list)
    assert dataset.attrs["load_stats"]["returned_rows"] > 0
