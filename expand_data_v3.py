from __future__ import annotations

from pathlib import Path

import pandas as pd
from rdkit import Chem


TARGET_ROWS = 500_000
CHUNK_SIZE = 50_000
PROGRESS_EVERY = 50_000


def main() -> int:
    root = Path(__file__).resolve().parent
    input_path = root / "genorova" / "data" / "moses" / "train.csv"
    output_path = root / "genorova" / "data" / "processed" / "cleaned_molecules_v3.csv"

    if not input_path.exists():
        raise FileNotFoundError(f"MOSES train file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_set: set[str] = set()
    collected: list[str] = []
    valid_count = 0
    duplicates_removed = 0
    next_progress = PROGRESS_EVERY

    for chunk_index, chunk in enumerate(
        pd.read_csv(input_path, usecols=["SMILES"], chunksize=CHUNK_SIZE),
        start=1,
    ):
        for smi in chunk["SMILES"].dropna():
            mol = Chem.MolFromSmiles(str(smi))
            if mol is None:
                continue

            valid_count += 1
            canonical = Chem.MolToSmiles(mol)
            if canonical in seen_set:
                duplicates_removed += 1
                continue

            seen_set.add(canonical)
            collected.append(canonical)

            while len(collected) >= next_progress:
                print(f"[expand] {next_progress} / {TARGET_ROWS} collected (chunk {chunk_index})")
                next_progress += PROGRESS_EVERY

            if len(collected) == TARGET_ROWS:
                break

        if len(collected) == TARGET_ROWS:
            break

    df = pd.DataFrame({"smiles": collected})
    df.to_csv(output_path, index=False)

    print(
        f"[expand] DONE — valid: {valid_count} | duplicates removed: {duplicates_removed} | "
        f"final rows: {len(collected)}"
    )
    print(f"[expand] Written to: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
