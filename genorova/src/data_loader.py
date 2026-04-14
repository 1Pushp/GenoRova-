"""
Genorova AI — Molecular Data Loader
====================================

This module loads SMILES strings from files, validates them using RDKit,
removes duplicates and invalid molecules, and returns a clean dataset
ready for model training.

RESPONSIBILITIES:
1. Load SMILES strings from ChEMBL database or CSV files
2. Parse molecular data and extract key properties (MW, LogP, HBD, HBA)
3. Validate each molecule using RDKit
4. Remove duplicates and invalid SMILES
5. Filter by drug-likeness criteria (Lipinski's Rule of 5)
6. Return cleaned Pandas DataFrame ready for preprocessing

INPUT:
- CSV file with SMILES column
- Python list of SMILES strings
- ChEMBL database (future enhancement)

OUTPUT:
- Pandas DataFrame with columns: smiles, molecular_weight, logp, hbd, hba, passes_lipinski, is_valid

KEY FUNCTIONS:
- load_smiles_from_csv() — load SMILES from CSV file
- load_smiles_from_list() — load SMILES from Python list
- validate_smiles() — validate individual SMILES using RDKit
- process_smiles_data() — master function to validate and process dataset
- load_and_process() — main entry point

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings

# Suppress RDKit warnings for cleaner output
warnings.filterwarnings("ignore")

# RDKit imported lazily inside functions (prevents Windows DLL load failure)
# Actual imports happen inside validate_smiles(), calculate_molecular_weight(), etc.
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Crippen
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
except ImportError:
    Chem = None
    Descriptors = None
    Crippen = None


def load_smiles_from_csv(file_path):
    """
    Load SMILES strings from a CSV file.

    Expects a CSV file with a column named 'smiles' or 'SMILES'.
    If neither exists, uses the first column.

    Args:
        file_path (str): Path to the CSV file

    Returns:
        list: List of SMILES strings
    """
    print(f"\n[*] Loading SMILES from CSV: {file_path}")

    try:
        df = pd.read_csv(file_path)
        print(f"   [OK] CSV loaded successfully. Shape: {df.shape}")

        # Try to find SMILES column
        smiles_column = None
        for col in df.columns:
            if col.lower() in ['smiles', 'smi', 'smile']:
                smiles_column = col
                break

        # If no SMILES column found, use the first column
        if smiles_column is None:
            smiles_column = df.columns[0]
            print(f"   [!] No 'smiles' column found. Using column: '{smiles_column}'")
        else:
            print(f"   [OK] Using SMILES column: '{smiles_column}'")

        smiles_list = df[smiles_column].astype(str).tolist()
        print(f"   [OK] Extracted {len(smiles_list)} SMILES strings")

        return smiles_list

    except FileNotFoundError:
        print(f"   [ERROR] File not found at {file_path}")
        raise
    except Exception as e:
        print(f"   [ERROR] Error loading CSV: {str(e)}")
        raise


def load_smiles_from_list(smiles_list):
    """
    Load SMILES strings directly from a Python list.

    Args:
        smiles_list (list): List of SMILES strings

    Returns:
        list: The input list (for consistency with file loading)
    """
    print(f"\n[*] Loading {len(smiles_list)} SMILES strings from list")
    return smiles_list


def validate_smiles(smiles_string):
    """
    Validate a single SMILES string using RDKit.

    Args:
        smiles_string (str): SMILES string to validate

    Returns:
        tuple: (is_valid: bool, mol_object: Mol or None)
    """
    try:
        # Try to create molecule from SMILES
        mol = Chem.MolFromSmiles(smiles_string)

        if mol is None:
            return False, None

        # Additional checks for valid molecules
        if mol.GetNumAtoms() == 0:
            return False, None

        return True, mol

    except:
        return False, None


def calculate_molecular_weight(mol_object):
    """
    Calculate molecular weight (MW) from RDKit molecule object.

    Args:
        mol_object: RDKit Mol object

    Returns:
        float: Molecular weight in Daltons (Da)
    """
    if mol_object is None:
        return np.nan

    return Descriptors.MolWt(mol_object)


def calculate_logp(mol_object):
    """
    Calculate LogP (lipophilicity) from RDKit molecule object.

    Args:
        mol_object: RDKit Mol object

    Returns:
        float: LogP value
    """
    if mol_object is None:
        return np.nan

    return Crippen.MolLogP(mol_object)


def check_lipinski_rule_of_5(mol_object):
    """
    Check if molecule passes Lipinski's Rule of 5 (drug-likeness filter).

    Lipinski's Rule of 5:
    - Molecular weight <= 500 Da
    - LogP <= 5
    - H-bond donors <= 5
    - H-bond acceptors <= 10

    Args:
        mol_object: RDKit Mol object

    Returns:
        bool: True if passes all criteria, False otherwise
    """
    if mol_object is None:
        return False

    mw = Descriptors.MolWt(mol_object)
    logp = Crippen.MolLogP(mol_object)
    hbd = Descriptors.NumHDonors(mol_object)
    hba = Descriptors.NumHAcceptors(mol_object)

    passes_lipinski = (mw <= 500) and (logp <= 5) and (hbd <= 5) and (hba <= 10)

    return passes_lipinski


def process_smiles_data(smiles_list, remove_duplicates=True, validate=True):
    """
    Process a list of SMILES strings: validate, remove duplicates, calculate properties.

    Args:
        smiles_list (list): List of SMILES strings
        remove_duplicates (bool): If True, remove duplicate SMILES
        validate (bool): If True, validate each SMILES using RDKit

    Returns:
        pd.DataFrame: Cleaned dataset with columns:
                     - smiles: SMILES string
                     - molecular_weight: MW in Daltons
                     - logp: LogP (lipophilicity)
                     - hbd: Hydrogen bond donors
                     - hba: Hydrogen bond acceptors
                     - passes_lipinski: Boolean flag for drug-likeness
                     - is_valid: Boolean flag for valid SMILES
    """
    print(f"\n[*] Processing {len(smiles_list)} SMILES strings...")

    initial_count = len(smiles_list)

    # Remove duplicates early if requested
    if remove_duplicates:
        smiles_list = list(dict.fromkeys(smiles_list))  # preserves order
        removed_dupes = initial_count - len(smiles_list)
        print(f"   [OK] Removed {removed_dupes} duplicates")

    # Process each SMILES
    data = {
        'smiles': [],
        'molecular_weight': [],
        'logp': [],
        'hbd': [],
        'hba': [],
        'passes_lipinski': [],
        'is_valid': []
    }

    invalid_count = 0

    for i, smiles in enumerate(smiles_list):
        if (i + 1) % 100 == 0:
            print(f"   [...] Processed {i + 1}/{len(smiles_list)} SMILES...")

        # Validate SMILES
        is_valid, mol = validate_smiles(smiles)

        if not is_valid and validate:
            invalid_count += 1
            continue

        # Calculate properties
        mw = calculate_molecular_weight(mol) if is_valid else np.nan
        logp = calculate_logp(mol) if is_valid else np.nan
        hbd = Descriptors.NumHDonors(mol) if is_valid else np.nan
        hba = Descriptors.NumHAcceptors(mol) if is_valid else np.nan
        passes_lipinski = check_lipinski_rule_of_5(mol) if is_valid else False

        # Store data
        data['smiles'].append(smiles)
        data['molecular_weight'].append(mw)
        data['logp'].append(logp)
        data['hbd'].append(hbd)
        data['hba'].append(hba)
        data['passes_lipinski'].append(passes_lipinski)
        data['is_valid'].append(is_valid)
 
    # Convert to DataFrame
    df = pd.DataFrame(data)

    print(f"   [OK] Processed all SMILES")
    print(f"   [!]  Invalid SMILES removed: {invalid_count}")
    print(f"   [OK] Final dataset size: {len(df)} molecules")

    return df


def save_dataset(df, output_path):
    """
    Save processed dataset to CSV file.

    Args:
        df (pd.DataFrame): DataFrame to save
        output_path (str): Path where to save the CSV file
    """
    print(f"\n[*] Saving dataset to: {output_path}")

    # Create parent directories if needed
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path, index=False)
    print(f"   [OK] Dataset saved successfully!")
    print(f"   [OK] Rows: {len(df)}, Columns: {len(df.columns)}")


def print_dataset_summary(df):
    """
    Print summary statistics of the processed dataset.

    Args:
        df (pd.DataFrame): Processed dataset
    """
    print(f"\n[SUMMARY] Dataset Summary")
    print(f"   -----------------------------------------")
    print(f"   Total molecules:          {len(df)}")
    print(f"   Valid SMILES:             {df['is_valid'].sum()} ({100*df['is_valid'].sum()/len(df):.1f}%)")
    print(f"   Invalid SMILES:           {(~df['is_valid']).sum()} ({100*(~df['is_valid']).sum()/len(df):.1f}%)")
    print(f"   Pass Lipinski's Rule:     {df['passes_lipinski'].sum()} ({100*df['passes_lipinski'].sum()/len(df):.1f}%)")
    print(f"\n   Molecular Weight (Da):")
    print(f"      Mean:                 {df['molecular_weight'].mean():.2f}")
    print(f"      Min:                  {df['molecular_weight'].min():.2f}")
    print(f"      Max:                  {df['molecular_weight'].max():.2f}")
    print(f"\n   LogP (Lipophilicity):")
    print(f"      Mean:                 {df['logp'].mean():.2f}")
    print(f"      Min:                  {df['logp'].min():.2f}")
    print(f"      Max:                  {df['logp'].max():.2f}")
    print(f"\n   H-Bond Donors:")
    print(f"      Mean:                 {df['hbd'].mean():.2f}")
    print(f"      Max:                  {df['hbd'].max():.0f}")
    print(f"\n   H-Bond Acceptors:")
    print(f"      Mean:                 {df['hba'].mean():.2f}")
    print(f"      Max:                  {df['hba'].max():.0f}")
    print(f"   -----------------------------------------\n")


def load_and_process(input_path=None, smiles_list=None, output_path=None):
    """
    Main function to load, validate, and process molecular data.

    Either provide input_path (CSV file) OR smiles_list (Python list), not both.

    Args:
        input_path (str): Path to CSV file with SMILES data
        smiles_list (list): List of SMILES strings
        output_path (str): Optional path to save cleaned dataset

    Returns:
        pd.DataFrame: Cleaned dataset
    """
    print("\n" + "="*60)
    print("  GENOROVA AI — Molecular Data Loader")
    print("="*60)

    # Load SMILES from either file or list
    if input_path is not None:
        smiles = load_smiles_from_csv(input_path)
    elif smiles_list is not None:
        smiles = load_smiles_from_list(smiles_list)
    else:
        raise ValueError("Must provide either input_path or smiles_list")

    # Process the data
    df = process_smiles_data(smiles)

    # Print summary
    print_dataset_summary(df)

    # Save if output path provided
    if output_path is not None:
        save_dataset(df, output_path)

    print("="*60 + "\n")

    return df


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__" and False:

    # Test data: 5 known valid SMILES strings for common drugs
    test_smiles = [
        "CC(=O)Oc1ccccc1C(=O)O",        # Aspirin
        "CN(C)C(=N)NC(=N)N",             # Metformin
        "Cn1cnc2c1c(=O)n(c(=O)n2C)C",  # Caffeine
        "CC(=O)Nc1ccc(O)cc1",            # Paracetamol (Acetaminophen)
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O"    # Ibuprofen
    ]

    print("\n" + "="*60)
    print("  RUNNING DATA LOADER TEST WITH 5 KNOWN VALID SMILES")
    print("="*60)

    # Process the test data
    df_test = load_and_process(
        smiles_list=test_smiles,
        output_path="data/processed/test_smiles.csv"
    )

    # Print detailed results
    print("\n[RESULTS] Detailed Results:")
    print(df_test.to_string(index=False))

    print("\n[SUCCESS] Data loader test completed successfully!")


# ============================================================================
# MODERN DATASET LOADER FOR MOSES / ChEMBL SUBSET
# ============================================================================

import argparse
import gzip
import os
from typing import Dict, Iterable, Optional

import urllib.request


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
MOSES_DIR = DATA_DIR / "moses"
CHEMBL_DIR = DATA_DIR / "chembl_subset"
DEFAULT_TIMEOUT = 120

MOSES_URLS: Dict[str, Iterable[str]] = {
    "train": (
        "https://media.githubusercontent.com/media/molecularsets/moses/master/moses/dataset/data/train.csv.gz",
        "https://raw.githubusercontent.com/molecularsets/moses/master/moses/dataset/data/train.csv.gz",
    ),
    "test": (
        "https://media.githubusercontent.com/media/molecularsets/moses/master/moses/dataset/data/test.csv.gz",
        "https://raw.githubusercontent.com/molecularsets/moses/master/moses/dataset/data/test.csv.gz",
    ),
}


def _download_to_path(urls: Iterable[str], destination: Path) -> Path:
    """Try a sequence of URLs until one successfully downloads."""
    last_error: Optional[Exception] = None
    destination.parent.mkdir(parents=True, exist_ok=True)

    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT) as response:
                with open(destination, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
            return destination
        except Exception as exc:
            last_error = exc
            destination.unlink(missing_ok=True)

    raise RuntimeError(f"Failed to download dataset file to {destination}") from last_error


def _gunzip_file(source_gz: Path, destination_csv: Path) -> Path:
    destination_csv.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(source_gz, "rb") as src, open(destination_csv, "wb") as dst:
        dst.write(src.read())
    return destination_csv


def _find_smiles_column(df: pd.DataFrame) -> str:
    for column in df.columns:
        if column.lower() in {"smiles", "smi", "smile"}:
            return column
    return df.columns[0]


def download_moses() -> Dict[str, Path]:
    """
    Fetch and cache the MOSES train/test splits under genorova/data/moses/.

    Returns:
        dict: {"train": Path(...), "test": Path(...)}
    """
    cached = {
        "train": MOSES_DIR / "train.csv",
        "test": MOSES_DIR / "test.csv",
    }
    if all(path.exists() for path in cached.values()):
        return cached

    for split, urls in MOSES_URLS.items():
        csv_path = cached[split]
        if csv_path.exists():
            continue
        gz_path = MOSES_DIR / f"{split}.csv.gz"
        _download_to_path(urls, gz_path)
        _gunzip_file(gz_path, csv_path)
        gz_path.unlink(missing_ok=True)

    return cached


def _load_chembl_subset(max_samples: Optional[int] = None) -> pd.DataFrame:
    """
    Load a cached ChEMBL subset or download one from GENOROVA_CHEMBL_SUBSET_URL.
    """
    local_candidates = [
        CHEMBL_DIR / "chembl_subset.csv",
        DATA_DIR / "chembl_subset.csv",
    ]

    env_url = os.environ.get("GENOROVA_CHEMBL_SUBSET_URL")
    if env_url:
        target = CHEMBL_DIR / "chembl_subset.csv"
        if not target.exists():
            _download_to_path((env_url,), target)
        local_candidates.insert(0, target)

    for path in local_candidates:
        if path.exists():
            df = pd.read_csv(path)
            smiles_column = _find_smiles_column(df)
            result = pd.DataFrame({"smiles": df[smiles_column].astype(str)})
            if max_samples is not None and len(result) > max_samples:
                result = result.sample(n=max_samples, random_state=42).reset_index(drop=True)
            return result

    raise FileNotFoundError(
        "ChEMBL subset not found. Place a CSV at genorova/data/chembl_subset/chembl_subset.csv "
        "or set GENOROVA_CHEMBL_SUBSET_URL."
    )


def load_smiles_dataset(
    name: str,
    max_samples: Optional[int] = None,
    min_len: int = 10,
    max_len: int = 100,
) -> pd.DataFrame:
    """
    Load a benchmark molecular dataset as a DataFrame with a `smiles` column.

    The returned DataFrame has dataset filtering metadata stored in
    `df.attrs["load_stats"]`.
    """
    dataset_name = name.lower().strip()

    if dataset_name == "moses":
        cached_files = download_moses()
        raw_df = pd.read_csv(cached_files["train"])
        smiles_column = _find_smiles_column(raw_df)
        source_df = pd.DataFrame({"smiles": raw_df[smiles_column].astype(str)})
    elif dataset_name in {"chembl", "chembl_subset"}:
        source_df = _load_chembl_subset(max_samples=max_samples)
    else:
        raise ValueError(f"Unsupported dataset '{name}'. Use 'moses' or 'chembl_subset'.")

    total_rows = len(source_df)
    source_df["smiles"] = source_df["smiles"].astype(str).str.strip()
    source_df = source_df[source_df["smiles"] != ""].drop_duplicates(subset=["smiles"]).reset_index(drop=True)
    deduped_rows = len(source_df)

    lengths = source_df["smiles"].str.len()
    length_filtered = source_df[lengths.between(min_len, max_len)].copy().reset_index(drop=True)
    removed_by_length = deduped_rows - len(length_filtered)

    if max_samples is not None and len(length_filtered) > max_samples:
        sample_pool = min(len(length_filtered), max(max_samples * 2, max_samples))
        length_filtered = length_filtered.sample(n=sample_pool, random_state=42).reset_index(drop=True)

    valid_smiles = []
    invalid_parse_count = 0

    for smiles in length_filtered["smiles"]:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            invalid_parse_count += 1
            continue
        valid_smiles.append(Chem.MolToSmiles(mol, canonical=True))

    filtered_df = pd.DataFrame({"smiles": valid_smiles}).drop_duplicates(subset=["smiles"]).reset_index(drop=True)

    post_validation_rows = len(filtered_df)
    if max_samples is not None and len(filtered_df) > max_samples:
        filtered_df = filtered_df.sample(n=max_samples, random_state=42).reset_index(drop=True)

    filtered_df.attrs["load_stats"] = {
        "dataset": dataset_name,
        "source_rows": total_rows,
        "deduplicated_rows": deduped_rows,
        "removed_by_length": removed_by_length,
        "invalid_parse_count": invalid_parse_count,
        "post_validation_rows": post_validation_rows,
        "returned_rows": len(filtered_df),
        "rdkit_warning_count": 0,
        "min_len": min_len,
        "max_len": max_len,
    }

    return filtered_df


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and validate molecular datasets for Genorova.")
    parser.add_argument("--dataset", default="moses", choices=["moses", "chembl_subset"])
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--min-len", type=int, default=10)
    parser.add_argument("--max-len", type=int, default=100)
    return parser


def main() -> None:
    args = _build_cli().parse_args()
    df = load_smiles_dataset(
        name=args.dataset,
        max_samples=args.max_samples,
        min_len=args.min_len,
        max_len=args.max_len,
    )
    stats = df.attrs.get("load_stats", {})

    print(f"Dataset: {args.dataset}")
    print(f"Molecules returned: {len(df)}")
    print(f"Filtered by length: {stats.get('removed_by_length', 0)}")
    print(f"Invalid RDKit parses removed: {stats.get('invalid_parse_count', 0)}")
    if not df.empty:
        lengths = df["smiles"].str.len()
        print(f"Length stats: min={lengths.min()} max={lengths.max()} mean={lengths.mean():.2f}")
        print("Sample molecules:")
        for smiles in df["smiles"].head(5):
            print(f"  {smiles}")


if __name__ == "__main__":
    main()
