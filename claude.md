# Genorova AI — Project Specification for Claude Code

## Project overview
Genorova AI is a generative drug discovery platform that uses machine learning to design novel drug molecules for diabetes and infectious diseases. The goal is a working prototype by April 2026.

## What we are building
A Python-based generative model that:
1. Takes molecular data (SMILES strings) as input
2. Learns patterns from existing drug compounds
3. Generates completely new drug molecule candidates
4. Validates generated molecules computationally

## Tech stack
- Language: Python 3.11+
- ML framework: PyTorch
- Chemistry: RDKit
- Data: Pandas, NumPy
- Visualization: Matplotlib, Seaborn
- Model architecture: Variational Autoencoder (VAE)
- Dataset: ChEMBL (public), client dataset (to be provided)

## Project structure to build
genorova/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── data/
│   ├── raw/          # raw molecular datasets
│   ├── processed/    # cleaned SMILES data
│   └── generated/    # AI-generated molecules
├── src/
│   ├── data_loader.py      # load and parse molecular data
│   ├── preprocessor.py     # clean and encode SMILES
│   ├── model.py            # VAE model architecture
│   ├── train.py            # training loop
│   ├── generate.py         # generate new molecules
│   └── validate.py         # validate generated molecules
├── notebooks/
│   └── exploration.ipynb   # data exploration
└── outputs/
└── models/             # saved trained models

## Step by step build order
1. Set up project structure and requirements.txt
2. Build data_loader.py — load SMILES from ChEMBL or CSV
3. Build preprocessor.py — tokenize and encode SMILES strings
4. Build model.py — VAE encoder and decoder architecture
5. Build train.py — training loop with loss functions
6. Build generate.py — sample from latent space to generate molecules
7. Build validate.py — check validity of generated SMILES using RDKit

## Model architecture details
- Input: SMILES string encoded as one-hot vectors
- Encoder: 3-layer neural network → latent space (256 dimensions)
- Latent space: mean and log variance vectors
- Decoder: 3-layer neural network → reconstructed SMILES
- Loss: Reconstruction loss + KL divergence
- Optimizer: Adam, learning rate 0.001

## Target diseases
- Diabetes (primary)
- Infectious diseases (secondary)

## Developer context
- Developer: Pushp Dwivedi, pharmacy researcher, 
- All code must be clearly commented in plain English
- Every function must have a docstring explaining what it does
- Avoid overly complex abstractions — keep it simple and readable
- When something might fail, add try/except with helpful error messages

## Important constraints
- Must run on Windows (HP laptop)
- Should work in VS Code terminal
- Keep memory usage reasonable — no massive batch sizes
- Use Google Colab as fallback if local GPU is insufficient

## How Claude Code should help
- Write all code from scratch
- Explain each file clearly before writing it
- Add detailed comments inside every function
- Debug errors step by step when they occur
- Suggest improvements as we progress
---

## New Feature Module: Multimodal Vision + Molecular Imaging

### Feature overview
Add a vision-capable module to Genorova AI that can:
1. Read and understand molecular structure images (2D/3D)
2. Extract chemical information from images and convert to SMILES
3. Visualize generated molecules as chemical structure diagrams
4. Analyze protein structures and identify target binding sites
5. Predict protein-ligand binding interactions visually

### New files to build for this feature

genorova/
└── src/
├── vision/
│   ├── image_reader.py        # read and preprocess molecular images
│   ├── smiles_extractor.py    # extract SMILES from structure images
│   ├── structure_visualizer.py # draw chemical structures from SMILES
│   ├── protein_analyzer.py    # analyze protein PDB structures
│   └── binding_site_detector.py # detect and visualize binding sites
└── data/
├── protein_structures/    # PDB files for target proteins
└── molecule_images/       # input molecular images

### Libraries to install for this feature
rdkit          # core chemistry — already in requirements
Pillow         # image reading and processing
cairosvg       # convert SVG molecule drawings to PNG
py3Dmol        # 3D molecular visualization
biopython      # protein structure parsing (PDB files)
biotite        # protein structure analysis
open-babel     # molecular format conversion
torchvision    # image feature extraction with PyTorch

### Step by step build order for this feature
1. image_reader.py — load PNG/JPG/SVG of molecules, preprocess for analysis
2. smiles_extractor.py — use RDKit to interpret structure images and output SMILES string
3. structure_visualizer.py — take any SMILES and draw it as a clean 2D chemical structure image
4. protein_analyzer.py — load PDB protein files using BioPython, extract amino acid sequences and 3D coordinates
5. binding_site_detector.py — identify hydrophobic pockets and active sites where drug molecules can bind

### How each component works

#### Image reader
- Accepts: PNG, JPG, SVG, PDF of molecular diagrams
- Output: preprocessed numpy array ready for analysis
- Uses: Pillow for image loading, OpenCV for preprocessing

#### SMILES extractor
- Accepts: molecular structure image
- Output: valid SMILES string (e.g. CC(=O)Oc1ccccc1C(=O)O for aspirin)
- Uses: RDKit MolFromImage function + image preprocessing pipeline

#### Structure visualizer
- Accepts: SMILES string from generative model output
- Output: clean 2D chemical structure diagram saved as PNG
- Uses: RDKit Draw module, MolToImage function
- Every generated molecule should be visualized automatically after generation

#### Protein analyzer
- Accepts: PDB file of target protein (e.g. insulin receptor, ACE2)
- Output: protein sequence, 3D coordinates, residue list
- Uses: BioPython PDBParser
- Target proteins for diabetes: insulin receptor (PDB: 1IR3), GLUT4
- Target proteins for infections: ACE2 (PDB: 6M0J), viral proteases

#### Binding site detector
- Accepts: protein PDB file + generated molecule SMILES
- Output: binding affinity score, key interacting residues, 3D visualization
- Uses: py3Dmol for visualization, biotite for structure analysis
- Method: identify hydrophobic pockets, hydrogen bond donors/acceptors

### Integration with main Genorova pipeline
After the VAE generates a new SMILES string:
1. Pass SMILES to structure_visualizer.py → save chemical structure image
2. Pass SMILES + target protein PDB to binding_site_detector.py → get binding score
3. If binding score is good → molecule is a strong candidate
4. Save candidate molecule with its structure image and binding report

### Developer notes
- Keep all vision functions simple and well commented
- Every function must show clear print statements so Pushp can follow what is happening
- Add example usage at the bottom of each file
- Start with structure_visualizer.py first — it is the simplest and most visual
- Use diabetes target protein insulin receptor (PDB ID: 1IR3) as the first test case
- All images should be saved to outputs/molecule_images/ folder automatically

---

## Model Training Parameters (Architect Recommendations)

### VAE Hyperparameters
```python
# Core architecture
LATENT_DIM = 256          # size of latent space vector
ENCODER_LAYERS = [512, 256]   # hidden layer sizes for encoder
DECODER_LAYERS = [256, 512]   # hidden layer sizes for decoder
MAX_SMILES_LENGTH = 120   # max length of SMILES string input

# Training settings
BATCH_SIZE = 256          # number of molecules per training batch
EPOCHS = 100              # total training cycles
LEARNING_RATE = 0.001     # Adam optimizer learning rate
LR_DECAY = 0.95           # reduce LR by 5% every 10 epochs
DROPOUT_RATE = 0.2        # prevent overfitting
CLIP_GRADIENT = 1.0       # prevent exploding gradients

# Loss function weights
KL_WEIGHT = 0.5           # weight of KL divergence loss
RECON_WEIGHT = 1.0        # weight of reconstruction loss
KL_ANNEALING = True       # gradually increase KL weight during training

# Validation
TRAIN_SPLIT = 0.80        # 80% data for training
VAL_SPLIT = 0.10          # 10% for validation
TEST_SPLIT = 0.10         # 10% for final testing
EARLY_STOPPING_PATIENCE = 10  # stop if no improvement for 10 epochs
```

### Molecule Generation Parameters
```python
# Generation settings
NUM_MOLECULES_TO_GENERATE = 1000  # generate 1000 candidates per run
TEMPERATURE = 1.0                 # sampling temperature (higher = more diverse)
VALIDITY_THRESHOLD = 0.85         # minimum % valid SMILES to accept
NOVELTY_THRESHOLD = 0.90          # minimum % new molecules (not in training data)
DIVERSITY_THRESHOLD = 0.60        # minimum Tanimoto diversity score

# Drug-likeness filters (Lipinski Rule of 5)
MAX_MOLECULAR_WEIGHT = 500        # daltons
MAX_LOGP = 5.0                    # lipophilicity
MAX_H_DONORS = 5                  # hydrogen bond donors
MAX_H_ACCEPTORS = 10              # hydrogen bond acceptors
MIN_QED_SCORE = 0.5               # drug-likeness score (0-1)
```

### Validation Metrics to Track
```python
# These must be logged every epoch
METRICS = [
    "reconstruction_loss",     # how well model recreates input molecules
    "kl_divergence",           # regularization of latent space
    "validity_rate",           # % generated molecules that are valid SMILES
    "uniqueness_rate",         # % generated molecules that are unique
    "novelty_rate",            # % generated molecules not seen in training
    "qed_score",               # average drug-likeness of generated molecules
    "sa_score",                # synthetic accessibility score (1=easy, 10=hard)
    "tanimoto_similarity",     # molecular similarity to known drugs
]
```

### Training Checkpoints and Logging
```python
# Save model every N epochs
CHECKPOINT_EVERY = 10      # save model weights every 10 epochs
SAVE_BEST_ONLY = True      # only save if validation loss improved
LOG_DIR = "outputs/logs/"  # tensorboard logs location
MODEL_DIR = "outputs/models/"  # saved model weights location

# Print progress every N batches
LOG_INTERVAL = 50          # print loss every 50 batches
```

### Target Protein Parameters for Binding
```python
# Diabetes targets
DIABETES_TARGETS = {
    "insulin_receptor": "1IR3",    # PDB ID
    "GLUT4": "6THA",
    "DPP4": "1NNY",                # sitagliptin target
}

# Infectious disease targets  
INFECTION_TARGETS = {
    "ACE2": "6M0J",                # COVID-19 target
    "HIV_protease": "3OXC",
    "bacterial_gyrase": "2XCT",    # antibiotic target
}

# Binding score thresholds
MIN_BINDING_AFFINITY = -7.0       # kcal/mol (more negative = better binding)
MIN_DOCKING_SCORE = -6.5          # acceptable docking score
```

### Data Augmentation for Better Training
```python
# Molecule data augmentation techniques
AUGMENT_DATA = True
AUGMENTATION_METHODS = [
    "randomize_smiles",    # generate alternative SMILES for same molecule
    "scaffold_hop",        # vary molecular scaffolds
    "bioisostere_swap",    # replace functional groups with equivalents
]
AUGMENTATION_FACTOR = 3   # multiply dataset size by 3x via augmentation
```

### Performance Benchmarks to Hit
```python
# Minimum acceptable model performance
TARGET_VALIDITY = 0.85       # 85% of generated SMILES must be valid
TARGET_NOVELTY = 0.90        # 90% must be new molecules
TARGET_DIVERSITY = 0.65      # 65% must be structurally diverse
TARGET_QED = 0.55            # average drug-likeness above 0.55
TARGET_SA_SCORE = 4.0        # synthetic accessibility below 4.0
```

### Hardware Configuration
```python
# Auto-detect and use best available device
import torch
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NUM_WORKERS = 4              # parallel data loading threads
PIN_MEMORY = True            # faster GPU data transfer
MIXED_PRECISION = True       # use float16 for faster training on GPU

# If no GPU available — use Google Colab
# Runtime > Change runtime type > GPU > T4 GPU (free)
```
---

## Advanced Feature Module: Next-Gen Drug Intelligence System

### Feature Overview
This module introduces cutting-edge capabilities that go beyond traditional AI drug discovery systems. It focuses on real-world applicability, continuous learning, and intelligent decision-making.

---

### 1. Self-Learning Feedback Loop

#### Description
Implement a closed-loop system where the model continuously improves using its own generated data.

#### Workflow
Generate → Validate → Score → Retrain → Improve

#### Key Benefits
- Continuous model improvement
- Adaptive learning from generated molecules
- Moves system toward autonomous drug discovery

---

### 2. Multi-Objective Optimization Engine

#### Description
Optimize multiple drug properties simultaneously instead of focusing on a single metric.

#### Parameters to Optimize
- Binding affinity
- Toxicity
- Solubility
- Stability
- Synthetic accessibility

#### Implementation Approach
- Reinforcement Learning (reward-based system)
- Weighted scoring function for all parameters

---

### 3. Toxicity and Side-Effect Prediction Module

#### Description
Predict potential adverse effects early in the drug design pipeline.

#### Features
- Hepatotoxicity (liver toxicity)
- Cardiotoxicity
- Blood-brain barrier penetration
- Off-target interaction prediction

#### Output
- Toxicity risk score
- Safety classification (Low / Medium / High)

---

### 4. Synthesis Feasibility Predictor

#### Description
Evaluate whether a generated molecule can be realistically synthesized in a laboratory.

#### Features
- Reaction pathway prediction
- Step count estimation
- Synthetic accessibility score (SA Score)

#### Importance
Prevents generation of chemically impractical molecules.

---

### 5. Drug Repositioning Engine

#### Description
Identify new therapeutic uses for existing or generated molecules.

#### Features
- Compare molecules with known drug databases
- Suggest alternative disease targets
- Similarity-based prediction (Tanimoto similarity)

---

### 6. Explainable AI (XAI) Module

#### Description
Provide transparency into model decisions.

#### Features
- Highlight important atoms/groups responsible for activity
- Visual heatmaps on molecular structures
- Explanation logs for each generated molecule

---

### 7. ADME Simulation Module (In-Silico Pharmacokinetics)

#### Description
Simulate how the drug behaves inside the human body.

#### Components
- Absorption
- Distribution
- Metabolism
- Excretion

#### Output
- Pharmacokinetic profile
- Drug-likeness validation

---

### 8. Real-Time Research Integration Module

#### Description
Continuously update system knowledge using latest scientific research.

#### Features
- Fetch latest research papers (PubMed APIs)
- Extract insights using NLP models
- Update internal knowledge base

---

### 9. Digital Twin Simulation (Future Scope)

#### Description
Simulate drug interaction in virtual patient models.

#### Parameters
- Age
- Metabolic rate
- Disease condition

#### Goal
Enable personalized drug discovery.

---

### Integration with Existing Pipeline

After molecule generation:

1. Pass molecule through toxicity predictor
2. Evaluate synthesis feasibility
3. Run multi-objective optimization scoring
4. Simulate ADME properties
5. Predict binding affinity with target proteins
6. Store results with full explainability report

Only molecules passing all thresholds are considered strong candidates.

---

### Developer Notes

- Each module should be independent and modular
- Use clear logging and print statements for traceability
- Keep implementations simple and scalable
- Prioritize readability over complexity
- Add example usage in each module file

---
---

## Architect Notes: Additional Recommendations from Co-Architect

### Why these additions matter
These parameters and guidelines were added by the project architect to ensure
Genorova AI is built to production quality — not just a prototype that works
once, but a model that is reproducible, validated, and ready for real pharma use.

---

## Model Training Parameters

### VAE Hyperparameters
```python
LATENT_DIM = 256
ENCODER_LAYERS = [512, 256]
DECODER_LAYERS = [256, 512]
MAX_SMILES_LENGTH = 120
BATCH_SIZE = 256
EPOCHS = 100
LEARNING_RATE = 0.001
LR_DECAY = 0.95
DROPOUT_RATE = 0.2
CLIP_GRADIENT = 1.0
KL_WEIGHT = 0.5
RECON_WEIGHT = 1.0
KL_ANNEALING = True
```

### Data Split
```python
TRAIN_SPLIT = 0.80
VAL_SPLIT = 0.10
TEST_SPLIT = 0.10
EARLY_STOPPING_PATIENCE = 10
```

### Molecule Generation Parameters
```python
NUM_MOLECULES_TO_GENERATE = 1000
TEMPERATURE = 1.0
VALIDITY_THRESHOLD = 0.85
NOVELTY_THRESHOLD = 0.90
DIVERSITY_THRESHOLD = 0.60
MAX_MOLECULAR_WEIGHT = 500
MAX_LOGP = 5.0
MAX_H_DONORS = 5
MAX_H_ACCEPTORS = 10
MIN_QED_SCORE = 0.5
```

### Validation Metrics to Track Every Epoch
```python
METRICS = [
    "reconstruction_loss",
    "kl_divergence",
    "validity_rate",
    "uniqueness_rate",
    "novelty_rate",
    "qed_score",
    "sa_score",
    "tanimoto_similarity",
]
```

### Performance Benchmarks to Hit
```python
TARGET_VALIDITY   = 0.85   # 85% generated SMILES must be valid
TARGET_NOVELTY    = 0.90   # 90% must be new molecules
TARGET_DIVERSITY  = 0.65   # 65% must be structurally diverse
TARGET_QED        = 0.55   # average drug-likeness above 0.55
TARGET_SA_SCORE   = 4.0    # synthetic accessibility below 4.0
```

### Checkpointing and Logging
```python
CHECKPOINT_EVERY  = 10
SAVE_BEST_ONLY    = True
LOG_DIR           = "outputs/logs/"
MODEL_DIR         = "outputs/models/"
LOG_INTERVAL      = 50
```

### Hardware Configuration
```python
import torch
DEVICE         = "cuda" if torch.cuda.is_available() else "cpu"
NUM_WORKERS    = 4
PIN_MEMORY     = True
MIXED_PRECISION = True
# Fallback: Google Colab > Runtime > Change runtime type > T4 GPU
```

### Data Augmentation
```python
AUGMENT_DATA = True
AUGMENTATION_METHODS = [
    "randomize_smiles",
    "scaffold_hop",
    "bioisostere_swap",
]
AUGMENTATION_FACTOR = 3
```

---

## Multimodal Vision Module

### Overview
Extend Genorova to read molecule images, visualize generated structures,
and analyze protein binding sites.

### New files to build

genorova/src/vision/
├── image_reader.py           # read and preprocess molecular images
├── smiles_extractor.py       # extract SMILES from structure images
├── structure_visualizer.py   # draw chemical structures from SMILES
├── protein_analyzer.py       # parse PDB protein files
└── binding_site_detector.py  # detect protein binding pockets

### Additional libraries for vision module
Pillow          # image reading and processing
cairosvg        # SVG to PNG conversion
py3Dmol         # 3D molecular visualization
biopython       # PDB protein file parsing
biotite         # protein structure analysis
torchvision     # image feature extraction

### Build order for vision module
1. structure_visualizer.py — simplest, most visual, start here
2. image_reader.py — load and preprocess molecular images
3. smiles_extractor.py — extract SMILES from structure images
4. protein_analyzer.py — parse PDB files, extract residues
5. binding_site_detector.py — score molecule-protein binding

### Target proteins
```python
DIABETES_TARGETS = {
    "insulin_receptor": "1IR3",
    "GLUT4":            "6THA",
    "DPP4":             "1NNY",
}

INFECTION_TARGETS = {
    "ACE2":             "6M0J",
    "HIV_protease":     "3OXC",
    "bacterial_gyrase": "2XCT",
}

MIN_BINDING_AFFINITY = -7.0   # kcal/mol
MIN_DOCKING_SCORE    = -6.5
```

### Integration with main pipeline
After VAE generates a SMILES string:
1. Pass to structure_visualizer.py → save chemical structure image
2. Pass SMILES + target PDB to binding_site_detector.py → get score
3. If binding score passes threshold → flag as strong candidate
4. Save candidate with structure image and binding report to outputs/

---

## Error Handling Guidelines
- Every function must have a try/except block with helpful print messages
- Always print what step is running so Pushp can follow along
- If RDKit returns None for a molecule, skip it and log a warning
- If GPU not found, automatically fall back to CPU with a clear message
- Save progress checkpoints so training can resume if interrupted

## Code Style Rules
- Every function must have a docstring in plain English
- Add a print statement at the start of each major function
- No function longer than 50 lines — split into smaller helpers
- Variable names must be descriptive (not x, y, z — use molecule, smiles, latent_vector)
- Add a simple example at the bottom of every file showing how to use it

---

## Memory Architecture for Genorova AI

### Four layers of memory

#### Layer 1 — Session memory (RAM)
```python
# Keep track of generated molecules in current run
# Prevents duplicate generation within same session
SESSION_MEMORY = {
    "generated_smiles": set(),      # all SMILES generated this session
    "valid_candidates": [],          # molecules that passed all filters
    "failed_molecules": [],          # invalid SMILES for analysis
    "session_stats": {}              # running statistics
}
```

#### Layer 2 — Persistent memory (Database)
```python
# Save every generated molecule permanently to SQLite database
# Location: outputs/genorova_memory.db
# Schema:
DATABASE_SCHEMA = {
    "molecules": {
        "id":               "INTEGER PRIMARY KEY",
        "smiles":           "TEXT UNIQUE",
        "validity":         "BOOLEAN",
        "qed_score":        "FLOAT",
        "sa_score":         "FLOAT",
        "molecular_weight": "FLOAT",
        "target_disease":   "TEXT",
        "binding_score":    "FLOAT",
        "is_candidate":     "BOOLEAN",
        "generated_at":     "TIMESTAMP",
        "model_version":    "TEXT",
    }
}
# This means Genorova NEVER forgets a molecule it generated
# Over time this becomes a proprietary database of AI-designed drugs
```

#### Layer 3 — Model memory (Checkpoints)
```python
# Save model weights every 10 epochs
# Best model is always preserved
# Allows training to resume if interrupted
CHECKPOINT_STRATEGY = {
    "save_every_n_epochs": 10,
    "keep_top_n_models":   3,       # keep 3 best checkpoints
    "metric_to_monitor":   "val_loss",
    "save_optimizer_state": True,   # resume training exactly
}
```

#### Layer 4 — Latent space memory (Smart generation)
```python
# Store coordinates of best molecules in latent space
# Use these as seeds for future generation — guided search
LATENT_MEMORY = {
    "top_candidates_latent_vectors": [],  # save z vectors of best molecules
    "cluster_centers": [],                # cluster similar molecules
    "exploration_radius": 0.5,           # how far to search around known good points
}
# This makes Genorova smarter over time —
# it remembers WHERE in chemical space good drugs live
```

### Memory file structure

genorova/
└── outputs/
├── genorova_memory.db       # persistent molecule database
├── models/                  # model checkpoints
├── latent_vectors/          # saved latent space coordinates
└── session_logs/            # per-session run logs

### Key principle
Every time Genorova runs, it should:
1. Load previous session memory from database
2. Never regenerate a molecule it already tried
3. Use best known latent coordinates as generation seeds
4. Save everything new back to the database
5. Get smarter and more targeted with every run

---

## Architect Addition: Real-World Clinical Validation Layer
## (Based on analysis of 50 Phase 3 diabetes clinical trials from ClinicalTrials.gov)

### Why this matters
Genorova doesn't just need to generate valid molecules.
It needs to generate molecules that could actually pass clinical trials.
This section teaches Claude Code what real pharma endpoints look like
so Genorova can score generated molecules against them.

---

### Real Clinical Trial Endpoints Genorova Must Target

#### Primary endpoints from real Phase 3 diabetes trials
These are what pharma companies actually measure — our generated
molecules must be predicted to influence these outcomes:

```python
DIABETES_CLINICAL_TARGETS = {

    # Most important — appears in 90% of all diabetes trials
    "HbA1c_reduction": {
        "description": "Reduce glycated hemoglobin from baseline",
        "target_change": "-0.5% to -1.5% from baseline",
        "timeframe": "24 to 26 weeks",
        "benchmark": "HbA1c < 7.0% is ADA success target",
        "genorova_score_weight": 0.35    # highest priority
    },

    # Second most important
    "fasting_plasma_glucose": {
        "description": "Reduce fasting blood glucose levels",
        "target_change": "Significant reduction from baseline",
        "timeframe": "24 weeks",
        "benchmark": "FPG < 126 mg/dL is normal",
        "genorova_score_weight": 0.25
    },

    # Safety critical
    "hypoglycemia_risk": {
        "description": "Must NOT cause dangerous low blood sugar",
        "target": "Minimal hypoglycemic episodes",
        "severity_levels": ["severe", "documented_symptomatic", "asymptomatic", "nocturnal"],
        "genorova_score_weight": 0.20    # penalize molecules that cause this
    },

    # Secondary but important
    "body_weight": {
        "description": "Ideally reduce or maintain body weight",
        "target_change": "Weight loss >= 5% is a bonus",
        "genorova_score_weight": 0.10
    },

    # Cardiovascular safety
    "cardiovascular_safety": {
        "description": "No increase in CV death, MI, or stroke",
        "key_markers": ["systolic_blood_pressure", "LDL_cholesterol", "QTc_interval"],
        "genorova_score_weight": 0.10
    }
}
```

#### Composite Genorova Molecule Scoring Function
```python
def genorova_clinical_score(molecule):
    """
    Score a generated molecule against real clinical trial endpoints.
    Higher score = better drug candidate.
    Scale: 0.0 (terrible) to 1.0 (excellent candidate)

    Based on analysis of 50 Phase 3 diabetes trials from ClinicalTrials.gov
    """
    score = 0.0

    # Lipinski Rule of 5 — basic drug-likeness
    if passes_lipinski(molecule):
        score += 0.20

    # QED drug-likeness score (0-1)
    qed = calculate_qed(molecule)
    score += qed * 0.20

    # Synthetic accessibility (lower = easier to make = better)
    sa = calculate_sa_score(molecule)
    if sa < 3.0:
        score += 0.15
    elif sa < 5.0:
        score += 0.08

    # Predicted binding to diabetes targets
    # Insulin receptor (PDB: 1IR3), DPP4 (PDB: 1NNY)
    binding = predict_binding_affinity(molecule, target="insulin_receptor")
    if binding < -8.0:       # very strong binding
        score += 0.25
    elif binding < -7.0:     # good binding
        score += 0.15
    elif binding < -6.0:     # acceptable binding
        score += 0.08

    # Novelty — not in training data
    if is_novel(molecule):
        score += 0.10

    # Structural similarity to known diabetes drugs
    # (semaglutide, metformin, sitagliptin, empagliflozin)
    similarity = max_similarity_to_approved_drugs(molecule)
    if 0.3 < similarity < 0.7:   # similar but not identical
        score += 0.10

    return round(score, 3)
```

### Molecule Report Template
Every molecule Genorova generates should produce this report:

```python
MOLECULE_REPORT_TEMPLATE = {
    "smiles":                  "",     # generated SMILES string
    "molecular_weight":        0.0,    # daltons
    "logP":                    0.0,    # lipophilicity
    "hbd":                     0,      # H-bond donors
    "hba":                     0,      # H-bond acceptors
    "qed_score":               0.0,    # drug-likeness 0-1
    "sa_score":                0.0,    # synthetic accessibility 1-10
    "passes_lipinski":         False,  # Rule of 5 pass/fail
    "binding_affinity_insulin_receptor": 0.0,  # kcal/mol
    "binding_affinity_DPP4":   0.0,    # kcal/mol
    "is_novel":                False,  # not seen in training data
    "similarity_to_metformin": 0.0,    # Tanimoto score
    "similarity_to_semaglutide": 0.0,
    "genorova_clinical_score": 0.0,    # composite score 0-1
    "recommendation":          "",     # "Strong candidate" / "Borderline" / "Reject"
    "structure_image_path":    "",     # path to saved 2D structure image
    "generated_at":            "",     # timestamp
    "model_version":           "1.0",
}
```

### Known Approved Diabetes Drugs as Reference Points
Genorova should compare every generated molecule against these:

```python
APPROVED_DIABETES_REFERENCE_DRUGS = {
    "metformin":      "CN(C)C(=N)NC(=N)N",                    # biguanide
    "sitagliptin":    "Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F",
    "empagliflozin":  "OC[C@@H]1O[C@@H](c2ccc(Cl)cc2-c2ccc(OCC3CCOCC3)cc2)[C@H](O)[C@@H](O)[C@@H]1O",
    "glipizide":      "Cc1cnc(CN2C(=O)CCC2=O)s1",             # sulfonylurea
    "insulin_analog": "reference_pdb_1IR3",                    # use PDB structure
}
```

### Build This File: src/scorer.py
```python
# src/scorer.py
# Genorova molecule scoring engine
# Scores generated molecules against real clinical trial endpoints
# Based on 50 Phase 3 diabetes trials from ClinicalTrials.gov

def score_molecule(smiles):
    """
    Master scoring function.
    Input: SMILES string
    Output: complete molecule report dictionary
    """
    pass   # Claude Code — build this file fully

def passes_lipinski(smiles):
    """Check Lipinski Rule of 5 using RDKit"""
    pass

def calculate_qed(smiles):
    """Calculate drug-likeness score using RDKit QED module"""
    pass

def calculate_sa_score(smiles):
    """Calculate synthetic accessibility score"""
    pass

def is_novel(smiles, database_path="outputs/genorova_memory.db"):
    """Check if molecule is new — not in our generated database"""
    pass

def generate_molecule_report(smiles):
    """Generate full report for a molecule and save to database"""
    pass

def rank_candidates(molecule_list):
    """
    Rank a list of generated molecules by clinical score.
    Return top candidates sorted by genorova_clinical_score descending.
    """
    pass
```

### Priority Build Order Updated
Based on everything above, build in this exact order:
1. src/data_loader.py        — load molecular data
2. src/preprocessor.py       — encode SMILES
3. src/model.py              — VAE architecture
4. src/train.py              — training loop
5. src/generate.py           — generate molecules
6. src/scorer.py             — score against clinical endpoints  ← NEW
7. src/validate.py           — final validation
8. src/vision/structure_visualizer.py  — visualize structures
9. src/vision/protein_analyzer.py     — protein binding
10. src/vision/binding_site_detector.py — binding sites

# GenorovaAI Working Rules

## Project purpose
GenorovaAI is being upgraded from a molecule generator into a drug-candidate validation platform.

## Scientific priorities
Every strong candidate should be evaluated across:
1. Chemical sanity
2. Target engagement
3. ADMET/safety
4. Clinical utility

## Non-negotiable rules
- Never present proxy scores as real experimental truth.
- Clearly label fallback, estimated, mock, or unavailable values.
- Keep code modular and documented.
- Prefer typed Python and structured outputs.
- Do not hardcode scientific outputs.
- Keep the interface understandable to non-technical faculty.

## Desired modules
- validation/chemistry
- validation/binding
- validation/admet
- validation/clinical

## Expected outputs
For each candidate molecule, show:
- SA score
- novelty status
- PAINS result
- docking comparison vs reference
- key residue interactions
- hepatotoxicity risk
- hERG risk
- CYP interaction risk
- final recommendation with plain-language explanation