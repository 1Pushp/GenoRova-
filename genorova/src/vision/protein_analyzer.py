"""
protein_analyzer.py — Genorova AI Protein Structure Analysis Module

PURPOSE:
Load and analyze protein structures (PDB files) to identify drug binding sites,
extract sequence information, and prepare structures for binding studies.

RESPONSIBILITIES:
1. Load PDB files (Protein Data Bank format)
2. Extract protein sequence
3. Parse 3D coordinates
4. Identify active sites and binding pockets
5. Calculate protein properties
6. Visualize protein structures
7. Identify key residues for drug targets

SUPPORTED TARGETS:
Diabetes:
- Insulin Receptor (PDB: 1IR3)
- GLUT4 (PDB: 6THA)
- DPP4 (PDB: 1NNY)

Infectious Disease:
- ACE2 (PDB: 6M0J) - COVID-19
- HIV Protease (PDB: 3OXC)
- Bacterial Gyrase (PDB: 2XCT)

EXAMPLE USAGE:
    from vision.protein_analyzer import ProteinAnalyzer
    
    analyzer = ProteinAnalyzer("path/to/1IR3.pdb")
    seq = analyzer.get_sequence()
    binding_site = analyzer.identify_binding_site()
    visualize = analyzer.get_structure_info()

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import os
from pathlib import Path
import logging
from datetime import datetime

try:
    from Bio import PDB
    from Bio.SeqUtils.IsoelectricPoint import IsoelectricPoint
    BIOPYTHON_AVAILABLE = True
except ImportError:
    BIOPYTHON_AVAILABLE = False
    print("[WARNING] BioPython not installed. Install with: pip install biopython")

import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# PROTEIN TARGETS DATABASE
# ============================================================================

PROTEIN_TARGETS = {
    # Diabetes targets
    "insulin_receptor": {
        "pdb_id": "1IR3",
        "name": "Insulin Receptor",
        "disease": "Type 2 Diabetes",
        "description": "Primary target for insulin-mimetic drugs",
        "binding_site_residues": [123, 156, 189, 220],  # Example residues
    },
    "glut4": {
        "pdb_id": "6THA",
        "name": "GLUT4 (Glucose Transporter)",
        "disease": "Type 2 Diabetes",
        "description": "Glucose transport protein, target for SGLT inhibitors",
        "binding_site_residues": [],
    },
    "dpp4": {
        "pdb_id": "1NNY",
        "name": "DPP-4 (Dipeptidyl Peptidase-4)",
        "disease": "Type 2 Diabetes",
        "description": "Target for DPP4 inhibitors (sitagliptin, etc.)",
        "binding_site_residues": [195, 205, 220, 245],
    },
    
    # Infectious disease targets
    "ace2": {
        "pdb_id": "6M0J",
        "name": "ACE2 Receptor",
        "disease": "COVID-19",
        "description": "SARS-CoV-2 attachment point",
        "binding_site_residues": [19, 24, 41, 42, 72, 82, 83],
    },
    "hiv_protease": {
        "pdb_id": "3OXC",
        "name": "HIV Protease",
        "disease": "HIV",
        "description": "Target for HIV protease inhibitors",
        "binding_site_residues": [],
    },
    "bacterial_gyrase": {
        "pdb_id": "2XCT",
        "name": "Bacterial Gyrase",
        "disease": "Bacterial Infection",
        "description": "Target for fluoroquinolone antibiotics",
        "binding_site_residues": [],
    },
}


# ============================================================================
# PROTEIN ANALYZER CLASS
# ============================================================================

class ProteinAnalyzer:
    """
    Load and analyze protein structures.
    """
    
    def __init__(self, pdb_file):
        """
        Initialize protein analyzer.
        
        Args:
            pdb_file (str): Path to PDB file
        """
        self.pdb_file = pdb_file
        self.structure = None
        self.model = None
        self.sequence = None
        self.atoms = []
        
        print(f"[PROTEIN] Loading PDB: {pdb_file}")
        
        if not BIOPYTHON_AVAILABLE:
            print("[WARNING] BioPython required for full functionality")
            self.structure = None
            return
        
        self._load_structure()
    
    def _load_structure(self):
        """Load PDB structure using BioPython."""
        try:
            parser = PDB.PDBParser(QUIET=True)
            self.structure = parser.get_structure("protein", self.pdb_file)
            
            # Get first model
            if len(self.structure) > 0:
                self.model = self.structure[0]
                print(f"[PROTEIN] Structure loaded: {len(list(self.model.get_residues()))} residues")
            
        except Exception as e:
            print(f"[ERROR] Failed to load PDB file: {e}")
            self.structure = None
    
    def get_sequence(self):
        """
        Extract protein amino acid sequence.
        
        Returns:
            str: One-letter amino acid sequence
        """
        if self.structure is None:
            return None
        
        try:
            three_to_one = {
                'ALA': 'A', 'ARG': 'R', 'ASN': 'N', 'ASP': 'D', 'CYS': 'C',
                'GLU': 'E', 'GLN': 'Q', 'GLY': 'G', 'HIS': 'H', 'ILE': 'I',
                'LEU': 'L', 'LYS': 'K', 'MET': 'M', 'PHE': 'F', 'PRO': 'P',
                'SER': 'S', 'THR': 'T', 'TRP': 'W', 'TYR': 'Y', 'VAL': 'V',
            }
            
            sequence = []
            for residue in self.model.get_residues():
                res_name = residue.get_resname()
                if res_name in three_to_one:
                    sequence.append(three_to_one[res_name])
            
            self.sequence = ''.join(sequence)
            print(f"[PROTEIN] Sequence length: {len(self.sequence)} aa")
            return self.sequence
        
        except Exception as e:
            print(f"[ERROR] Failed to extract sequence: {e}")
            return None
    
    def get_structure_info(self):
        """
        Get information about protein structure.
        
        Returns:
            dict: Structure information
        """
        if self.structure is None:
            return None
        
        info = {
            "pdb_file": self.pdb_file,
            "num_residues": len(list(self.model.get_residues())),
            "num_chains": len(list(self.model.get_chains())),
            "sequence_length": len(self.get_sequence()) if self.get_sequence() else 0,
        }
        
        # Get coordinate range
        coords = []
        for atom in self.model.get_atoms():
            coords.append(atom.get_coord())
        
        coords = np.array(coords)
        info["min_coords"] = coords.min(axis=0).tolist()
        info["max_coords"] = coords.max(axis=0).tolist()
        info["center"] = coords.mean(axis=0).tolist()
        
        print(f"[PROTEIN] Structure info: {len(info['num_residues'])} residues")
        
        return info
    
    def identify_binding_site(self, pocket_size=4.0):
        """
        Identify potential binding pocket (simplified).
        
        Args:
            pocket_size (float): Radius to search (Ų)
        
        Returns:
            dict: Binding pocket information
        """
        if self.structure is None:
            return None
        
        # Simplified: pocket = central residues
        residues = list(self.model.get_residues())
        center_idx = len(residues) // 2
        
        pocket_residues = residues[
            max(0, center_idx - 5) : min(len(residues), center_idx + 6)
        ]
        
        return {
            "center_residue": center_idx,
            "pocket_residues": len(pocket_residues),
            "description": "Simplified binding pocket (use docking software for accuracy)",
        }
    
    def get_residue_properties(self):
        """
        Calculate residue-level properties.
        
        Returns:
            dict: Properties
        """
        if self.structure is None:
            return None
        
        props = {
            "total_residues": len(list(self.model.get_residues())),
            "hydrophobic_residues": 0,
            "charged_residues": 0,
            "polar_residues": 0,
        }
        
        hydrophobic = {'ALA', 'CYS', 'LEU', 'MET', 'PHE', 'TRP', 'VAL', 'ILE'}
        charged = {'ARG', 'LYS', 'ASP', 'GLU'}
        polar = {'SER', 'THR', 'ASN', 'GLN'}
        
        for residue in self.model.get_residues():
            res_name = residue.get_resname()
            if res_name in hydrophobic:
                props["hydrophobic_residues"] += 1
            if res_name in charged:
                props["charged_residues"] += 1
            if res_name in polar:
                props["polar_residues"] += 1
        
        return props
    
    def get_surface_residues(self, threshold=14.0):
        """
        Identify surface-exposed residues (potential binding sites).
        
        Args:
            threshold (float): Distance threshold for surface definition
        
        Returns:
            list: Surface residue indices
        """
        if self.structure is None:
            return []
        
        # Simplified: residues with CA atoms at periphery
        surface_residues = []
        coords = []
        residues = []
        
        for residue in self.model.get_residues():
            if 'CA' in residue:
                coords.append(residue['CA'].get_coord())
                residues.append(residue)
        
        coords = np.array(coords)
        center = coords.mean(axis=0)
        
        for i, coord in enumerate(coords):
            dist = np.linalg.norm(coord - center)
            if dist > threshold:
                surface_residues.append(i)
        
        return surface_residues


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def download_pdb(pdb_id, output_dir="data/protein_structures/"):
    """
    Download PDB structure from RCSB.
    
    Args:
        pdb_id (str): PDB identifier (e.g., "1IR3")
        output_dir (str): Output directory
    
    Returns:
        str: Path to downloaded PDB file
    """
    if not BIOPYTHON_AVAILABLE:
        print("[ERROR] BioPython required for PDB downloads")
        return None
    
    print(f"[PDB] Downloading {pdb_id}...")
    
    try:
        from Bio.PDB import PDBList
        
        PDB  = PDBList()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        pdb_file = PDB.retrieve_pdb_file(
            pdb_id,
            pdir=str(output_dir),
            file_format="pdb"
        )
        
        print(f"[PDB] Downloaded: {pdb_file}")
        return pdb_file
    
    except Exception as e:
        print(f"[ERROR] Failed to download PDB: {e}")
        return None


def get_protein_info(protein_key):
    """
    Get information about a known protein target.
    
    Args:
        protein_key (str): Protein identifier
    
    Returns:
        dict: Protein information
    """
    if protein_key in PROTEIN_TARGETS:
        return PROTEIN_TARGETS[protein_key]
    else:
        print(f"[ERROR] Unknown protein: {protein_key}")
        print(f"Available: {list(PROTEIN_TARGETS.keys())}")
        return None


def list_available_proteins():
    """List all available protein targets."""
    print("\n[PROTEINS] Available targets:")
    print("-" * 70)
    
    for key, info in PROTEIN_TARGETS.items():
        print(f"\n{key} (PDB: {info['pdb_id']})")
        print(f"  Name: {info['name']}")
        print(f"  Disease: {info['disease']}")
        print(f"  Description: {info['description']}")
    
    print("\n" + "-" * 70)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("[TEST] protein_analyzer.py — Protein Structure Analysis")
    
    # Display available proteins
    list_available_proteins()
    
    # If no PDB files downloaded yet, just show the structure
    print("\n[TEST] protein_analyzer.py ready for use")
    print("[TEST] To use: download PDB file and pass path to ProteinAnalyzer()")
