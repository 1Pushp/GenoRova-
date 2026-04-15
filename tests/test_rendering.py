from __future__ import annotations


def test_molecule_svg_renders_valid_smiles(api_module):
    svg = api_module._molecule_svg("CCO")

    assert svg is not None
    assert "<svg" in svg.lower()


def test_molecule_svg_handles_invalid_smiles(api_module):
    svg = api_module._molecule_svg("not_a_smiles")

    assert svg is None
