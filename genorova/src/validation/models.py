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


class NoveltyProvenance(BaseModel):
    """Auditable record of which novelty checks ran and what each check found."""

    local_db_checked: bool = Field(
        description="True when the local Genorova database lookup was actually performed."
    )
    local_db_match_found: bool = Field(
        description="True when the local Genorova database lookup found a match."
    )
    reference_exact_match_checked: bool = Field(
        description="True when the exact-match screen against canonical reference drugs ran."
    )
    reference_exact_match_found: bool = Field(
        description="True when the exact-match reference screen found a match."
    )
    tanimoto_checked: bool = Field(
        description="True when the Tanimoto analogue screen was actually computed."
    )
    closest_reference: Optional[str] = Field(
        default=None,
        description="Closest approved reference drug identified during novelty checking.",
    )
    closest_reference_tanimoto: Optional[float] = Field(
        default=None,
        description="Tanimoto similarity to the closest approved reference drug.",
    )
    tanimoto_threshold: Optional[float] = Field(
        default=None,
        description="Canonical Tanimoto threshold used in the novelty decision.",
    )
    pubchem_checked: bool = Field(
        description="True when a PubChem lookup actually completed."
    )
    pubchem_match_found: bool = Field(
        description="True when PubChem lookup found an existing compound match."
    )
    pubchem_enabled: bool = Field(
        description="True when the caller enabled PubChem novelty lookup."
    )
    final_novelty_status: Literal["known", "uncertain", "potentially_novel"] = Field(
        description="Final outward-facing novelty status after all available checks."
    )
    final_novelty_reason: str = Field(
        description="Short plain-language reason for the final novelty status."
    )
    provenance_explanation: str = Field(
        description="Plain-language summary of which checks ran, what they found, and why the final label was assigned."
    )


class ADMETProvenance(BaseModel):
    """Auditable record of which ADMET checks ran and why the final safety label was assigned."""

    hepatotoxicity_checked: bool = Field(
        description="True when the hepatotoxicity screen actually ran."
    )
    hepatotoxicity_method: str = Field(
        description="Method used for hepatotoxicity assessment, including fallback or not-run states."
    )
    hepatotoxicity_alerts: List[str] = Field(
        default_factory=list,
        description="Matched hepatotoxicity alerts or explanatory not-run notes."
    )
    hepatotoxicity_score: Optional[float] = Field(
        default=None,
        description="Heuristic hepatotoxicity score when available."
    )
    herg_checked: bool = Field(
        description="True when the hERG screen actually ran."
    )
    herg_method: str = Field(
        description="Method used for hERG assessment, including fallback or not-run states."
    )
    herg_alerts: List[str] = Field(
        default_factory=list,
        description="Matched hERG alerts or explanatory not-run notes."
    )
    herg_score: Optional[float] = Field(
        default=None,
        description="Heuristic hERG score when available."
    )
    cyp_checked: bool = Field(
        description="True when the CYP interaction screen actually ran."
    )
    cyp_method: str = Field(
        description="Method used for CYP interaction assessment, including fallback or not-run states."
    )
    cyp_alerts: List[str] = Field(
        default_factory=list,
        description="Matched CYP interaction alerts or explanatory not-run notes."
    )
    overall_safety_method: str = Field(
        description="Canonical method used to combine the individual ADMET checks into the final safety label."
    )
    overall_safety_flag: Literal["likely_safe", "caution", "likely_unsafe", "unknown"] = Field(
        description="Final outward-facing ADMET safety label."
    )
    overall_safety_reason: str = Field(
        description="Short plain-language reason for the final safety label."
    )
    evidence_level: str = Field(
        description="Honest evidence-strength label such as heuristic proxy, regex fallback, or incomplete."
    )
    provenance_explanation: str = Field(
        description="Plain-language summary of which ADMET checks ran, what they found, and why the final safety label was assigned."
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
    status: Literal["known", "uncertain", "potentially_novel"] = Field(
        description="Stable outward-facing novelty bucket used across ranked payloads and reports."
    )

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
    exact_reference_name: Optional[str] = Field(
        default=None,
        description="Approved reference-drug name when the SMILES is an exact canonical match.",
    )
    closest_reference: Optional[str] = Field(
        default=None,
        description="Closest approved reference drug used for novelty interpretation.",
    )
    most_similar_drug: Optional[str] = Field(
        default=None,
        description="Backward-compatible alias for the closest approved reference drug.",
    )
    max_tanimoto: Optional[float] = Field(
        default=None,
        description="Tanimoto similarity score (Morgan FP, radius 2) to most similar drug.",
    )
    tanimoto_threshold: float = Field(
        description="Canonical Tanimoto threshold used to classify a known repurposing lead."
    )
    reason: str = Field(
        description="Plain-language novelty explanation for faculty and non-technical reviewers."
    )
    novelty_provenance: NoveltyProvenance = Field(
        description=(
            "Canonical novelty provenance block showing which checks ran, what each "
            "check found, and why the final novelty label was assigned."
        ),
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

class BindingProvenance(BaseModel):
    """Auditable record of which binding path ran and why the final interpretation was assigned."""

    binding_checked: bool = Field(
        description="True when a binding path actually ran or was checked to completion."
    )
    binding_state: Literal[
        "not_checked",
        "checked_unavailable",
        "attempted_failed",
        "proxy_intentional",
        "real_docking_executed",
    ] = Field(
        description=(
            "Canonical one-word summary of the binding path outcome. "
            "not_checked: path never evaluated (e.g. invalid SMILES). "
            "checked_unavailable: path ran but produced no usable score or proxy. "
            "attempted_failed: real docking attempted but runtime failed; fell back to proxy. "
            "proxy_intentional: proxy path used intentionally (no active real-docking path, or path is blocked). "
            "real_docking_executed: AutoDock Vina completed and returned a usable score."
        )
    )
    binding_mode: Literal["real_docking", "scaffold_proxy", "fallback_proxy", "unavailable"] = Field(
        description="Binding path used for the outward-facing result."
    )
    binding_mode_reason: str = Field(
        description="Plain-language reason for why this binding path was used."
    )
    real_docking_status: str = Field(
        description="ready / executed / runtime_failed / blocked / unsupported_target / not_checked_invalid_smiles"
    )
    real_docking_probe: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured readiness probe for the real docking path."
    )
    real_docking_failure: Optional[str] = Field(
        default=None,
        description="Exact blocker or runtime failure when real docking did not produce a usable result."
    )
    receptor_asset_checked: bool = Field(
        description="True when the receptor asset lookup actually ran."
    )
    receptor_asset_available: bool = Field(
        description="True when a prepared receptor asset was available."
    )
    docking_engine_checked: bool = Field(
        description="True when the docking engine import/callable check actually ran."
    )
    docking_engine_available: bool = Field(
        description="True when the docking engine was available for real docking."
    )
    comparator_name: str = Field(
        description="Reference comparator name used for the binding interpretation."
    )
    comparator_score: Optional[float] = Field(
        default=None,
        description="Comparator score used in the binding comparison."
    )
    candidate_score: Optional[float] = Field(
        default=None,
        description="Candidate binding score from real docking or proxy mode."
    )
    delta_vs_reference: Optional[float] = Field(
        default=None,
        description="Candidate minus comparator score."
    )
    key_interactions_available: bool = Field(
        description="True when key interaction residues were available from the binding path."
    )
    evidence_level: str = Field(
        description="Honest evidence-strength label for the binding stage."
    )
    final_binding_reason: str = Field(
        description="Short plain-language binding interpretation."
    )
    provenance_explanation: str = Field(
        description="Plain-language summary of which binding path ran, what blocked real docking if any, and why the final interpretation was assigned."
    )


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
    final_binding_reason: str = Field(
        default="",
        description="Stable outward-facing binding interpretation used across API and reports.",
    )
    evidence_level: str = Field(
        default="unavailable",
        description="real_docking / proxy_screening / fallback_proxy / unavailable",
    )
    binding_checked: bool = Field(
        default=False,
        description="True when a binding path actually ran or was checked to completion.",
    )
    binding_state: Literal[
        "not_checked",
        "checked_unavailable",
        "attempted_failed",
        "proxy_intentional",
        "real_docking_executed",
    ] = Field(
        default="not_checked",
        description=(
            "Canonical one-word summary of the binding path outcome — "
            "mirrors binding_provenance.binding_state for quick access without unpacking the provenance block."
        ),
    )
    binding_evidence_level: str = Field(
        default="unavailable",
        description="Honest evidence-strength label for the binding stage.",
    )
    binding_provenance: BindingProvenance = Field(
        description=(
            "Canonical binding provenance block showing which path ran, what blocked "
            "real docking if any, what comparator was used, and why the final binding "
            "interpretation was assigned."
        ),
    )
    binding_provenance_explanation: str = Field(
        default="",
        description="Faculty-facing plain-language summary of the binding provenance block.",
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
    checked: bool = Field(
        default=True,
        description=(
            "True when this ADMET check actually ran, including regex fallback mode. "
            "False when the check could not be completed."
        ),
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
    overall_safety_reason: str = Field(
        description="Plain-language explanation for why the overall safety label was assigned."
    )
    overall_safety_method: str = Field(
        description="Canonical method label for the overall safety interpretation."
    )
    admet_evidence_level: str = Field(
        description="Honest evidence-strength label for the ADMET stage."
    )
    admet_provenance: ADMETProvenance = Field(
        description=(
            "Canonical ADMET provenance block showing which safety checks ran, "
            "which were skipped, what alerts were found, and why the final safety label was assigned."
        ),
    )
    admet_provenance_explanation: str = Field(
        description="Faculty-facing plain-language summary of the ADMET provenance block."
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

class DecisionProvenance(BaseModel):
    """
    Canonical decision provenance block for the Clinical Utility stage.

    Records which comparator was used, what each evidence category contributed,
    what penalties or hard blockers applied, and why the final advancement
    label was assigned.  A faculty reviewer can use this block to audit any
    final decision without inspecting raw score internals.
    """

    decision_checked: bool = Field(
        description="True when the clinical evaluation path actually ran to completion."
    )
    final_decision: Literal["advance", "conditional_advance", "reject"] = Field(
        description="Canonical advancement verdict."
    )
    decision_score: float = Field(
        description="Composite evidence-weighted score that drove the verdict (0.0 – 1.0)."
    )
    decision_method: str = Field(
        description="Algorithm used to produce the composite score (e.g. evidence_weighted_composite_score)."
    )
    comparator_name: str = Field(
        description="Name of the reference drug used as the comparator in the composite scoring."
    )
    comparator_basis: str = Field(
        description="Plain-language description of how the comparator was used and what weights were applied."
    )
    chemistry_contribution: str = Field(
        description="Synthesizability and drug-likeness component contributions to the composite score."
    )
    binding_contribution: str = Field(
        description="Target binding component contribution, including mode and weight."
    )
    novelty_contribution: str = Field(
        description="Novelty component contribution, including flag category and weight."
    )
    admet_contribution: str = Field(
        description="Safety (ADMET) component contribution, including safety flag and weight."
    )
    ranking_penalties_applied: List[str] = Field(
        default_factory=list,
        description="Evidence-quality penalties applied by the ranking layer (e.g. proxy binding, PAINS)."
    )
    hard_gates_triggered: List[str] = Field(
        default_factory=list,
        description="Hard rejection gates that triggered (e.g. invalid SMILES, high safety risk)."
    )
    confidence_tier: Literal["high", "medium", "low"] = Field(
        description="Confidence level of the final decision: high=advance, medium=conditional, low=reject."
    )
    evidence_level: Literal["full_criteria_met", "partial_criteria_met", "criteria_not_met"] = Field(
        description="Whether evidence fully, partially, or did not meet the scoring criteria."
    )
    final_decision_reason: str = Field(
        description="Short plain-language reason for the final advancement label."
    )
    conditions: List[str] = Field(
        default_factory=list,
        description="Conditions that must be resolved before advancing (conditional_advance only)."
    )
    rejection_reasons: List[str] = Field(
        default_factory=list,
        description="Specific rejection reasons when decision is reject."
    )
    provenance_explanation: str = Field(
        description="Faculty-facing plain-language summary of the decision path."
    )


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
    decision_provenance: Optional[Any] = Field(
        default=None,
        description=(
            "Canonical decision provenance block showing which comparator was used, "
            "what each evidence category contributed, what penalties or hard blockers "
            "applied, and why the final advancement label was assigned."
        ),
    )


class FacultyExplanationSection(BaseModel):
    """One faculty-facing explanation section with explicit evidence roles."""

    summary: str = Field(
        description="Short plain-language explanation for this stage."
    )
    supporting_evidence: List[str] = Field(
        default_factory=list,
        description="Evidence in the existing provenance that supports the current interpretation."
    )
    limiting_evidence: List[str] = Field(
        default_factory=list,
        description="Evidence that weakens certainty or narrows what can honestly be claimed."
    )
    blocking_evidence: List[str] = Field(
        default_factory=list,
        description="Evidence that directly blocks a stronger claim or advancement path."
    )
    skipped_or_unavailable_checks: List[str] = Field(
        default_factory=list,
        description="Checks that were skipped, blocked, or unavailable in the active path."
    )
    provenance_pointers: "FacultyExplanationProvenancePointers" = Field(
        description=(
            "Traceable pointers back to the canonical provenance fields that drove the "
            "section summary, supporting evidence, limitations, blockers, and skipped checks."
        )
    )


class FacultyExplanationProvenancePointers(BaseModel):
    """Traceable provenance-field pointers for one faculty explanation layer."""

    summary_sources: List[str] = Field(
        default_factory=list,
        description="Exact provenance fields that support the plain-language summary."
    )
    supporting_sources: List[str] = Field(
        default_factory=list,
        description="Exact provenance fields that support the positive evidence statements."
    )
    limiting_sources: List[str] = Field(
        default_factory=list,
        description="Exact provenance fields that explain the limitations or uncertainty statements."
    )
    blocking_sources: List[str] = Field(
        default_factory=list,
        description="Exact provenance fields that support the blocking or disqualifying statements."
    )
    skipped_sources: List[str] = Field(
        default_factory=list,
        description="Exact provenance fields that show which checks were skipped or unavailable."
    )


class FacultyExplanation(BaseModel):
    """Canonical faculty-facing explanation stack shared across active outputs."""

    novelty_summary: FacultyExplanationSection = Field(
        description="Novelty explanation derived from the canonical novelty provenance."
    )
    admet_summary: FacultyExplanationSection = Field(
        description="ADMET explanation derived from the canonical ADMET provenance."
    )
    binding_summary: FacultyExplanationSection = Field(
        description="Binding explanation derived from the canonical binding provenance."
    )
    decision_summary: FacultyExplanationSection = Field(
        description="Final decision explanation derived from the canonical decision provenance."
    )
    overall_summary: str = Field(
        description="Short faculty-readable paragraph tying novelty, ADMET, binding, and the final decision into one chain."
    )
    overall_summary_provenance_pointers: FacultyExplanationProvenancePointers = Field(
        description=(
            "Traceable pointers back to the canonical provenance fields used in the overall "
            "faculty-facing summary paragraph."
        )
    )


class FacultySummaryRollup(BaseModel):
    """Compact faculty-review summary reused in compare-mode presentation payloads."""

    label: Optional[str] = Field(
        default=None,
        description="Display label for the candidate within the active compare surface."
    )
    smiles: Optional[str] = Field(
        default=None,
        description="Candidate SMILES string for direct identification in compare mode."
    )
    rank_score: Optional[float] = Field(
        default=None,
        description="Evidence-weighted comparison score used for the current ordering."
    )
    rank_label: Optional[str] = Field(
        default=None,
        description="Human-readable ranking label already assigned by the canonical ranking logic."
    )
    candidate_status: Optional[str] = Field(
        default=None,
        description="Current candidate status or final decision label."
    )
    confidence_tier: Optional[str] = Field(
        default=None,
        description="Current confidence tier carried from the canonical decision payload."
    )
    main_strengths: List[str] = Field(
        default_factory=list,
        description="Short faculty-readable strengths lifted from the canonical explanation sections."
    )
    main_limitations: List[str] = Field(
        default_factory=list,
        description="Short faculty-readable limitations lifted from the canonical explanation sections."
    )
    final_recommendation: Optional[str] = Field(
        default=None,
        description="Current recommendation label already produced by the canonical ranking logic."
    )
    overall_summary: str = Field(
        description="Top faculty-readable summary paragraph for this candidate."
    )
    overall_summary_provenance_pointers: FacultyExplanationProvenancePointers = Field(
        description="Traceability pointers backing the overall faculty summary paragraph."
    )
    decision_summary: FacultyExplanationSection = Field(
        description="Canonical final-decision section reused by summary cards and reports."
    )
    faculty_explanation: FacultyExplanation = Field(
        description="Full canonical faculty explanation stack backing this summary rollup."
    )


class ComparisonPresentationPreferredCandidate(BaseModel):
    """Identity block for the currently preferred candidate in compare mode."""

    side: Literal["left", "right"] = Field(
        description="Which side of the comparison is currently preferred."
    )
    label: Optional[str] = Field(
        default=None,
        description="Display label for the preferred candidate."
    )
    smiles: Optional[str] = Field(
        default=None,
        description="Preferred candidate SMILES string."
    )


class ComparisonPresentationSectionCandidate(BaseModel):
    """One side of a compare-mode section row."""

    label: Optional[str] = Field(
        default=None,
        description="Display label for this side of the comparison row."
    )
    smiles: Optional[str] = Field(
        default=None,
        description="Candidate SMILES string for this side of the comparison row."
    )
    is_preferred: bool = Field(
        default=False,
        description="Whether this side is the currently preferred candidate."
    )
    section: FacultyExplanationSection = Field(
        description="Canonical faculty explanation section reused directly in compare mode."
    )


class ComparisonPresentationSection(BaseModel):
    """Parallel compare-mode section row shared by UI and report output."""

    step: str = Field(description="Ordered faculty review step label.")
    title: str = Field(description="Faculty-readable section title.")
    left_candidate: ComparisonPresentationSectionCandidate = Field(
        description="Left-side section content."
    )
    right_candidate: ComparisonPresentationSectionCandidate = Field(
        description="Right-side section content."
    )


class ComparisonPresentationSections(BaseModel):
    """Named ordered comparison sections shared across active compare outputs."""

    novelty: ComparisonPresentationSection = Field(
        description="Parallel novelty comparison content."
    )
    admet: ComparisonPresentationSection = Field(
        description="Parallel ADMET comparison content."
    )
    binding: ComparisonPresentationSection = Field(
        description="Parallel binding comparison content."
    )
    final_decision: ComparisonPresentationSection = Field(
        description="Parallel final-decision comparison content."
    )


class ComparisonPresentationSectionSummaries(BaseModel):
    """Paired plain-language section summaries for both candidates, shared by UI and report."""

    novelty: str = Field(
        description="Paired plain-language novelty summary: preferred candidate then other candidate."
    )
    admet: str = Field(
        description="Paired plain-language ADMET summary: preferred candidate then other candidate."
    )
    binding: str = Field(
        description="Paired plain-language binding summary: preferred candidate then other candidate."
    )
    decision: str = Field(
        description="Paired plain-language final-decision summary: preferred candidate then other candidate."
    )


class ComparisonPresentation(BaseModel):
    """Canonical compare-mode presentation payload shared by UI and report output."""

    preferred_candidate: ComparisonPresentationPreferredCandidate = Field(
        description="Identity block for the currently preferred candidate."
    )
    preferred_reason: str = Field(
        description="Short plain-language explanation for why the preferred candidate currently leads."
    )
    confidence_limits: List[str] = Field(
        default_factory=list,
        description="Current evidence limitations that reduce confidence in the preference."
    )
    full_comparison_note: str = Field(
        description="Full canonical comparison note tying the preference back to the faculty explanation stack."
    )
    left_candidate_summary: FacultySummaryRollup = Field(
        description="Faculty-summary rollup for the left-side candidate."
    )
    right_candidate_summary: FacultySummaryRollup = Field(
        description="Faculty-summary rollup for the right-side candidate."
    )
    comparison_sections: ComparisonPresentationSections = Field(
        description="Ordered section-level comparison content reused across compare-mode outputs."
    )
    section_summaries: ComparisonPresentationSectionSummaries = Field(
        description="Paired plain-language section summaries consumed by UI and report instead of locally derived strings."
    )
    score_note: str = Field(
        description="Plain-language note on the evidence-weighted score comparison, shared by UI and report."
    )


# ---------------------------------------------------------------------------
# E.  Evidence Ledger (per-candidate scientific honesty summary)
# ---------------------------------------------------------------------------

class EvidenceLedgerBinding(BaseModel):
    """Binding sub-record in the evidence ledger."""
    mode: str = Field(description="real_docking / scaffold_proxy / fallback_proxy / unavailable")
    binding_checked: bool = Field(default=False)
    score: Optional[float] = Field(default=None)
    reference_drug: str = Field(default="unknown")
    reference_score: Optional[float] = Field(default=None)
    delta: Optional[float] = Field(default=None)
    comparator_note: str = Field(default="")
    final_binding_reason: str = Field(default="")
    evidence_level: str = Field(description="real_docking / heuristic_proxy / fallback_proxy / unavailable")
    provenance: Dict[str, Any] = Field(default_factory=dict)
    provenance_explanation: str = Field(default="")
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
    faculty_explanation: Optional[FacultyExplanation] = Field(
        default=None,
        description=(
            "Canonical faculty-facing explanation stack that reorganizes the existing "
            "novelty, ADMET, binding, and decision provenance into one readable flow."
        ),
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
    binding_checked: bool = Field(
        description="Top-level binding check status for quick review across API and report surfaces."
    )
    binding_mode: Literal["real_docking", "scaffold_proxy", "fallback_proxy", "unavailable"] = Field(
        description="Top-level binding mode for quick review across API and report surfaces."
    )
    binding_evidence_level: str = Field(
        description="Top-level evidence-strength label for the binding stage."
    )
    final_binding_reason: str = Field(
        description="Top-level plain-language binding interpretation for summaries and reports."
    )
    binding_provenance: BindingProvenance = Field(
        description=(
            "Canonical binding provenance block showing which path ran, what blocked "
            "real docking if any, what comparator was used, and why the final binding "
            "interpretation was assigned."
        ),
    )
    binding_provenance_explanation: str = Field(
        description="Faculty-facing plain-language summary of the binding provenance block."
    )
    novelty_status: Literal["known", "uncertain", "potentially_novel"] = Field(
        description="Top-level novelty bucket for quick review across API and report surfaces.",
    )
    novelty_closest_reference: Optional[str] = Field(
        default=None,
        description="Closest approved reference drug surfaced for quick faculty review.",
    )
    novelty_tanimoto_score: Optional[float] = Field(
        default=None,
        description="Tanimoto similarity to the surfaced closest approved reference drug.",
    )
    novelty_threshold: Optional[float] = Field(
        default=None,
        description="Canonical Tanimoto threshold used in the novelty classification.",
    )
    novelty_reason: str = Field(
        description="Plain-language novelty explanation surfaced in summaries and reports.",
    )
    novelty_provenance: NoveltyProvenance = Field(
        description=(
            "Canonical novelty provenance block showing which novelty checks ran, "
            "which were skipped, and why the final novelty label was assigned."
        ),
    )
    overall_safety_flag: Literal["likely_safe", "caution", "likely_unsafe", "unknown"] = Field(
        description="Top-level ADMET safety label for quick review across API and report surfaces."
    )
    overall_safety_reason: str = Field(
        description="Plain-language explanation for why the ADMET safety label was assigned."
    )
    overall_safety_method: str = Field(
        description="Canonical method label for the ADMET safety interpretation."
    )
    admet_evidence_level: str = Field(
        description="Honest evidence-strength label for the ADMET stage."
    )
    admet_provenance: ADMETProvenance = Field(
        description=(
            "Canonical ADMET provenance block showing which checks ran, which were skipped, "
            "what alerts were found, and why the final safety label was assigned."
        ),
    )
    admet_provenance_explanation: str = Field(
        description="Faculty-facing plain-language summary of the ADMET provenance block."
    )
    decision_provenance: Optional[DecisionProvenance] = Field(
        default=None,
        description=(
            "Top-level decision provenance block for quick faculty review without "
            "opening the nested clinical stage."
        ),
    )
    decision_provenance_explanation: Optional[str] = Field(
        default=None,
        description="Faculty-facing plain-language summary of the decision provenance block."
    )
    final_decision_reason: Optional[str] = Field(
        default=None,
        description="Top-level plain-language explanation for the final advancement label."
    )
    decision_confidence_tier: Optional[Literal["high", "medium", "low"]] = Field(
        default=None,
        description="Top-level confidence tier for the final decision."
    )
    decision_evidence_level: Optional[str] = Field(
        default=None,
        description="Top-level evidence-strength label for the final decision."
    )
    summary: str = Field(
        description="Canonical one-paragraph faculty-facing summary of novelty, ADMET, binding, and the final decision.",
    )
    faculty_explanation: FacultyExplanation = Field(
        description=(
            "Canonical faculty-facing explanation stack shared across top candidate "
            "payloads, full validation results, chat, and report output."
        ),
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
