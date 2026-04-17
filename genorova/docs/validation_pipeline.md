# Genorova AI — Second-Stage Validation Pipeline (v2.0)

## Overview

The validation pipeline takes a generated SMILES string and answers five core drug-discovery questions:

| Question | Answered by |
|---|---|
| Can it be synthesized? | SA score (Stage A) |
| Is it likely novel? | Novelty lookup (Stage A) |
| Does it bind well relative to a standard? | Docking / proxy (Stage B) |
| Is it likely safe enough to investigate? | ADMET (Stage C) |
| Is it clinically worth pursuing? | Decision engine (Stage D) |

---

## Architecture

```
SMILES
  │
  ▼
Stage A: Chemical Sanity      (src/validation/chemistry/sanitizer.py)
  │    SA score, PAINS filter, novelty lookup
  │
  ▼
Stage B: Target Engagement    (src/validation/binding/target_binder.py)
  │    AutoDock Vina (if available) or scaffold-similarity proxy
  │
  ▼
Stage C: ADMET Safety         (src/validation/admet/admet_predictor.py)
  │    DILI risk, hERG risk, CYP450 interaction risk
  │
  ▼
Stage D: Clinical Utility     (src/validation/clinical/clinical_evaluator.py)
  │    Weighted decision: advance / conditional_advance / reject
  │
  ▼
ValidationResult              (src/validation/models.py)
  JSON with all four stage results + five core question answers + summary
```

---

## Module Reference

### Stage A — Chemical Sanity (`chemistry/sanitizer.py`)

**Input:** SMILES string, `pubchem_lookup` flag

**Functions:**
- `calculate_sa_score(smiles)` → `(float, str)` — SA score + data source label
- `check_pains(smiles)` → `(bool, list, str)` — PAINS hit, matched alerts, source
- `check_novelty(smiles, pubchem_lookup)` → dict — novelty flag + details
- `run_chemistry_sanity(smiles, pubchem_lookup)` → dict — full stage result

**SA score interpretation:**
| Score | Flag | Meaning |
|---|---|---|
| 1–4 | synthesizable | Most medicinal chemistry labs can make this |
| 4–6 | difficult | Feasible but requires specialist chemistry |
| > 6 | impractical | Synthesis is not practical for most labs |

**Novelty flags:**
| Flag | Meaning |
|---|---|
| `potentially_novel_patentable` | Not found locally or in PubChem |
| `known_repurposing_lead` | Matches a known drug (Tanimoto ≥ 0.85 or exact match) |
| `unrealistic` | Too simple to be a viable drug lead |
| `local_only_checked` | PubChem was not queried — uncertainty acknowledged |

**PAINS filtering** uses RDKit's built-in `FilterCatalog` with the PAINS catalog from Baell & Holloway (2010). A PAINS hit does not automatically disqualify a molecule but flags it for assay interference risk.

---

### Stage B — Target Engagement (`binding/target_binder.py`)

**Input:** SMILES, target name, optional reference drug name

**Supported targets:**

| Key | PDB | Description | Reference drug |
|---|---|---|---|
| `insulin_receptor` | 1IR3 | Insulin receptor kinase | staurosporine |
| `dpp4` | 1NNY | DPP-4 (sitagliptin target) | sitagliptin |
| `glut4` | 6THA | GLUT4 glucose transporter | cytochalasin_b |
| `ace2` | 6M0J | ACE2 (COVID-19 target) | MLN-4760 |
| `hiv_protease` | 3OXC | HIV-1 protease | lopinavir |

**Modes:**

| Mode | Condition | Score units | Confidence |
|---|---|---|---|
| `real_docking` | AutoDock Vina installed + PDBQT files present | kcal/mol | high |
| `scaffold_proxy` | RDKit available, Vina absent | Unitless proxy | medium/low |
| `unavailable` | Neither RDKit nor Vina | — | none |

**Delta interpretation (real_docking only):**
- `delta_vs_reference ≤ −1.0` kcal/mol → candidate binds better than reference
- `delta_vs_reference ≈ 0.0` → comparable to reference
- `delta_vs_reference > +1.0` → weaker than reference

**Proxy score formula (scaffold_proxy mode):**
```
proxy = weak_baseline + tanimoto × (ref_energy − weak_baseline) + property_bonus
```
Where `weak_baseline = −4.0`, `ref_energy` = published literature value for the target's reference drug. The property bonus adds up to ±1.0 based on MW, LogP, HBA, HBD.

---

### Stage C — ADMET Safety (`admet/admet_predictor.py`)

**Input:** SMILES string

**Outputs:**

```json
{
  "hepatotoxicity_risk": {"level": "low|medium|high|unknown", "score": 0.0, "alerts": [], "method": "..."},
  "herg_risk":           {"level": "...", "score": 0.0, "alerts": [], "method": "..."},
  "cyp_risk":            {"level": "...", "score": 0.0, "alerts": [], "method": "..."},
  "overall_safety_flag": "likely_safe|caution|likely_unsafe|unknown",
  "safety_score":        0.85
}
```

**Risk level thresholds:**
- score < 0.25 → low
- score 0.25–0.55 → medium
- score > 0.55 → high

**Structural alerts used:**

*DILI / hepatotoxicity:*
- Aromatic nitro groups, hydrazines, acyl halides, anhydrides
- LogP > 5.0 (hepatic accumulation)
- MW > 600 Da (biliary load)
- ≥ 4 aromatic rings (reactive metabolite formation)

*hERG inhibition:*
- Core pharmacophore: basic nitrogen + aromatic ring(s) + LogP > 2.0
- MW in 300–700 Da range
- ≥ 3 aromatic rings (flat molecule fits hERG channel)

*CYP450 interaction:*
- Pyridine, imidazole, triazole (heme coordination)
- Large lipophilic flexible molecules (CYP3A4 substrates)
- Acidic groups + aromatic ring (CYP2C9 substrates)

**Overall safety flag logic:**
- Any HIGH risk → `likely_unsafe`
- Any MEDIUM risk → `caution`
- All LOW → `likely_safe`

---

### Stage D — Clinical Utility (`clinical/clinical_evaluator.py`)

**Input:** Upstream stage results + optional QED / Lipinski data

**Decision scoring:**

| Component | Weight | Basis |
|---|---|---|
| Binding | 35% | Real docking delta or proxy score |
| Safety | 30% | ADMET safety_score |
| Novelty | 15% | Novelty flag |
| Synthesizability | 10% | SA score → 0/0.5/1.0 |
| Drug-likeness | 10% | QED + Lipinski |

**Decision thresholds:**
- score ≥ 0.65 → **advance**
- score 0.45–0.65 → **conditional_advance**
- score < 0.45 → **reject**

**Hard-reject overrides (score is ignored):**
1. `valid_smiles == False`
2. `overall_safety_flag == "likely_unsafe"`
3. `sa_flag == "impractical"` (unless real docking score ≤ −9.0 kcal/mol)

---

## API Endpoints

All endpoints accept `POST` with a JSON body and return structured JSON.

| Endpoint | Input | Output |
|---|---|---|
| `POST /api/validate` | ValidateRequest | Full ValidationResult |
| `POST /api/validate/chemistry` | `{smiles, pubchem_lookup}` | ChemistryResult |
| `POST /api/validate/binding` | `{smiles, target, reference_drug}` | BindingResult |
| `POST /api/validate/admet` | `{smiles}` | ADMETResult |
| `POST /api/validate/clinical` | `{smiles, target, disease, ...}` | ClinicalResult |

**Example (cURL):**
```bash
curl -s -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1", "target": "insulin_receptor", "disease": "diabetes"}' \
  | python -m json.tool
```

---

## Python API

```python
from validation.pipeline import validate_molecule

result = validate_molecule(
    smiles="Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
    target="insulin_receptor",
    disease="diabetes",
    pubchem_lookup=False,   # set True for real novelty check (needs internet)
)

print(result["final_decision"])          # advance | conditional_advance | reject
print(result["summary"])                 # plain-language paragraph
print(result["can_be_synthesized"])      # True / False / None
print(result["likely_novel"])            # True / False / None
print(result["binding"]["mode"])         # real_docking | scaffold_proxy | unavailable
print(result["admet"]["overall_safety_flag"])  # likely_safe | caution | likely_unsafe
```

**Batch mode:**
```python
from validation.pipeline import validate_batch

results = validate_batch(
    smiles_list=["SMILES1", "SMILES2", "SMILES3"],
    target="insulin_receptor",
    disease="diabetes",
)
# results is sorted by decision_score descending
for r in results:
    print(r["smiles"][:30], r["final_decision"], r["clinical"]["decision_score"])
```

---

## Running the Tests

```bash
cd "c:/Users/pushp/OneDrive/Desktop/organic chemistry/genorova/src"

# All validation tests
python -m pytest ../tests/test_validation_chemistry.py -v
python -m pytest ../tests/test_validation_binding.py -v
python -m pytest ../tests/test_validation_admet.py -v
python -m pytest ../tests/test_validation_clinical.py -v
python -m pytest ../tests/test_validation_pipeline.py -v

# All tests at once
python -m pytest ../tests/ -v
```

---

## Enabling Real Docking

1. Install AutoDock Vina:  download `vina.exe` and place it in `genorova/` or on `PATH`
2. Prepare protein PDBQT files and place them in `genorova/docking/`:
   - `1ir3_prepared.pdbqt` (insulin receptor)
   - `1nny_prepared.pdbqt` (DPP4)
   - etc.
3. On the next call to `run_binding_evaluation()`, the pipeline auto-detects
   `vina.exe` and switches from `scaffold_proxy` to `real_docking` mode.

---

## Enabling PubChem Novelty Lookup

Pass `pubchem_lookup=True` to `validate_molecule()` or set `pubchem_lookup: true`
in the API request body.  Requires internet access.  Adds ~1–3 seconds per call.

```python
result = validate_molecule(smiles, pubchem_lookup=True)
print(result["chemistry"]["novelty"]["pubchem_cid"])   # None if not found in PubChem
```
