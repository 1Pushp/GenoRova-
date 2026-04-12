"""
Genorova Vision Module

Provides molecular structure visualization and protein analysis capabilities.

Submodules:
- structure_visualizer: Generate 2D structure diagrams (PNG) from SMILES
- protein_analyzer: Parse and analyze protein structures from PDB files
- binding_site_detector: Predict binding affinity between molecules and proteins
"""

from .structure_visualizer import (
    visualize_molecule,
    batch_visualize,
    extract_molecular_formula,
    create_structure_summary,
    generate_structure_grid,
    add_smiles_label,
)

from .protein_analyzer import (
    ProteinAnalyzer,
    list_available_proteins,
)

from .binding_site_detector import (
    predict_binding_affinity,
    identify_interaction_residues,
    generate_binding_report,
    batch_predict_binding,
    rank_by_binding,
)

__all__ = [
    # structure_visualizer
    "visualize_molecule",
    "batch_visualize",
    "extract_molecular_formula",
    "create_structure_summary",
    "generate_structure_grid",
    "add_smiles_label",
    
    # protein_analyzer
    "ProteinAnalyzer",
    "list_available_proteins",
    
    # binding_site_detector
    "predict_binding_affinity",
    "identify_interaction_residues",
    "generate_binding_report",
    "batch_predict_binding",
    "rank_by_binding",
]

__version__ = "1.0.0"
__author__ = "Genorova AI Team"
__description__ = "Molecular visualization and protein analysis for drug discovery"

if __name__ == "__main__":
    print("Genorova Vision Module v1.0.0")
    print("Available modules:")
    print("  - structure_visualizer: SMILES → PNG structure diagrams")
    print("  - protein_analyzer: Parse PDB protein files")
    print("  - binding_site_detector: Predict molecular binding affinity")
