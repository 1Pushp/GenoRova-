"""
Genorova AI — Validation Pipeline: Typed Output Models
=======================================================

PURPOSE:
Defines Pydantic v2 data models for every stage of the second-stage
validation pipeline.  All results travel as these typed objects so that
callers (API, tests, reports) always receive a consistent, documented schema.

IMPORTANT HONESTY NOTE:
Many scores in this pipeline are PROXY ESTIMATES based on molecular
descriptors and structural alerts.  Each model includes a ``data_source``
field that makes this explicit.  Values are never presented as measured
experimental data unless they come from a real docking run or a validated
external service.

Possible data_source values (used consistently throughout the pipeline):
    "rdkit_computed"        — calculated directly by RDKit from the SMILES
    "heuristic_proxy"       — rule-based estimate, NOT a physical measurement
    "real_docking"          — produced by AutoDock Vina or equivalent
    "pubchem_lookup"        — confirmed by PubChem REST API response
    "local_db_lookup"       — checked against local Genorova SQLite database
    "external_unavailable"  — external service was not reachable (timeout/error)
    "rdkit_unavailable"     — RDKit not loaded; result is a pure-Python estimate

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class _StageResult(BaseModel):
    """
    Base class shared by all stage result models.
    Adds a standard metadata block so every result carries:
      - when it was computed
      - whether RDKit was available
      - any notes the module wants to attach
    """
    computed_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO-8601 UTC timestamp when this result was produced.",
    )
    rdkit_available: bool = Field(
        default=True,
        description="Whether RDKit was successfully loaded when this was run.",
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Free-text notes, warnings, or caveats from the module.",
    )


# ---------------------------------------------------------------------------
# A.  Chemical Sanity Result
# ---------------------------------------------------------------------------

class PAINSMatch(BaseModel):
    """One matched PAINS structural alert."""
    alert_name: str = Field(description="Name of the matched PAINS filter pattern.")
    description: str = Field(
        default="",
        description="Human-readable description of what this alert flags.",
    )


class NoveltyStatus(BaseModel):
    """
    Structured novelty report for a molecule.

    Flags:
        potentially_novel_patentable  — not found locally or via PubChem
        known_repurposing_lead        — matches a known drug (Tanimoto ≥ 0.85)
        unrealistic                   — too simple / too complex to be useful
        local_only_checked            — PubChem lookup was skipped or failed
    """
    flag: Literal[
        "potentially_novel_patentable",
        "known_repurposing_lead",
        "unrealistic",
        "local_only_checked",
    ] = Field(description="Primary novelty classification.")

    found_in_local_db: bool = Field(
        description="True if molecule matches local Genorova database."
    )
    found_in_approved_drugs: bool = Field(
        description="True if SMILES matches a known approved drug exactly."
    )
    pubchem_cid: Optional[int] = Field(
        default=None,
        description="PubChem CID if the molecule was found there, else None.",
    )
    pubchem_checked: bool = Field(
        description="Whether PubChem was actually queried (requires internet)."
    )
    most_similar_drug: Optional[str] = Field(
        default=None,
        description="Name of the approved drug with the highest Tanimoto similarity.",
    )
    max_tanimoto: Optional[float] = Field(
        default=None,
        description="Tanimoto similarity score (Morgan FP, radius 2) to most similar drug.",
    )
    data_source: str = Field(
        default="local_db_lookup",
        description="How novelty was determined (see module docstring for options).",
    )


class ChemistryResult(_StageResult):
    """
    Result of the Chemical Sanity stage (Module A).

    Contains:
      - SA score (ease of synthesis)
      - PAINS filter results
      - Novelty status with source labeling
    """
    smiles: str = Field(description="Input SMILES string.")
    valid_smiles: bool = Field(description="True if RDKit can parse the SMILES.")

    # SA score
    sa_score: Optional[float] = Field(
        default=None,
        description=(
            "Synthetic Accessibility score, 1 (easy) – 10 (nearly impossible). "
            "Computed by RDKit sascorer when available; heuristic otherwise."
        ),
    )
    sa_score_source: str = Field(
        default="heuristic_proxy",
        description="How the SA score was computed (rdkit_computed / heuristic_proxy).",
    )
    sa_flag: Literal["synthesizable", "difficult", "impractical"] = Field(
        default="difficult",
        description=(
            "synthesizable: SA ≤ 4  |  difficult: 4 < SA ≤ 6  |  "
            "impractical: SA > 6"
        ),
    )

    # PAINS
    is_pains: bool = Field(
        description="True if molecule matches one or more PAINS structural alerts."
    )
    pains_matches: List[PAINSMatch] = Field(
        default_factory=list,
        description="List of matched PAINS alerts.  Empty when is_pains is False.",
    )
    pains_source: str = Field(
        default="rdkit_computed",
        description="How PAINS was evaluated.",
    )

    # Novelty
    novelty: NoveltyStatus = Field(
        description="Structured novelty / repurposing classification."
    )

    # Overall sanity flag
    passes_sanity: bool = Field(
        description=(
            "True when: valid SMILES + not PAINS + SA ≤ 6. "
            "Does NOT mean the molecule is clinically useful."
        ),
    )


# ---------------------------------------------------------------------------
# B.  Target Engagement / Binding Result
# ---------------------------------------------------------------------------

class BindingResult(_StageResult):
    """
    Result of the Target Engagement stage (Module B).

    When real docking is blocked or unavailable the module uses a proxy mode.
    The ``confidence`` and ``mode`` fields always make this explicit.
    """
    smiles: str = Field(description="Input SMILES string.")
    target: str = Field(description="Target protein name or PDB ID.")
    reference_drug: str = Field(
        description="Name of the reference drug used for comparison."
    )

    # Candidate score
    docking_score: Optional[float] = Field(
        default=None,
        description=(
            "Binding score for the candidate.  Units: kcal/mol when real docking "
            "was run; unitless proxy score otherwise.  Always check ``mode``."
        ),
    )

    # Reference drug score
    reference_score: Optional[float] = Field(
        default=None,
        description="Binding score for the reference drug under the same protocol.",
    )

    # Delta
    delta_vs_reference: Optional[float] = Field(
        default=None,
        description=(
            "docking_score – reference_score.  Negative = candidate binds better "
            "than reference (only meaningful when mode == 'real_docking')."
        ),
    )

    # Interaction details (populated only by real docking)
    key_h_bonds: List[str] = Field(
        default_factory=list,
        description="Residues involved in key hydrogen bonds with the ligand.",
    )
    key_hydrophobic: List[str] = Field(
        default_factory=list,
        description="Residues involved in hydrophobic contacts.",
    )

    # Source metadata — always present
    mode: Literal["real_docking", "scaffold_proxy", "fallback_proxy", "unavailable"] = Field(
        description=(
            "real_docking: AutoDock Vina result.  "
            "scaffold_proxy: descriptor-based estimate.  "
            "fallback_proxy: target supports docking but the runtime is blocked or failed.  "
            "unavailable: could not score."
        ),
    )
    confidence: Literal["high", "medium", "low", "none"] = Field(
        description=(
            "high: real docking with validated protein structure.  "
            "medium: proxy with good descriptor coverage.  "
            "low: proxy with limited coverage.  "
            "none: unable to score."
        ),
    )
    data_source: str = Field(
        description="Source of this result (see module docstring).",
    )
    interpretation: str = Field(
        default="",
        description="Plain-language interpretation of the binding result.",
    )
    evidence_level: str = Field(
        default="unavailable",
        description="real_docking / proxy_screening / fallback_proxy / unavailable",
    )
    mode_reason: str = Field(
        default="",
        description="Why this binding mode was used.",
    )
    real_docking_status: str = Field(
        default="blocked",
        description="ready / executed / runtime_failed / blocked / unsupported_target",
    )
    real_docking_failure: Optional[str] = Field(
        default=None,
        description="The exact runtime blocker or failure reason when real docking was not available.",
    )
    real_docking_probe: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured readiness probe for the real docking path.",
    )


# ---------------------------------------------------------------------------
# C.  ADMET and Safety Result
# ---------------------------------------------------------------------------

class RiskLevel(BaseModel):
    """
    A single ADMET risk assessment with its source and alerts.

    ``level`` is always one of: low / medium / high / unknown.
    ``method`` describes how the assessment was made so readers know
    whether to treat it as a real prediction or a heuristic flag.
    """
    level: Literal["low", "medium", "high", "unknown"] = Field(
        description="Risk level."
    )
    score: Optional[float] = Field(
        default=None,
        description="Numerical risk score where applicable (0 = low, 1 = high).",
    )
    alerts: List[str] = Field(
        default_factory=list,
        description="Structural alerts or rules that contributed to this risk level.",
    )
    method: str = Field(
        description=(
            "How the risk was estimated.  Always read this before acting on level.  "
            "Example values: 'structural_alerts_heuristic', 'rdkit_descriptors_proxy'."
        ),
    )


class ADMETResult(_StageResult):
    """
    Result of the ADMET and Safety stage (Module C).

    IMPORTANT: All predictions in this module are HEURISTIC PROXIES based on
    structural alerts and molecular descriptors.  They are NOT validated ML
    models.  They provide a screening-level signal only and must be confirmed
    by proper QSAR models or in-vitro assays before any decision is made.
    """
    smiles: str = Field(description="Input SMILES string.")

    hepatotoxicity_risk: RiskLevel = Field(
        description="Predicted liver toxicity (DILI) risk — heuristic proxy."
    )
    herg_risk: RiskLevel = Field(
        description="Predicted hERG potassium channel inhibition risk — heuristic proxy."
    )
    cyp_risk: RiskLevel = Field(
        description="Predicted CYP450 interaction risk — heuristic proxy."
    )

    overall_safety_flag: Literal["likely_safe", "caution", "likely_unsafe", "unknown"] = Field(
        description=(
            "likely_safe: all risks low.  "
            "caution: at least one medium risk.  "
            "likely_unsafe: at least one high risk.  "
            "unknown: assessment incomplete."
        ),
    )
    safety_score: float = Field(
        description=(
            "Composite safety score: 0.0 (highest risk) – 1.0 (lowest risk).  "
            "Heuristic proxy only."
        ),
    )
    disclaimer: str = Field(
        default=(
            "All ADMET predictions are heuristic proxies based on structural alerts "
            "and molecular descriptors.  They have NOT been validated against "
            "experimental assay data and must not be used as the sole basis for "
            "any safety decision."
        ),
        description="Standard disclaimer for this module.",
    )


# ---------------------------------------------------------------------------
# D.  Clinical Utility Result
# ---------------------------------------------------------------------------

class ClinicalComparison(BaseModel):
    """
    Side-by-side comparison of candidate vs reference drug on key metrics.
    """
    metric: str = Field(description="Name of the property being compared.")
    candidate_value: Optional[Any] = Field(description="Candidate molecule's value.")
    reference_value: Optional[Any] = Field(description="Reference drug's value.")
    better: Optional[bool] = Field(
        default=None,
        description="True if candidate appears better on this metric.",
    )
    note: str = Field(default="", description="Short explanation of the comparison.")


class ClinicalResult(_StageResult):
    """
    Result of the Clinical Utility stage (Module D).

    The decision field uses a 3-level verdict:
        advance            — molecule passes all criteria; recommend for further study
        conditional_advance — passes most criteria; specific concerns noted
        reject             — fails one or more critical criteria

    IMPORTANT: This is a COMPUTATIONAL decision aid, not a clinical recommendation.
    It integrates outputs from stages A–C and applies configurable scoring weights.
    """
    smiles: str = Field(description="Input SMILES string.")
    target: str = Field(description="Target protein name.")
    disease: str = Field(description="Target disease area.")
    reference_drug: str = Field(description="Reference drug used for comparison.")

    decision: Literal["advance", "conditional_advance", "reject"] = Field(
        description="Clinical utility verdict."
    )
    decision_score: float = Field(
        description="Composite score driving the decision (0.0 – 1.0).",
    )
    explanation: str = Field(
        description="Plain-language explanation of the decision for non-technical readers.",
    )
    conditions: List[str] = Field(
        default_factory=list,
        description=(
            "Conditions that must be met before advancing "
            "(populated only when decision == 'conditional_advance')."
        ),
    )
    rejection_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons for rejection (populated only when decision == 'reject').",
    )

    comparisons: List[ClinicalComparison] = Field(
        default_factory=list,
        description="Property-by-property comparison vs reference drug.",
    )

    potency_vs_toxicity_note: str = Field(
        default="",
        description="Notes on the tradeoff between predicted potency and safety signals.",
    )
    recommended_next_step: str = Field(
        default="",
        description="Suggested next experimental or computational step.",
    )


# ---------------------------------------------------------------------------
# E.  Evidence Ledger (per-candidate scientific honesty summary)
# ---------------------------------------------------------------------------

class EvidenceLedgerBinding(BaseModel):
    """Binding sub-record in the evidence ledger."""
    mode: str = Field(description="real_docking / scaffold_proxy / fallback_proxy / unavailable")
    score: Optional[float] = Field(default=None)
    reference_drug: str = Field(default="unknown")
    reference_score: Optional[float] = Field(default=None)
    delta: Optional[float] = Field(default=None)
    comparator_note: str = Field(default="")
    evidence_level: str = Field(description="real_docking / heuristic_proxy / fallback_proxy / unavailable")
    mode_reason: str = Field(default="")
    real_docking_status: str = Field(default="blocked")
    real_docking_failure: Optional[str] = Field(default=None)
    probe_blockers: List[str] = Field(default_factory=list)


class EvidenceLedger(BaseModel):
    """
    Structured per-candidate evidence summary.

    Shows explicitly:
      - whether the molecule is known, uncertain, or potentially novel
      - which scores are computed vs heuristic vs real docking
      - major safety flags
      - confidence tier and plain-language rationale

    This is the primary tool for maintaining scientific honesty in reports and
    for faculty reviewers who need to evaluate the quality of each decision.

    Confidence tiers:
        tier_1_high   — real docking + RDKit SA + PubChem novelty confirmed
        tier_2_medium — RDKit SA with proxy binding, or real docking without novelty check
        tier_3_low    — all heuristic proxies; use for screening only
    """

    novelty: Dict[str, Any] = Field(
        description="Novelty status with evidence level (known / uncertain / potentially_novel)."
    )
    sa_score: Dict[str, Any] = Field(
        description="SA score value, flag, and evidence level (computed / heuristic)."
    )
    pains: Dict[str, Any] = Field(
        description="PAINS alert status and list of matched alerts."
    )
    binding: EvidenceLedgerBinding = Field(
        description="Binding score with comparator note and evidence level."
    )
    admet: Dict[str, Any] = Field(
        description="ADMET risk levels (hepatotoxicity, hERG, CYP) and evidence level."
    )
    clinical: Dict[str, Any] = Field(
        description="Clinical decision and score with evidence level (always heuristic)."
    )
    major_risks: List[str] = Field(
        default_factory=list,
        description="List of major risk flags that reviewers should investigate.",
    )
    confidence_tier: str = Field(
        description="Overall confidence tier: tier_1_high / tier_2_medium / tier_3_low."
    )
    confidence_note: str = Field(
        description="Plain-language explanation of why this confidence tier was assigned."
    )
    recommendation_rationale: str = Field(
        description=(
            "Plain-language rationale for the final recommendation, "
            "written for non-technical faculty reviewers."
        )
    )
    dt_warnings: List[str] = Field(
        default_factory=list,
        description="Disease-target consistency warnings (empty = no issues).",
    )


# ---------------------------------------------------------------------------
# F.  Full Validation Result (all 4 stages combined)
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    """
    Complete second-stage validation report for one molecule.

    Aggregates all four pipeline stages into a single structured object that
    can be serialised directly to JSON for API responses, reports, or storage.
    """
    smiles: str = Field(description="Input SMILES string.")
    target: str = Field(description="Protein target used for binding evaluation.")
    disease: str = Field(description="Disease context for clinical evaluation.")
    reference_drug: str = Field(description="Reference drug used for comparison.")

    chemistry: ChemistryResult = Field(description="Stage A — Chemical Sanity.")
    binding: BindingResult = Field(description="Stage B — Target Engagement.")
    admet: ADMETResult = Field(description="Stage C — ADMET and Safety.")
    clinical: ClinicalResult = Field(description="Stage D — Clinical Utility.")

    # Top-level summary for quick display
    final_decision: Literal["advance", "conditional_advance", "reject"] = Field(
        description="Mirrors ClinicalResult.decision for quick access.",
    )
    summary: str = Field(
        description="One-paragraph plain-language summary of all four stages.",
    )

    # Evidence ledger — scientific honesty record for each candidate
    evidence_ledger: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Structured per-candidate evidence summary.  Shows which scores are "
            "computed vs heuristic, novelty status, major risks, and the confidence "
            "tier with plain-language rationale for non-technical reviewers.  "
            "Cast to EvidenceLedger for full typed access."
        ),
    )
    pipeline_warnings: List[str] = Field(
        default_factory=list,
        description=(
            "Warnings raised during pipeline execution (e.g. disease-target mismatch).  "
            "Empty list means no issues detected."
        ),
    )

    pipeline_version: str = Field(
        default="2.1",
        description="Version of the Genorova validation pipeline that produced this result.",
    )
    validated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO-8601 UTC timestamp for this full validation run.",
    )

    # Answers to the five core questions
    can_be_synthesized: Optional[bool] = Field(
        default=None,
        description="SA score ≤ 4 (True) / ≤ 6 (borderline) / > 6 (False).",
    )
    likely_novel: Optional[bool] = Field(
        default=None,
        description=(
            "True when novelty flag is 'potentially_novel_patentable' "
            "and not found in local DB or PubChem."
        ),
    )
    binds_well_vs_standard: Optional[bool] = Field(
        default=None,
        description=(
            "True when binding delta vs reference drug is ≤ −0.5 kcal/mol "
            "(real docking only) or proxy score is notably better."
        ),
    )
    likely_safe_to_investigate: Optional[bool] = Field(
        default=None,
        description="True when overall_safety_flag is 'likely_safe' or 'caution'.",
    )
    clinically_worth_pursuing: Optional[bool] = Field(
        default=None,
        description="True when final_decision is 'advance' or 'conditional_advance'.",
    )
