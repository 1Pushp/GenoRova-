"""
structure_visualizer.py — Genorova AI Molecular Structure Visualization

PURPOSE:
Read SMILES strings and generate 2D chemical structure diagrams as PNG images.
This is the simplest and most visual part of the vision module.

RESPONSIBILITIES:
1. Take SMILES string as input
2. Parse structure using RDKit
3. Generate 2D coordinates
4. Draw 2D chemical structure diagram
5. Highlight important atoms/features
6. Save as high-quality PNG image
7. Batch process multiple molecules

OUTPUT:
- PNG images of molecular structures
- One image per molecule
- Saved to outputs/molecule_images/

EXAMPLE USAGE:
    from vision.structure_visualizer import visualize_molecule, batch_visualize
    
    # Single molecule
    smiles = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
    img_path = visualize_molecule(smiles, output_dir="outputs/molecule_images/")
    
    # Batch
    smiles_list = [...]
    batch_visualize(smiles_list, output_dir="outputs/molecule_images/")

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import os
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import Draw, AllChem, Descriptors
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from tqdm import tqdm
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

IMG_SIZE = 400  # Pixels
HIGHLIGHT_IMPORTANT_ATOMS = True
ADD_ATOM_INDICES = False
ADD_MOLECULAR_FORMULA = True


# ============================================================================
# STRUCTURE VISUALIZATION
# ============================================================================

def visualize_molecule(smiles, output_dir="outputs/molecule_images/", 
                      molecule_id=None, size=(400, 400), add_label=True):
    """
    Generate 2D chemical structure diagram from SMILES.
    
    Args:
        smiles (str): SMILES string
        output_dir (str): Output directory
        molecule_id (str): Optional molecule identifier (used in filename)
        size (tuple): Image size (width, height)
        add_label (bool): Add SMILES label to image
    
    Returns:
        str: Path to saved image, or None if invalid
    """
    print(f"[VIZ] Visualizing: {smiles[:50]}...")
    
    # Validate SMILES
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print(f"[ERROR] Invalid SMILES: {smiles}")
        return None
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate 2D coordinates
    AllChem.Compute2DCoords(mol)
    
    # Generate image
    try:
        img = Draw.MolToImage(mol, size=size, kekulize=True)
        
        # Optionally add label
        if add_label:
            img = add_smiles_label(img, smiles)
        
        # Generate filename
        if molecule_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
            molecule_id = timestamp
        
        filename = f"molecule_{molecule_id}.png"
        filepath = Path(output_dir) / filename
        
        # Save
        img.save(str(filepath))
        print(f"[VIZ] Saved: {filepath}")
        
        return str(filepath)
    
    except Exception as e:
        print(f"[ERROR] Failed to visualize {smiles}: {e}")
        return None


def add_smiles_label(img, smiles, fontsize=12):
    """
    Add SMILES label to bottom of image.
    
    Args:
        img (PIL.Image): Image to label
        smiles (str): SMILES string
        fontsize (int): Font size
    
    Returns:
        PIL.Image: Image with label
    """
    # Create new image with extra space for text
    width, height = img.size
    new_height = height + 60
    
    new_img = Image.new('RGB', (width, new_height), color='white')
    new_img.paste(img, (0, 0))
    
    # Add text
    draw = ImageDraw.Draw(new_img)
    
    # Truncate long SMILES
    smiles_display = smiles if len(smiles) <= 50 else smiles[:47] + "..."
    
    # Draw text
    try:
        draw.text((10, height + 10), f"SMILES: {smiles_display}", fill='black')
    except:
        # Fallback if font loading fails
        draw.text((10, height + 10), f"SMILES: {smiles_display}", fill='black')
    
    return new_img


def batch_visualize(smiles_list, output_dir="outputs/molecule_images/",
                   add_labels=True, skip_invalid=True):
    """
    Visualize multiple molecules in batch.
    
    Args:
        smiles_list (list): List of SMILES strings
        output_dir (str): Output directory
        add_labels (bool): Add SMILES labels
        skip_invalid (bool): Skip invalid SMILES
    
    Returns:
        dict: Summary of batch visualization
    """
    print(f"\n[BATCH] Visualizing {len(smiles_list)} molecules...")
    
    successful = 0
    failed = 0
    output_paths = []
    
    for i, smiles in enumerate(tqdm(smiles_list, desc="Visualizing"), 1):
        img_path = visualize_molecule(
            smiles,
            output_dir=output_dir,
            molecule_id=f"{i:05d}",
            add_label=add_labels
        )
        
        if img_path:
            successful += 1
            output_paths.append(img_path)
        else:
            failed += 1
            if not skip_invalid:
                raise ValueError(f"Invalid SMILES at index {i}: {smiles}")
    
    print(f"\n[BATCH] Complete: {successful} successful, {failed} failed")
    
    return {
        "total": len(smiles_list),
        "successful": successful,
        "failed": failed,
        "output_paths": output_paths,
        "output_dir": output_dir,
    }


def extract_molecular_formula(smiles):
    """
    Extract molecular formula from SMILES.
    
    Args:
        smiles (str): SMILES string
    
    Returns:
        str: Molecular formula (e.g., "C9H8O4")
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return "Unknown"
        
        formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
        return formula
    except:
        return "Unknown"


def create_structure_summary(smiles, img_path):
    """
    Create summary info for a molecule's structure.
    
    Args:
        smiles (str): SMILES string
        img_path (str): Path to structure image
    
    Returns:
        dict: Summary information
    """
    mol = Chem.MolFromSmiles(smiles)
    
    if mol is None:
        return {
            "smiles": smiles,
            "valid": False,
            "image_path": img_path,
        }
    
    return {
        "smiles": smiles,
        "valid": True,
        "image_path": img_path,
        "molecular_formula": extract_molecular_formula(smiles),
        "molecular_weight": round(Descriptors.MolWt(mol), 2),
        "num_atoms": mol.GetNumAtoms(),
        "num_bonds": mol.GetNumBonds(),
        "num_rings": Descriptors.RingCount(mol),
        "num_aromatic_rings": Descriptors.NumAromaticRings(mol),
        "num_rotatable_bonds": Descriptors.NumRotatableBonds(mol),
        "num_h_donors": Descriptors.NumHDonors(mol),
        "num_h_acceptors": Descriptors.NumHAcceptors(mol),
    }


def generate_structure_grid(smiles_list, output_dir="outputs/molecule_images/",
                           grid_size=(3, 3), img_size=(200, 200)):
    """
    Generate grid of molecule structures (useful for comparisons).
    
    Args:
        smiles_list (list): List of SMILES strings
        output_dir (str): Output directory
        grid_size (tuple): Grid dimensions (rows, cols)
        img_size (tuple): Size of each sub-image
    
    Returns:
        str: Path to grid image
    """
    print(f"\n[GRID] Creating {grid_size[0]}x{grid_size[1]} grid for {len(smiles_list)} molecules...")
    
    mols = []
    for smiles in smiles_list:
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            mols.append(mol)
    
    if not mols:
        print("[ERROR] No valid molecules for grid")
        return None
    
    # Create grid image
    try:
        img = Draw.MolsToGridImage(
            mols[:grid_size[0] * grid_size[1]],
            molsPerRow=grid_size[1],
            subImgSize=img_size,
            legends=[extract_molecular_formula(Chem.MolToSmiles(mol)) for mol in mols],
        )
        
        # Save
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        grid_path = Path(output_dir) / f"structure_grid_{timestamp}.png"
        img.save(str(grid_path))
        
        print(f"[GRID] Saved: {grid_path}")
        return str(grid_path)
    
    except Exception as e:
        print(f"[ERROR] Failed to create grid: {e}")
        return None


# ============================================================================
# CLEAN API FUNCTIONS (requested by CLAUDE.md spec)
# ============================================================================

def generate_structure_image(smiles: str, filename: str = None,
                              output_dir: str = "outputs/molecule_images/",
                              size: tuple = (400, 300)) -> str:
    """
    Draw a 2D molecular structure from SMILES and save as PNG.

    This is the main entry point called by run_pipeline.py and report_generator.py
    after the VAE generates a new molecule.

    Args:
        smiles (str): SMILES string (e.g. "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2")
        filename (str): Output filename without path (auto-generated if None)
        output_dir (str): Directory to save image in
        size (tuple): Image size in pixels (width, height)

    Returns:
        str: Absolute path to saved PNG, or None if SMILES is invalid
    """
    print(f"[VIZ] Drawing structure: {smiles[:55]}{'...' if len(smiles) > 55 else ''}")

    # Parse molecule
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"[VIZ] Invalid SMILES — skipping")
            return None
    except Exception as e:
        print(f"[VIZ] RDKit error: {e}")
        return None

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Auto-generate filename from first few SMILES characters if not given
    if filename is None:
        safe = "".join(c for c in smiles[:12] if c.isalnum())
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"mol_{safe}_{timestamp}.png"

    # Ensure .png extension
    if not filename.lower().endswith(".png"):
        filename += ".png"

    save_path = Path(output_dir) / filename

    try:
        # Compute 2D coordinates for clean drawing
        AllChem.Compute2DCoords(mol)

        # Draw molecule
        img = Draw.MolToImage(mol, size=size, kekulize=True)

        # Add a white border and SMILES caption below
        border     = 4
        caption_h  = 32
        total_h    = img.height + 2 * border + caption_h
        canvas = Image.new("RGB", (img.width + 2 * border, total_h), "white")
        canvas.paste(img, (border, border))

        draw = ImageDraw.Draw(canvas)
        caption = smiles if len(smiles) <= 55 else smiles[:52] + "..."
        draw.text((border + 4, img.height + border + 6), caption, fill="#333333")

        canvas.save(str(save_path))
        print(f"[VIZ] Saved: {save_path.name}  ({size[0]}x{size[1]}px)")
        return str(save_path)

    except Exception as e:
        print(f"[VIZ] Draw error: {e}")
        return None


def generate_comparison_grid(smiles_list: list, title: str = "Genorova AI Top Candidates",
                              output_dir: str = "outputs/molecule_images/",
                              cols: int = 3, sub_size: tuple = (300, 250)) -> str:
    """
    Draw multiple molecules in a grid and save as a single PNG.

    Used to create the comparison panel shown in the HTML report and
    to visualise the top candidates side by side.

    Args:
        smiles_list (list): List of SMILES strings
        title (str): Title text printed above the grid
        output_dir (str): Directory to save the grid image
        cols (int): Number of columns in the grid
        sub_size (tuple): Size of each individual molecule cell (w, h)

    Returns:
        str: Path to saved grid PNG, or None if all SMILES invalid
    """
    print(f"\n[GRID] Creating comparison grid for {len(smiles_list)} molecules...")
    print(f"       Title: {title}")

    # Parse all valid molecules
    mols   = []
    labels = []
    for smi in smiles_list:
        try:
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                AllChem.Compute2DCoords(mol)
                mols.append(mol)
                # Use molecular formula as label
                try:
                    formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
                except Exception:
                    formula = smi[:20]
                labels.append(formula)
        except Exception:
            pass

    if not mols:
        print("[GRID] No valid molecules — cannot create grid")
        return None

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        # RDKit grid drawing
        grid_img = Draw.MolsToGridImage(
            mols,
            molsPerRow=cols,
            subImgSize=sub_size,
            legends=labels,
        )

        # Add title banner above grid
        title_h = 50
        total_w = grid_img.width
        total_h = grid_img.height + title_h
        canvas  = Image.new("RGB", (total_w, total_h), "white")
        canvas.paste(grid_img, (0, title_h))

        draw = ImageDraw.Draw(canvas)
        # Centre the title
        try:
            title_x = max(10, (total_w - len(title) * 8) // 2)
        except Exception:
            title_x = 10
        draw.text((title_x, 14), title, fill="#1a1a2e")

        # Save
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:30].strip()
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        grid_name  = f"grid_{safe_title.replace(' ', '_')}_{timestamp}.png"
        grid_path  = Path(output_dir) / grid_name
        canvas.save(str(grid_path))

        print(f"[GRID] Saved: {grid_path.name}  ({total_w}x{total_h}px, {len(mols)} molecules)")
        return str(grid_path)

    except Exception as e:
        print(f"[GRID] Error creating grid: {e}")
        return None


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 65)
    print("  STRUCTURE VISUALIZER TEST — Genorova AI")
    print("=" * 65)

    # Three molecules specified in spec
    test_molecules = {
        "Best infection candidate (clinical score 0.9649)":
            "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2",
        "Metformin (diabetes reference drug)":
            "CN(C)C(=N)NC(=N)N",
        "Aspirin (analgesic reference)":
            "CC(=O)Oc1ccccc1C(=O)O",
    }

    output_dir = "outputs/molecule_images/"

    # Test generate_structure_image()
    print("\n[TEST 1] Testing generate_structure_image()...")
    saved_paths = []
    for label, smi in test_molecules.items():
        print(f"\n  Molecule: {label}")
        path = generate_structure_image(
            smiles     = smi,
            filename   = f"test_{label[:20].replace(' ', '_')}.png",
            output_dir = output_dir,
            size       = (400, 300),
        )
        if path:
            saved_paths.append(path)
            print(f"  [OK] Image saved: {path}")
        else:
            print(f"  [FAIL] Could not draw molecule")

    # Test generate_comparison_grid()
    print("\n[TEST 2] Testing generate_comparison_grid()...")
    grid_path = generate_comparison_grid(
        smiles_list = list(test_molecules.values()),
        title       = "Genorova AI — Test Candidates",
        output_dir  = output_dir,
        cols        = 3,
    )
    if grid_path:
        print(f"  [OK] Grid saved: {grid_path}")
    else:
        print(f"  [FAIL] Grid generation failed")

    print(f"\n{'='*65}")
    print(f"TEST COMPLETE: {len(saved_paths)}/3 individual images + 1 grid")
    print(f"Output directory: {output_dir}")
    print(f"{'='*65}")
