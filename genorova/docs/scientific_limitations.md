# Genorova AI — Scientific Limitations and Honest Assessment

This document describes what Genorova AI computes, what it estimates, and what
still requires wet-lab validation before any real-world drug-discovery decision
can be made.

Read this document before interpreting any Genorova output in a scientific or
academic context.

---

## Part 1: What is Real vs Estimated

### Genuinely Computed (can be trusted as-is)

| Output | Source | How reliable |
|---|---|---|
| SMILES validity | RDKit `MolFromSmiles` | Exact — either parses or doesn't |
| Molecular weight | RDKit Descriptors | Exact within floating-point precision |
| LogP | RDKit Crippen | Good approximation (±0.5 typical error) |
| H-bond donors/acceptors | RDKit Lipinski | Exact from graph topology |
| QED score | RDKit QED module | Deterministic given SMILES |
| SA score (RDKit sascorer) | RDKit Contrib SA_Score | ±0.5 vs expert opinion; validated literature tool |
| PAINS filter | RDKit FilterCatalog | Direct substructure match; false negatives possible |
| Tanimoto similarity | RDKit DataStructs | Exact (given fingerprint parameters) |

### Heuristic Estimates (labeled `heuristic_proxy` in output)

These outputs are derived from rules and descriptor thresholds, not from validated
predictive models.  They are useful for screening but must be confirmed.

| Output | Method | Limitations |
|---|---|---|
| Hepatotoxicity risk | Structural alerts + LogP/MW rules | No experimental training data; misses novel toxicophores |
| hERG inhibition risk | Pharmacophore heuristic (basic N + aromatic + LogP) | Many exceptions; drugs like amiodarone are hERG blockers not flagged by simple rules |
| CYP450 risk | Structural alerts (pyridine, imidazole, etc.) | Ignores 3D binding geometry; substrate ≠ inhibitor |
| Scaffold binding proxy | Tanimoto similarity to reference + property bonus | Not validated against binding assay data; Tanimoto is a structural similarity measure, not a binding predictor |
| Clinical decision score | Weighted combination of heuristic components | The weights were set by engineering judgment, not calibrated on clinical trial outcomes |

### Not Computed At All (currently unavailable)

| Feature | Why not available | Needed to address |
|---|---|---|
| Real docking energy | Requires AutoDock Vina + prepared PDBQT files | Install Vina, prepare proteins (see validation_pipeline.md) |
| PubChem novelty check | Requires internet; off by default | Set `pubchem_lookup=True` |
| SureChEMBL patent search | No API integration implemented | Manual search at surechembl.org |
| Metabolic stability prediction | No metabolite prediction engine | Use external tools (e.g., MetaSite, GLORYx) |
| Solubility prediction | Not implemented | Use AqSolDB / ESOL model externally |
| Blood-brain barrier penetration | Not implemented | Use pkCSM or SwissADME |
| In-vivo ADMET | Cannot be predicted by any purely computational tool | Wet-lab studies required |

---

## Part 2: Known Scientific Weaknesses

### 2.1 Molecule Generation Quality

The VAE generates SMILES strings from a learned latent space.  Key limitations:

- **Validity rate:** The original parallel-decoder VAE achieves approximately 9–15% valid SMILES on held-out test sets without structural guards.  With guards, validity improves but generated molecules may be subtly over-corrected.
- **Distribution collapse:** VAE latent spaces can collapse, causing many generated molecules to be structurally similar to each other (low diversity).  KL warm-up and free-bits regularisation mitigate this but do not eliminate it.
- **Training data scope:** The model was trained on a small diabetes/infection drug subset (< 100 molecules in minimal mode).  Full ChEMBL training (250K+ molecules) would produce a much more capable generator.

### 2.2 Binding Score Limitations

**Scaffold proxy mode (most users will see this):**
- The proxy score is an interpolation between Tanimoto = 0 (−4.0 "weak") and Tanimoto = 1 (reference literature binding energy).
- A Tanimoto similarity of 0.3 does NOT mean the molecule will bind with 30% the potency of the reference drug.  Structural similarity and binding affinity are only loosely correlated.
- The proxy has no knowledge of 3D pocket geometry, induced fit, solvation, or electrostatics.
- **Do not report proxy scores as docking results.**  The output always labels them `mode="scaffold_proxy"`.

**Real docking mode (when Vina is available):**
- AutoDock Vina is a fast empirical scoring function.  Typical RMSD vs crystallographic binding pose: 1–3 Å.  Typical score error vs experimental Ki: 1–2 kcal/mol.
- Protein flexibility is not modelled (rigid receptor docking).
- Water-mediated interactions, allosteric effects, and induced fit are not captured.
- Predicted binding scores should be treated as a ranking tool, not an absolute affinity prediction.

### 2.3 ADMET Limitations

All ADMET predictions in Genorova v2 are based on structural alerts and descriptor thresholds.  They are **not trained machine-learning models**.

Known failure modes:
- **DILI:** Many approved drugs have aromatic rings, LogP > 4, or amine groups without causing liver injury.  The alert-based method has high false-positive rates.
- **hERG:** Not all molecules with basic nitrogens and aromatic rings block hERG.  Geometric and charge-state factors (not modelled here) are critical.
- **CYP:** Substrate and inhibitor are different concepts.  This module flags substrates (metabolised by CYP) but may also flag CYP inhibitors.  The distinction matters clinically.

**Recommended external tools for better ADMET:**
- pkCSM (https://biosig.lab.uq.edu.au/pkcsm/) — web tool, validated on large datasets
- SwissADME (http://www.swissadme.ch/) — free, covers multiple ADMET properties
- ADMETLab 3.0 (https://admetlab3.scbdd.com/) — comprehensive ADMET prediction
- ProTox-3.0 (https://tox.charite.de/protox3/) — toxicity prediction

### 2.4 Novelty Assessment Limitations

- Local database check: only checks molecules that Genorova has previously generated and stored.  It does NOT check the broader chemical universe.
- PubChem lookup: finds whether the exact SMILES (or a close canonical form) is in PubChem.  A molecule not in PubChem may still be patented under a different representation.
- Tanimoto similarity threshold (0.85) for "known analogue" is a conventional cutoff but is not a legal patentability standard.  Patent searches require professional IP analysis.

---

## Part 3: What Wet-Lab Validation Is Required

Before any Genorova candidate is considered seriously, these experimental steps are required:

### 3.1 Minimum computational confirmation
- [ ] Re-run docking with prepared protein structure (AutoDock Vina with energy minimization)
- [ ] Run ADMET through a validated tool (pkCSM or SwissADME)
- [ ] Check molecule against patent databases (SureChEMBL or Scifinder)
- [ ] Confirm PAINS non-interference with your specific assay format

### 3.2 In-vitro primary validation
- [ ] Binding assay (ITC, SPR, or fluorescence competition) against target protein
- [ ] Cell-based potency assay (IC50 or EC50) in appropriate disease cell line
- [ ] LDH assay or MTT viability for cytotoxicity screening (HepG2 for DILI)
- [ ] hERG patch-clamp or FLIPR assay for cardiac safety

### 3.3 ADME profiling
- [ ] Aqueous solubility (kinetic / thermodynamic)
- [ ] Caco-2 or PAMPA membrane permeability
- [ ] Microsomal metabolic stability (human liver microsomes)
- [ ] CYP inhibition panel (3A4, 2D6, 2C9 at minimum)

### 3.4 In-vivo (preclinical)
- [ ] PK study in appropriate rodent model (Cmax, AUC, half-life, bioavailability)
- [ ] Efficacy study in disease model (e.g. STZ-induced diabetic mice for diabetes)
- [ ] Safety/tolerability study

---

## Part 4: Literature References for Methods Used

### SA Score
Ertl P, Schuffenhauer A. "Estimation of synthetic accessibility score of drug-like molecules based on molecular complexity and fragment contributions." *J Cheminform.* 2009;1:8.

### PAINS Filtering
Baell JB, Holloway GA. "New substructure filters for removal of pan assay interference compounds (PAINS) from screening libraries." *J Med Chem.* 2010;53(7):2719-2740.

### hERG Structural Correlates
Redfern WS, et al. "Relationships between preclinical cardiac electrophysiology, clinical QT interval prolongation and torsade de pointes for a broad range of drugs." *Cardiovasc Res.* 2003;58(1):32-45.

Sanguinetti MC, Tristani-Firouzi M. "hERG potassium channels and cardiac arrhythmia." *Nature.* 2006;440(7083):463-469.

### CYP450 Substrate Patterns
Pelkonen O, et al. "Inhibition and induction of human cytochrome P450 enzymes: current status." *Arch Toxicol.* 2008;82(10):667-715.

### DILI Structural Alerts
Brenk R, et al. "Lessons learnt from assembling screening libraries for drug discovery for neglected diseases." *ChemMedChem.* 2008;3(3):435-444.

### AutoDock Vina
Trott O, Olson AJ. "AutoDock Vina: improving the speed and accuracy of docking with a new scoring function, efficient optimization, and multithreading." *J Comput Chem.* 2010;31(2):455-461.

### Reference Binding Energies Used as Anchors
- Insulin receptor / staurosporine: Hubbard SR, et al. *Nature.* 1994;372:746 (approximate IC50 converted to ΔG)
- DPP4 / sitagliptin: Kim D, et al. *J Med Chem.* 2005;48:141
- ACE2 / MLN-4760: Dales NA, et al. *J Am Chem Soc.* 2002;124:11852

---

## Part 5: Responsible Use Statement

Genorova AI is a research support tool for computational drug discovery.  It is not:
- A regulatory submission tool
- A replacement for experimental validation
- A predictor of clinical outcomes
- A toxicology assessment for human exposure

All outputs must be reviewed by qualified medicinal chemists and pharmacologists
before any experimental or financial decision is made.

The ADMET predictions in this system have been built using published structural
knowledge but have not been validated on a held-out experimental dataset.  They
are provided as a screening-level signal and must be confirmed by validated
computational or experimental tools before being cited in any scientific report.
