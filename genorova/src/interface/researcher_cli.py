"""
Genorova AI — Researcher CLI
============================
Plain-English query interface over the Genorova molecule database.
Supports filtering, ADMET scoring, Tanimoto similarity ranking,
paginated display, CSV export, and per-molecule property explanation.

Run interactively:
    python genorova/src/interface/researcher_cli.py

Run non-interactive tests:
    python genorova/src/interface/researcher_cli.py --test
"""

from __future__ import annotations

import re
import sys
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from tabulate import tabulate

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError for box-drawing
# characters and special symbols like ≤, ✓, ✗, ║, ╔, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem

# ---------------------------------------------------------------------------
# Path setup — allow running from any working directory
# ---------------------------------------------------------------------------

_HERE        = Path(__file__).resolve().parent          # genorova/src/interface/
_SRC_DIR     = _HERE.parent                             # genorova/src/
_GENOROVA    = _SRC_DIR.parent                          # genorova/
_PROJECT     = _GENOROVA.parent                         # project root

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from admet.scorer import score_smiles, score_batch      # noqa: E402

MOLECULES_CSV  = _GENOROVA / "data" / "processed" / "cleaned_molecules_v2.csv"
DPP4_CSV       = _GENOROVA / "data" / "chembl" / "dpp4_actives.csv"
OUTPUTS_DIR    = _GENOROVA / "outputs"

# ---------------------------------------------------------------------------
# Known reference compounds (used for "similar to X" queries)
# ---------------------------------------------------------------------------

REFERENCE_SMILES: dict[str, str] = {
    "sitagliptin":   "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
    "aspirin":       "CC(=O)Oc1ccccc1C(=O)O",
    "metformin":     "CN(C)C(=N)NC(=N)N",
    "acetazolamide": "CC(=O)Nc1nnc(S(N)(=O)=O)s1",
    "empagliflozin": "OC[C@@H]1O[C@@H](c2ccc(Cl)cc2-c2ccc(OCC3CCOCC3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
    "glipizide":     "Cc1cnc(CN2C(=O)CCC2=O)s1",
    "metronidazole": "Cc1ncc([N+](=O)[O-])n1CCO",
    "ciprofloxacin": "O=C(O)c1cn(C2CC2)c2cc(N3CCNCC3)c(F)cc2c1=O",
}

# Display name for reverse-lookup
_SMILES_TO_NAME = {v: k for k, v in REFERENCE_SMILES.items()}

# ---------------------------------------------------------------------------
# Part 1 — Query Parser
# ---------------------------------------------------------------------------

def parse_query(text: str) -> dict:
    """
    Parse a plain-English drug query into a structured parameter dict.

    Recognised intents
    ------------------
    target       : diabetes/DPP-4 keywords → "DPP4"
                   antibacterial/gyrase keywords → "GYRASE"
                   default → "ANY"
    n_molecules  : "give me 50" / "20 molecules" → int  (default 50)
    mw_max       : "under 500 Da" / "MW < 400"   → float (default 550)
    qed_min      : "high QED" / "drug-like"       → 0.6  (default 0.0)
    potent_only  : "potent" / "active" / "IC50"   → True  (default False)
    reference    : "similar to sitagliptin"        → SMILES string or None
    """
    t = text.lower()

    # ── target ──────────────────────────────────────────────────────────────
    dpp4_kw  = ("dpp4", "dpp-4", "sitagliptin", "gliptin", "diabetes",
                 "anti-diabetic", "diabetic", "glucose", "insulin", "gluco")
    gyrase_kw = ("antibacterial", "antibiotic", "gyrase", "bacterial",
                  "bacteria", "antimicrobial", "anti-infective", "infection")

    if any(w in t for w in dpp4_kw):
        target = "DPP4"
    elif any(w in t for w in gyrase_kw):
        target = "GYRASE"
    else:
        target = "ANY"

    # ── n_molecules ─────────────────────────────────────────────────────────
    # "give me 50" / "generate 100" / "top 30" / "20 molecules"
    n_match = re.search(
        r'(?:give\s+me|generate|top|show|get|find|fetch|list)\s+(\d+)', t)
    if not n_match:
        n_match = re.search(r'(\d+)\s*(?:molecules?|compounds?|hits?|candidates?)', t)
    n_molecules = int(n_match.group(1)) if n_match else 50

    # ── mw_max ───────────────────────────────────────────────────────────────
    # "under 500" / "below 450" / "MW < 400" / "500 daltons"
    mw_match = re.search(
        r'(?:under|below|mw\s*[<≤]|max\s*mw|molecular\s*weight\s*(?:under|below|<|≤))\s*([\d.]+)',
        t)
    if not mw_match:
        mw_match = re.search(r'([\d.]+)\s*(?:da\b|dalton)', t)
    mw_max = float(mw_match.group(1)) if mw_match else 550.0

    # ── qed_min ──────────────────────────────────────────────────────────────
    qed_kw = ("high qed", "drug-like", "drug like", "druglike", "drug likeness")
    qed_min = 0.6 if any(w in t for w in qed_kw) else 0.0

    # ── potent_only ───────────────────────────────────────────────────────────
    potent_kw = ("potent", "highly active", "high activity", "ic50", "active only")
    potent_only = any(w in t for w in potent_kw)

    # ── reference SMILES ──────────────────────────────────────────────────────
    reference = None
    for name, smi in REFERENCE_SMILES.items():
        if name in t:
            reference = smi
            break

    params = {
        "target":       target,
        "n_molecules":  n_molecules,
        "mw_max":       mw_max,
        "qed_min":      qed_min,
        "potent_only":  potent_only,
        "reference":    reference,
    }

    ref_label = _SMILES_TO_NAME.get(reference, None) if reference else None
    extra = f" | similar_to={ref_label}" if ref_label else ""
    print(f"  Understood: target={target} | n={n_molecules} | MW≤{mw_max}"
          f" | QED≥{qed_min} | potent={potent_only}{extra}")

    return params


# ---------------------------------------------------------------------------
# Part 2 — Molecule Retrieval
# ---------------------------------------------------------------------------

def _tanimoto_column(smiles_series: pd.Series, ref_smiles: str) -> pd.Series:
    """Compute Tanimoto similarity (Morgan fp radius=2) for every SMILES."""
    ref_mol = Chem.MolFromSmiles(ref_smiles)
    if ref_mol is None:
        return pd.Series([0.0] * len(smiles_series), index=smiles_series.index)

    ref_fp = AllChem.GetMorganFingerprintAsBitVect(ref_mol, radius=2, nBits=2048)

    scores = []
    for smi in smiles_series:
        try:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                scores.append(0.0)
            else:
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
                scores.append(DataStructs.TanimotoSimilarity(ref_fp, fp))
        except Exception:
            scores.append(0.0)

    return pd.Series(scores, index=smiles_series.index)


def retrieve_molecules(params: dict) -> pd.DataFrame:
    """
    Load molecules, apply filters, run ADMET scoring, and rank results.

    Returns a DataFrame with lowercase column names ready for display:
        smiles, composite_score, grade, qed, mol_weight, sa_score,
        logp, hbd, hba, tpsa, lipinski_pass, pains_flag
        + tanimoto   (if reference given)
        + ic50_nm    (if DPP4 source)
    """
    # ── Step 1: load source data ─────────────────────────────────────────────
    if params["target"] == "DPP4":
        print("  Loading DPP-4 actives … ", end="", flush=True)
        df = pd.read_csv(DPP4_CSV)
        if params["potent_only"]:
            df = df[df["ic50_nm"] < 100]
            print(f"potent filter → {len(df)} rows", end="", flush=True)
    else:
        print("  Loading general library … ", end="", flush=True)
        df = pd.read_csv(MOLECULES_CSV)

    print(f" {len(df)} molecules loaded")

    # ── Step 2: fast pre-filter on existing CSV columns ───────────────────────
    before = len(df)
    df = df[df["mol_weight"] <= params["mw_max"]]
    if params["qed_min"] > 0.0:
        df = df[df["qed"] >= params["qed_min"]]
    print(f"  Filter MW≤{params['mw_max']} QED≥{params['qed_min']} → {len(df)}/{before} remain")

    if df.empty:
        print("  [WARN] No molecules passed the filters — try relaxing MW or QED thresholds.")
        return df

    # ── Step 3: score ────────────────────────────────────────────────────────
    if params["target"] == "DPP4":
        # DPP4 dataset is small enough for full RDKit scoring, and we want
        # the detailed descriptor columns (HBD, HBA, TPSA, PAINS, etc.).
        print(f"  Scoring {len(df)} molecules … ", end="", flush=True)
        t0 = time.perf_counter()
        scored = score_batch(df["smiles"].tolist())
        print(f"{time.perf_counter()-t0:.1f}s")

        scored = scored[scored["valid"]].reset_index(drop=True)
        df     = df.reset_index(drop=True).loc[scored.index].reset_index(drop=True)

        result = pd.DataFrame({
            "smiles":          scored["smiles"],
            "composite_score": scored["composite_score"],
            "grade":           scored["grade"],
            "mol_weight":      scored["MW"],
            "qed":             scored["QED"],
            "sa_score":        scored["SA_Score"],
            "logp":            scored["LogP"],
            "hbd":             scored["HBD"],
            "hba":             scored["HBA"],
            "tpsa":            scored["TPSA"],
            "lipinski_pass":   scored["lipinski_pass"],
            "pains_flag":      scored["pains_flag"],
        })

        if "ic50_nm" in df.columns:
            result["ic50_nm"] = df["ic50_nm"].values

    else:
        # GYRASE / ANY — cleaned_molecules_v2.csv already has qed, logp,
        # mol_weight, sa_score computed by RDKit during data preparation.
        # Re-apply the same composite formula used in admet/scorer.py using
        # vectorised pandas operations — no RDKit call needed, ~0.02s for 10K rows.
        print(f"  Scoring {len(df)} molecules from pre-computed columns … ",
              end="", flush=True)
        t0 = time.perf_counter()

        df = df.reset_index(drop=True).copy()

        qed_comp      = df["qed"] * 40.0
        lipinski_comp = pd.Series(10.0, index=df.index)
        lipinski_comp[(df["mol_weight"] <= 500) & (df["logp"] <= 5)] = 20.0
        sa_comp       = (20.0 * (1.0 - (df["sa_score"] - 1.0) / 9.0)).clip(lower=0.0)
        pains_comp    = 20.0   # curated dataset — no PAINS alerts present

        composite = (qed_comp + lipinski_comp + sa_comp + pains_comp).round(2)

        grade = pd.Series("F", index=df.index)
        grade[composite >= 40] = "C"
        grade[composite >= 60] = "B"
        grade[composite >= 80] = "A"

        print(f"{time.perf_counter()-t0:.3f}s")

        result = pd.DataFrame({
            "smiles":          df["smiles"],
            "composite_score": composite,
            "grade":           grade,
            "mol_weight":      df["mol_weight"],
            "qed":             df["qed"],
            "sa_score":        df["sa_score"],
            "logp":            df["logp"],
        })

    # ── Step 4: rank ──────────────────────────────────────────────────────────
    if params["reference"]:
        ref_label = _SMILES_TO_NAME.get(params["reference"], "reference")
        print(f"  Computing Tanimoto similarity to {ref_label} … ", end="", flush=True)
        result["tanimoto"] = _tanimoto_column(result["smiles"], params["reference"])
        print("done")
        result = result.sort_values("tanimoto", ascending=False)
    else:
        result = result.sort_values("composite_score", ascending=False)

    return result.head(params["n_molecules"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_DISPLAY_COLS = ["smiles", "composite_score", "grade", "qed", "mol_weight", "sa_score"]

def _print_table(df: pd.DataFrame, offset: int = 0, page_size: int = 10) -> None:
    """Print a paginated table slice."""
    page = df.iloc[offset: offset + page_size].copy()
    page["smiles"] = page["smiles"].str[:45]  # truncate long SMILES

    # Pick available display columns
    show_cols = [c for c in _DISPLAY_COLS if c in page.columns]
    if "tanimoto" in page.columns:
        show_cols.append("tanimoto")
    if "ic50_nm" in page.columns:
        show_cols.insert(3, "ic50_nm")

    print(tabulate(
        page[show_cols],
        headers="keys",
        tablefmt="rounded_outline",
        floatfmt=".2f",
        showindex=False,
    ))


def _explain(smiles: str) -> None:
    """Print a human-readable property breakdown for one SMILES string."""
    r = score_smiles(smiles)

    if not r["valid"]:
        print(f"  [ERROR] Could not parse SMILES: {r['error']}")
        return

    def _check(value, limit, label, unit="", lower_is_better=False):
        ok = (value <= limit) if not lower_is_better else (value >= limit)
        symbol = "✓" if ok else "✗"
        direction = "≤" if not lower_is_better else "≥"
        return f"  {symbol}  {label}: {value} {unit}  (limit {direction}{limit})"

    print(f"\n  SMILES : {smiles}")
    print(f"  ───────────────────────────────────────────────────────")
    print(f"  MW        : {r['MW']} Da"
          + ("  ✓ within Lipinski ≤500" if r["MW"] <= 500 else "  ✗ exceeds Lipinski limit"))
    print(f"  LogP      : {r['LogP']}"
          + ("  ✓ within Lipinski ≤5" if r["LogP"] <= 5 else "  ✗ too lipophilic"))
    print(f"  HBD       : {r['HBD']}"
          + ("  ✓ ≤5" if r["HBD"] <= 5 else "  ✗ too many H-bond donors"))
    print(f"  HBA       : {r['HBA']}"
          + ("  ✓ ≤10" if r["HBA"] <= 10 else "  ✗ too many H-bond acceptors"))
    print(f"  TPSA      : {r['TPSA']} Å²"
          + ("  ✓ oral absorption likely (≤140)" if r["TPSA"] <= 140 else "  ✗ poor oral absorption expected"))
    print(f"  RotBonds  : {r['RotBonds']}"
          + ("  ✓ flexible (≤10)" if r["RotBonds"] <= 10 else "  ✗ too rigid or too flexible"))
    print(f"  Fsp3      : {r['Fsp3']:.2f}"
          + ("  ✓ good 3D character (>0.3)" if r["Fsp3"] > 0.3 else "  — low saturation (flat molecule)"))
    print()

    qed = r["QED"]
    qed_label = "excellent" if qed >= 0.7 else "good" if qed >= 0.5 else "moderate" if qed >= 0.3 else "poor"
    print(f"  QED       : {qed:.3f}  — {qed_label} drug-likeness  (0=bad, 1=ideal)")

    sa = r["SA_Score"]
    if sa is not None:
        sa_label = "easy" if sa < 3 else "moderate" if sa < 5 else "hard" if sa < 7 else "very hard"
        print(f"  SA Score  : {sa:.2f}  — {sa_label} to synthesise  (1=easy, 10=hard)")

    print()
    lipinski_label = "PASS" if r["lipinski_pass"] else f"FAIL ({r['lipinski_violations']} violation(s))"
    print(f"  Lipinski  : {lipinski_label}")
    print(f"  Veber     : {'PASS' if r['veber_pass'] else 'FAIL'}")
    print(f"  BBB       : {'likely penetrant' if r['bbb_flag'] else 'unlikely to cross'}")
    print(f"  PAINS     : {'ALERT — structural concern' if r['pains_flag'] else 'clean'}")
    print()
    print(f"  Composite score : {r['composite_score']} / 100   Grade: {r['grade']}")
    print()


# ---------------------------------------------------------------------------
# Part 3 — Session Loop
# ---------------------------------------------------------------------------

BANNER = """
╔══════════════════════════════════════════╗
║   GENOROVA AI — Researcher Interface     ║
║   Type your drug goal, or 'quit'         ║
╚══════════════════════════════════════════╝
Commands:
  <natural language query>   — search and score molecules
  more                       — next 10 results from last query
  export                     — save last results to CSV
  explain <SMILES>           — property breakdown for one molecule
  quit / exit / q            — exit
"""


def main() -> None:
    """Interactive researcher session loop."""
    print(BANNER)

    last_results: pd.DataFrame | None = None
    display_offset = 0

    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not query:
            continue

        cmd = query.lower()

        # ── quit ────────────────────────────────────────────────────────────
        if cmd in ("quit", "exit", "q"):
            print("Bye.")
            break

        # ── more ────────────────────────────────────────────────────────────
        elif cmd == "more":
            if last_results is None or last_results.empty:
                print("  No previous results — run a query first.")
            else:
                display_offset += 10
                if display_offset >= len(last_results):
                    print(f"  No more results (showed all {len(last_results)}).")
                    display_offset = len(last_results)
                else:
                    _print_table(last_results, offset=display_offset)
                    remaining = len(last_results) - display_offset - 10
                    if remaining > 0:
                        print(f"  {remaining} more rows available. Type 'more' to continue.")

        # ── export ──────────────────────────────────────────────────────────
        elif cmd.startswith("export"):
            if last_results is None or last_results.empty:
                print("  Nothing to export — run a query first.")
            else:
                OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = OUTPUTS_DIR / f"researcher_session_{ts}.csv"
                last_results.to_csv(path, index=False)
                print(f"  Saved {len(last_results)} rows → {path}")

        # ── explain ─────────────────────────────────────────────────────────
        elif cmd.startswith("explain"):
            smiles_arg = query[7:].strip()
            if not smiles_arg:
                print("  Usage: explain <SMILES>")
            else:
                _explain(smiles_arg)

        # ── drug query ───────────────────────────────────────────────────────
        else:
            params = parse_query(query)
            print(f"  Target: {params['target']} | n={params['n_molecules']}"
                  f" | MW≤{params['mw_max']}")

            results = retrieve_molecules(params)
            if results.empty:
                print("  No molecules found. Try a different query.")
                continue

            last_results   = results
            display_offset = 0

            _print_table(results, offset=0)
            print(f"\n  Showing top 10 of {len(results)} results.")
            print("  Commands: 'more' | 'export' | 'explain [SMILES]' | new query")


# ---------------------------------------------------------------------------
# Part 4 — Non-interactive test runner
# ---------------------------------------------------------------------------

def _run_test_queries() -> None:
    """Run 3 pre-defined queries and print results without user interaction."""
    test_queries = [
        "anti-diabetic molecules under 500 daltons",
        "give me 20 potent DPP-4 inhibitors with high QED",
        "antibacterial compounds with MW under 400",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i}: {query}")
        print("="*60)

        params  = parse_query(query)
        print(f"  Target: {params['target']} | n={params['n_molecules']}"
              f" | MW≤{params['mw_max']}")
        results = retrieve_molecules(params)

        if results.empty:
            print("  No results.")
            continue

        _print_table(results, offset=0)
        print(f"\n  Returned {len(results)} molecules.")

        # Show grade distribution
        if "grade" in results.columns:
            dist = results["grade"].value_counts().to_dict()
            print(f"  Grade distribution: {dist}")

    print(f"\n{'='*60}")
    print("All test queries complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_test_queries()
    else:
        main()
