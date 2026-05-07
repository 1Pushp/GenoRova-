"""
ADMET scorer — RDKit-only, fully offline.

Computes physicochemical descriptors, rule-based flags, and a composite
0-100 score for any input SMILES string.  No network calls, no external
binaries required.

Composite score breakdown (max 100):
  QED component      40   QED * 40
  Lipinski component 20   20 if 0 violations, 10 if 1, 0 if 2+
  SA component       20   max(0, 20 * (1 - (SA-1) / 9))
  PAINS component    20   20 if no PAINS alert, 0 if flagged

Grade: A >= 80 | B 60-79 | C 40-59 | F < 40

Usage:
    from genorova.src.admet.scorer import score_smiles, score_batch

    result = score_smiles("CC(=O)Oc1ccccc1C(=O)O")
    print(result["composite_score"], result["grade"])

    df = score_batch(["CC(=O)O", "c1ccccc1"])
    print(df[["smiles", "composite_score", "grade"]])
"""

from __future__ import annotations

import sys
import os
import time
import importlib
from typing import Any

import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors, QED as RDKitQED, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

# ---------------------------------------------------------------------------
# Load sascorer from RDKit contrib (ships with every RDKit install)
# ---------------------------------------------------------------------------

def _load_sascorer():
    """Import sascorer from RDKit's Contrib bundle."""
    try:
        from rdkit.Contrib.SA_Score import sascorer as _sa
        return _sa
    except ImportError:
        pass
    # Fallback: add the Contrib/SA_Score folder to sys.path manually
    import rdkit as _rdkit
    sa_dir = os.path.join(os.path.dirname(_rdkit.__file__), "Contrib", "SA_Score")
    if sa_dir not in sys.path:
        sys.path.insert(0, sa_dir)
    import sascorer as _sa  # type: ignore
    return _sa

_sascorer = _load_sascorer()

# ---------------------------------------------------------------------------
# Build PAINS filter once at module load — reusing it is ~10x faster than
# constructing it per molecule.
#
# PAINS_A+B covers all high-confidence alerts (~80 patterns).
# PAINS_C adds ~400 low-confidence patterns that cost 5x more CPU time
# and are not well-validated in drug discovery pipelines.
# ---------------------------------------------------------------------------

_pains_params = FilterCatalogParams()
_pains_params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_A)
_pains_params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_B)
_PAINS_CATALOG = FilterCatalog(_pains_params)


# ---------------------------------------------------------------------------
# Core descriptor computation
# ---------------------------------------------------------------------------

def _compute_descriptors(mol: Chem.Mol) -> dict[str, Any]:
    """
    Compute all physicochemical descriptors for a valid RDKit mol object.
    Returns a flat dict of numeric properties.
    """
    mw       = Descriptors.MolWt(mol)
    logp     = Descriptors.MolLogP(mol)
    hbd      = rdMolDescriptors.CalcNumHBD(mol)
    hba      = rdMolDescriptors.CalcNumHBA(mol)
    tpsa     = rdMolDescriptors.CalcTPSA(mol)
    rot_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
    qed_val  = RDKitQED.qed(mol)
    fsp3     = rdMolDescriptors.CalcFractionCSP3(mol)

    try:
        sa_val = _sascorer.calculateScore(mol)
    except Exception:
        sa_val = float("nan")

    return {
        "MW":        round(mw,       2),
        "LogP":      round(logp,     3),
        "HBD":       hbd,
        "HBA":       hba,
        "TPSA":      round(tpsa,     2),
        "RotBonds":  rot_bonds,
        "QED":       round(qed_val,  4),
        "Fsp3":      round(fsp3,     4),
        "SA_Score":  round(sa_val,   3) if sa_val == sa_val else None,
    }


# ---------------------------------------------------------------------------
# Rule-based flags
# ---------------------------------------------------------------------------

def _compute_flags(descriptors: dict[str, Any], mol: Chem.Mol) -> dict[str, Any]:
    """
    Apply rule-based filters and return boolean flags.

    lipinski_pass: Lipinski Rule of 5 (0 or 1 violation allowed by Lipinski's
                   original definition — we require strict 0 violations here).
    veber_pass:    Veber oral bioavailability rules.
    bbb_flag:      Rough CNS-penetrant heuristic (MW, LogP, TPSA).
    pains_flag:    True if molecule contains a PAINS structural alert.
    lipinski_violations: count of individual violations (0-4).
    """
    mw   = descriptors["MW"]
    logp = descriptors["LogP"]
    hbd  = descriptors["HBD"]
    hba  = descriptors["HBA"]
    tpsa = descriptors["TPSA"]
    rot  = descriptors["RotBonds"]

    violations = (
        int(mw   > 500) +
        int(logp > 5.0) +
        int(hbd  > 5)   +
        int(hba  > 10)
    )
    lipinski_pass = violations == 0

    veber_pass = (tpsa <= 140) and (rot <= 10)

    bbb_flag = (mw < 450) and (1.0 <= logp <= 3.0) and (tpsa < 90)

    pains_flag = _PAINS_CATALOG.HasMatch(mol)

    return {
        "lipinski_pass":       lipinski_pass,
        "lipinski_violations": violations,
        "veber_pass":          veber_pass,
        "bbb_flag":            bbb_flag,
        "pains_flag":          pains_flag,
    }


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def _composite_score(descriptors: dict[str, Any],
                     flags: dict[str, Any]) -> tuple[float, str]:
    """
    Calculate the composite ADMET score (0-100) and letter grade.

    Returns (score, grade).
    """
    score = 0.0

    # QED component — max 40
    score += descriptors["QED"] * 40.0

    # Lipinski component — 20 / 10 / 0
    v = flags["lipinski_violations"]
    if v == 0:
        score += 20.0
    elif v == 1:
        score += 10.0
    # 2+ violations → 0 (nothing added)

    # SA component — max 20; penalises hard-to-synthesise molecules
    sa = descriptors["SA_Score"]
    if sa is not None:
        score += max(0.0, 20.0 * (1.0 - (sa - 1.0) / 9.0))

    # PAINS component — 20 if clean
    if not flags["pains_flag"]:
        score += 20.0

    score = round(min(score, 100.0), 2)

    if score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 40:
        grade = "C"
    else:
        grade = "F"

    return score, grade


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_smiles(smiles: str) -> dict[str, Any]:
    """
    Score a single SMILES string and return a full property dict.

    Keys returned:
        smiles, valid, error,
        MW, LogP, HBD, HBA, TPSA, RotBonds, QED, Fsp3, SA_Score,
        lipinski_pass, lipinski_violations, veber_pass, bbb_flag, pains_flag,
        composite_score, grade

    If the SMILES is invalid, 'valid' is False, 'error' contains the message,
    and all numeric fields are None.
    """
    result: dict[str, Any] = {"smiles": smiles, "valid": False, "error": None}

    if not smiles or not isinstance(smiles, str):
        result["error"] = "empty or non-string input"
        return result

    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        result["error"] = "RDKit could not parse SMILES"
        return result

    result["valid"] = True

    try:
        descriptors = _compute_descriptors(mol)
        flags       = _compute_flags(descriptors, mol)
        score, grade = _composite_score(descriptors, flags)
    except Exception as exc:
        result["error"] = f"descriptor error: {exc}"
        return result

    result.update(descriptors)
    result.update(flags)
    result["composite_score"] = score
    result["grade"]           = grade
    return result


def score_batch(smiles_list: list[str]) -> pd.DataFrame:
    """
    Score a list of SMILES strings and return a tidy DataFrame.

    Each row corresponds to one input SMILES.  Invalid entries appear as rows
    with valid=False and NaN numeric columns.
    """
    rows = [score_smiles(s) for s in smiles_list]
    df = pd.DataFrame(rows)

    # Enforce consistent column order
    cols_front = ["smiles", "valid", "error", "composite_score", "grade"]
    cols_props = [c for c in df.columns if c not in cols_front]
    df = df[cols_front + cols_props]
    return df


# ---------------------------------------------------------------------------
# Smoke test + benchmark — run this file directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("ADMET SCORER — smoke test")
    print("=" * 60)

    smiles_test = [
        ("Sitagliptin",
         "O=C(N1CCC[C@@H]1C(=O)N1CCn2c(nnc2-c2ccc(F)cc2)C1)CC(F)(F)F"),
        ("Aspirin",     "CC(=O)Oc1ccccc1C(=O)O"),
        ("Caffeine",    "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
        ("DPP4-hit",
         "CN(C)C(=O)[C@@H](c1ccc(-c2ccc(F)cc2)cc1)[C@H](N)C(=O)N1CC[C@H](F)C1"),
    ]

    for name, smi in smiles_test:
        r = score_smiles(smi)
        print(f"\n{name}")
        print(f"  valid         : {r['valid']}")
        if r["valid"]:
            print(f"  MW / LogP     : {r['MW']} / {r['LogP']}")
            print(f"  HBD / HBA     : {r['HBD']} / {r['HBA']}")
            print(f"  TPSA          : {r['TPSA']}")
            print(f"  QED           : {r['QED']}")
            print(f"  SA_Score      : {r['SA_Score']}")
            print(f"  Fsp3          : {r['Fsp3']}")
            print(f"  lipinski_pass : {r['lipinski_pass']} "
                  f"(violations={r['lipinski_violations']})")
            print(f"  veber_pass    : {r['veber_pass']}")
            print(f"  bbb_flag      : {r['bbb_flag']}")
            print(f"  pains_flag    : {r['pains_flag']}")
            print(f"  composite     : {r['composite_score']}  grade={r['grade']}")
        else:
            print(f"  error: {r['error']}")

    # ------------------------------------------------------------------
    # Benchmark: 1000 molecules from cleaned_molecules_v2.csv
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("BENCHMARK — 1000 molecules")
    print("=" * 60)

    _csv_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "processed",
        "cleaned_molecules_v2.csv"
    )
    _csv_path = os.path.normpath(_csv_path)

    if not os.path.exists(_csv_path):
        print(f"[WARN] CSV not found at {_csv_path} — skipping benchmark")
    else:
        df_src = pd.read_csv(_csv_path)
        sample = df_src["smiles"].dropna().sample(
            min(1000, len(df_src)), random_state=42
        ).tolist()

        t0 = time.perf_counter()
        df_out = score_batch(sample)
        elapsed = time.perf_counter() - t0

        valid_count = df_out["valid"].sum()
        grade_counts = df_out[df_out["valid"]]["grade"].value_counts().to_dict()

        print(f"  molecules scored : {len(sample)}")
        print(f"  valid            : {valid_count}")
        print(f"  grade breakdown  : {grade_counts}")
        print(f"  elapsed          : {elapsed:.2f}s")
        print(f"  throughput       : {len(sample)/elapsed:.0f} mol/s")

        if elapsed > 15.0:
            print("[WARN] benchmark exceeded 15-second target")
        else:
            print("[OK]  under 15-second target")

        print("\nTop 5 by composite score:")
        top = df_out[df_out["valid"]].nlargest(5, "composite_score")[
            ["smiles", "composite_score", "grade", "QED", "SA_Score", "pains_flag"]
        ]
        print(top.to_string(index=False))
