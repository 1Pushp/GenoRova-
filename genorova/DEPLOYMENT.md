# Genorova AI v1.0 — Deployment Guide

**Status:** Production Ready · April 2026  
**Developer:** Pushp Dwivedi · pushpdwivedi911@gmail.com

---

## Best Molecule Discovered

```
SMILES:         COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2
IUPAC Name:     6,7-Dimethoxy-1-methyl-3,4-dihydroisoquinoline-2-sulfonamide
Clinical Score: 0.9649   (scale 0–1)
QED Score:      0.892    (top 5% of approved drugs)
SA Score:       2.83     (easy to synthesise)
MW:             286.35 Da
Lipinski:       PASS (0 violations)
Mutagenic:      None detected
ChEMBL:         CHEMBL1089045
CA7 Ki:         6.4 nM  (experimentally confirmed, 2011)
Docking (DHPS): -5.06 kcal/mol (AutoDock Vina — matches sulfamethoxazole)
```

---

## Installation

### Requirements
- Python 3.9+
- Windows 10/11 (tested on Windows 11 Home)
- 4 GB RAM minimum (model checkpoints are ~150 MB each)

### Step 1 — Install Python dependencies

```bash
pip install -r requirements_deploy.txt
```

### Step 2 — Install RDKit (required for chemistry)

```bash
conda install -c conda-forge rdkit
# or via pip (Windows):
pip install rdkit
```

### Step 3 — Download training data (if re-training)

```bash
python src/download_data.py
# Downloads ~1700 molecules per disease from ChEMBL REST API
```

### Step 4 — Run the pipeline (if starting fresh)

```bash
python -X utf8 src/run_pipeline.py
# ~18 minutes on CPU | ~4 minutes on GPU
# Trains both models, generates candidates, scores, visualises, reports
```

---

## Starting the API Server

### Windows (double-click or terminal)

```
start_genorova.bat
```

### Manual start

```bash
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

Server will be live at: **http://localhost:8000**

---

## API Reference

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

### GET /health
Service status and model availability.

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "running",
  "model": "Genorova AI v1.0",
  "models_loaded": {"diabetes": true, "infection": true},
  "molecules_in_db": 99,
  "best_molecule": "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2",
  "best_score": 0.9649
}
```

---

### POST /score
Score any SMILES string. Returns full ADMET + Genorova clinical score.

```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"smiles": "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"}'
```

Response:
```json
{
  "smiles": "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2",
  "molecular_weight": 286.35,
  "logp": 0.826,
  "qed_score": 0.8918,
  "sa_score": 2.8319,
  "passes_lipinski": true,
  "clinical_score": 0.9649,
  "recommendation": "Strong candidate"
}
```

---

### POST /generate
Generate drug candidates for a disease.

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"disease": "diabetes", "count": 10}'
```

Parameters:
- `disease`: `"diabetes"` or `"infection"`
- `count`: integer, 1–200

---

### GET /best_molecules
Top N molecules from the persistent molecule database.

```bash
curl "http://localhost:8000/best_molecules?n=10"
```

---

### GET /report
Returns the full HTML discovery report (self-contained, base64 images).

```bash
curl http://localhost:8000/report > genorova_report.html
```

Or open in browser: `http://localhost:8000/report`

---

## Command Line Interface

```bash
# Generate 100 diabetes drug candidates
python src/genorova_cli.py generate --disease diabetes --count 100

# Generate 100 infection drug candidates
python src/genorova_cli.py generate --disease infection --count 100

# Score molecules from a CSV file
python src/genorova_cli.py score --file outputs/generated/molecules.csv

# Generate HTML report
python src/genorova_cli.py report

# Train model (100 epochs)
python src/genorova_cli.py train --disease diabetes --epochs 100

# Visualise a molecule
python src/genorova_cli.py visualize --smiles "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"
```

---

## Output Files

```
outputs/
├── models/
│   ├── diabetes/genorova_diabetes_best.pt     (133 MB)
│   └── infection/genorova_infection_best.pt   (163 MB)
├── generated/
│   ├── diabetes_candidates_validated.csv
│   └── infection_candidates_validated.csv
├── molecule_images/                           (2D structure PNGs)
├── genorova_memory.db                         (SQLite molecule database)
├── genorova_report.html                       (174 KB self-contained report)
├── index.html                                 (landing page)
├── vocabulary_diabetes.json
└── vocabulary_infection.json
```

---

## Score Interpretation

| Score | Verdict | Meaning |
|-------|---------|---------|
| 0.85 – 1.00 | **Strong Candidate** | Excellent drug-likeness, good binding prediction |
| 0.60 – 0.84 | **Borderline** | Acceptable but has weaknesses |
| 0.00 – 0.59 | **Reject** | Does not meet drug-likeness criteria |

Score components: QED (25%) · Binding affinity (25%) · SA score (20%) · Lipinski (20%) · Novelty (10%)

---

## Scientific Validation

The best molecule was validated using real computational methods:

- **Novelty check:** PubChem CID 45378228, ChEMBL CHEMBL1089045 (known since 2010, never clinically trialled)
- **Experimental data:** CA7 Ki = 6.4 nM (Supuran group, J.Med.Chem. 2011)
- **Docking:** AutoDock Vina 1.2.5 vs S.aureus DHPS (3TYE): -5.06 kcal/mol
- **Reference:** Sulfamethoxazole vs same receptor: -5.17 kcal/mol
- **ADMET:** Zero Lipinski violations, zero mutagenicity alerts, QED 0.892

Validation report: `outputs/validation_report_COc1cc2.txt`

---

## Technology Stack

| Component | Library | Version |
|-----------|---------|---------|
| Machine Learning | PyTorch | 2.0+ |
| Chemistry | RDKit | 2026.03.1 |
| Data source | ChEMBL REST API | v34 |
| Web API | FastAPI + uvicorn | 0.135 / 0.44 |
| Docking | AutoDock Vina | 1.2.5 |
| Database | SQLite3 | built-in |

---

## Contact

**Pushp Dwivedi**  
Pharmacy Researcher | AI Drug Discovery  
pushpdwivedi911@gmail.com

---

*Genorova AI v1.0 · Built with PyTorch · RDKit · ChEMBL · FastAPI · April 2026*

---

## Render Deployment Note (April 2026)

- Keep Render service root at the repository root so `render.yaml` can run `pip install -r requirements.txt`.
- If Render root is set to `genorova/`, dependency install is still deterministic because `genorova/requirements.txt` delegates to `../requirements.txt`.
- Do not use `+cpu` torch pins in requirements files for standard PyPI installs on Render.
