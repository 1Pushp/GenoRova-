"""
Canonical science-policy helpers for the active Genorova product path.

This module standardizes the live scientific story around one active workflow:

- disease program: bacterial infection (H. pylori / antibacterial)
- target narrative: bacterial carbonic anhydrase (bCA) inhibition
- comparator strategy: acetazolamide as the canonical reference drug (Ki=6.4 nM)

It also builds a per-candidate evidence ledger so API, chat, and reporting
surfaces can present the same facts with the same caveats.
"""

from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any

# Ensure validation package is importable from anywhere
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import the canonical ranking module — the single source of truth for
# score adjustment, sort key, labels, and rationale generation.
from validation.ranking import (
    evidence_rank_score,
    sort_key        as canonical_sort_key,
    best_candidate_label,
    rank_batch,
    best_candidate_rationale,
)
from validation.chemistry.sanitizer import (
    build_novelty_evidence,
    novelty_status_from_flag,
)
from validation.admet.admet_predictor import build_admet_evidence
from validation.binding.target_binder import build_binding_evidence

ACTIVE_DISEASE = "infection"
ACTIVE_TARGET = "bca"
ACTIVE_REFERENCE_DRUG = "acetazolamide"
ACTIVE_PROGRAM_ID = "infection_bca_acetazolamide_v1"
ACTIVE_PROGRAM_LABEL = "Bacterial carbonic anhydrase (bCA) inhibitor program"
ACTIVE_PROGRAM_SUMMARY = (
    "Active Genorova lead-evaluation path: bacterial infection / "
    "H. pylori carbonic anhydrase (bCA) target / acetazolamide comparator (Ki=6.4 nM)."
)
ACTIVE_SCOPE_NOTE = (
    "The live Genorova scientific path is standardized to the bacterial carbonic anhydrase "
    "(bCA) inhibitor program. Acetazolamide (Ki=6.4 nM vs H. pylori bCA, PDB 3CYU) is the "
    "canonical reference anchor. The previous diabetes/DPP4 path is archived in archive/dpp4_legacy/."
)

COMPUTED_FIELD_NAMES = [
    "SMILES validity",
    "molecular weight",
    "LogP",
    "QED",
    "SA score",
    "Lipinski pass/fail",
    "PAINS check",
]

HEURISTIC_FIELD_NAMES = [
    "novelty status without PubChem confirmation",
    "binding proxy or docking fallback mode",
    "hepatotoxicity risk",
    "hERG risk",
    "CYP interaction risk",
    "ADMET provenance explanation",
    "final decision score",
]

DECISION_PRIORITY = {
    "advance": 2,
    "conditional_advance": 1,
    "reject": 0,
}

CONFIDENCE_PRIORITY = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


@dataclass(frozen=True)
class CandidateConfidence:
    level: str
    evidence_level: str
    note: str


def _normalize_sentence(text: Any, fallback: str) -> str:
    """Return a clean sentence with conservative fallback text."""
    value = str(text or "").strip()
    if not value:
        value = fallback
    if value.endswith((".", "!", "?")):
        return value
    return f"{value}."


def _metric_text(value: Any, digits: int = 2) -> str:
    """Render a numeric metric for faculty-facing summaries."""
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return "not available"


def _pretty_label(value: Any) -> str:
    """Render compact enum-like labels as plain faculty-readable text."""
    text = str(value or "").strip()
    if not text:
        return "not available"
    return text.replace("_", " ")


def _dedupe_messages(messages: list[str]) -> list[str]:
    """Preserve message order while removing blank or duplicate entries."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for message in messages:
        raw = str(message or "").strip()
        if not raw:
            continue
        normalized = raw if raw.endswith((".", "!", "?")) else f"{raw}."
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _dedupe_pointers(paths: list[str]) -> list[str]:
    """Preserve pointer order while removing blanks and duplicates."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for path in paths:
        value = str(path or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def _pointer_fields(block: str, *fields: str) -> list[str]:
    """Build canonical provenance-field pointers for audit-friendly output."""
    return [f"{block}.{field}" for field in fields if str(field or "").strip()]


def _pointer_bundle(
    *,
    summary_sources: list[str] | None = None,
    supporting_sources: list[str] | None = None,
    limiting_sources: list[str] | None = None,
    blocking_sources: list[str] | None = None,
    skipped_sources: list[str] | None = None,
) -> dict[str, list[str]]:
    """Return one normalized provenance-pointer bundle."""
    return {
        "summary_sources": _dedupe_pointers(list(summary_sources or [])),
        "supporting_sources": _dedupe_pointers(list(supporting_sources or [])),
        "limiting_sources": _dedupe_pointers(list(limiting_sources or [])),
        "blocking_sources": _dedupe_pointers(list(blocking_sources or [])),
        "skipped_sources": _dedupe_pointers(list(skipped_sources or [])),
    }


def _has_pointer_bundle(bundle: Any) -> bool:
    """Check whether a provenance-pointer bundle has the expected fields."""
    return isinstance(bundle, dict) and {
        "summary_sources",
        "supporting_sources",
        "limiting_sources",
        "blocking_sources",
        "skipped_sources",
    }.issubset(bundle.keys())


def _faculty_section_has_traceability(section: Any) -> bool:
    """Return True when a faculty explanation section already includes pointers."""
    return isinstance(section, dict) and {
        "summary",
        "supporting_evidence",
        "limiting_evidence",
        "blocking_evidence",
        "skipped_or_unavailable_checks",
        "provenance_pointers",
    }.issubset(section.keys()) and _has_pointer_bundle(section.get("provenance_pointers"))


def _faculty_explanation_has_traceability(explanation: Any) -> bool:
    """Return True when an explanation stack already contains the Day 11 shape."""
    return isinstance(explanation, dict) and {
        "novelty_summary",
        "admet_summary",
        "binding_summary",
        "decision_summary",
        "overall_summary",
        "overall_summary_provenance_pointers",
    }.issubset(explanation.keys()) and all(
        _faculty_section_has_traceability(explanation.get(key))
        for key in (
            "novelty_summary",
            "admet_summary",
            "binding_summary",
            "decision_summary",
        )
    ) and _has_pointer_bundle(explanation.get("overall_summary_provenance_pointers"))


def _section_pointer_bundle(section: dict[str, Any]) -> dict[str, list[str]]:
    """Read the pointer bundle from a section, or return an empty normalized one."""
    if not _faculty_section_has_traceability(section):
        return _pointer_bundle()
    return _pointer_bundle(
        summary_sources=section["provenance_pointers"].get("summary_sources"),
        supporting_sources=section["provenance_pointers"].get("supporting_sources"),
        limiting_sources=section["provenance_pointers"].get("limiting_sources"),
        blocking_sources=section["provenance_pointers"].get("blocking_sources"),
        skipped_sources=section["provenance_pointers"].get("skipped_sources"),
    )


def _faculty_section(
    summary: Any,
    *,
    fallback: str,
    supporting: list[str] | None = None,
    limiting: list[str] | None = None,
    blocking: list[str] | None = None,
    skipped: list[str] | None = None,
    summary_sources: list[str] | None = None,
    supporting_sources: list[str] | None = None,
    limiting_sources: list[str] | None = None,
    blocking_sources: list[str] | None = None,
    skipped_sources: list[str] | None = None,
) -> dict[str, Any]:
    """Build one canonical faculty explanation section."""
    return {
        "summary": _normalize_sentence(summary, fallback),
        "supporting_evidence": _dedupe_messages(list(supporting or [])),
        "limiting_evidence": _dedupe_messages(list(limiting or [])),
        "blocking_evidence": _dedupe_messages(list(blocking or [])),
        "skipped_or_unavailable_checks": _dedupe_messages(list(skipped or [])),
        "provenance_pointers": _pointer_bundle(
            summary_sources=summary_sources,
            supporting_sources=supporting_sources,
            limiting_sources=limiting_sources,
            blocking_sources=blocking_sources,
            skipped_sources=skipped_sources,
        ),
    }


def _build_novelty_faculty_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize novelty evidence without inventing new scientific claims."""
    provenance = dict(payload.get("novelty_provenance") or {})
    novelty_status = str(payload.get("novelty_status") or provenance.get("final_novelty_status") or "uncertain")
    closest_reference = (
        payload.get("novelty_closest_reference")
        or provenance.get("closest_reference")
    )
    tanimoto_score = payload.get("novelty_tanimoto_score")
    if tanimoto_score is None:
        tanimoto_score = provenance.get("closest_reference_tanimoto")
    threshold = payload.get("novelty_threshold")
    if threshold is None:
        threshold = provenance.get("tanimoto_threshold")

    supporting: list[str] = []
    limiting: list[str] = []
    blocking: list[str] = []
    skipped: list[str] = []
    summary_sources = _pointer_fields(
        "novelty_provenance",
        "final_novelty_status",
        "final_novelty_reason",
        "provenance_explanation",
    )
    supporting_sources: list[str] = []
    limiting_sources: list[str] = []
    blocking_sources: list[str] = []
    skipped_sources: list[str] = []

    if provenance.get("local_db_checked"):
        if provenance.get("local_db_match_found"):
            blocking.append("Local database lookup found a match.")
            blocking_sources.extend(
                _pointer_fields("novelty_provenance", "local_db_checked", "local_db_match_found")
            )
        else:
            supporting.append("Local database lookup found no match.")
            supporting_sources.extend(
                _pointer_fields("novelty_provenance", "local_db_checked", "local_db_match_found")
            )
    else:
        skipped.append("Local database lookup did not run.")
        skipped_sources.extend(_pointer_fields("novelty_provenance", "local_db_checked"))

    if provenance.get("reference_exact_match_checked"):
        if provenance.get("reference_exact_match_found"):
            blocking.append("Reference exact-match screen found an approved-drug match.")
            blocking_sources.extend(
                _pointer_fields(
                    "novelty_provenance",
                    "reference_exact_match_checked",
                    "reference_exact_match_found",
                )
            )
        else:
            supporting.append("Reference exact-match screen found no approved-drug match.")
            supporting_sources.extend(
                _pointer_fields(
                    "novelty_provenance",
                    "reference_exact_match_checked",
                    "reference_exact_match_found",
                )
            )
    else:
        skipped.append("Reference exact-match screen did not run.")
        skipped_sources.extend(_pointer_fields("novelty_provenance", "reference_exact_match_checked"))

    if provenance.get("tanimoto_checked"):
        tanimoto_sources = _pointer_fields(
            "novelty_provenance",
            "tanimoto_checked",
            "closest_reference",
            "closest_reference_tanimoto",
            "tanimoto_threshold",
        )
        if closest_reference and tanimoto_score is not None and threshold is not None:
            analogue_note = (
                f"Closest approved reference was {closest_reference} at Tanimoto "
                f"{_metric_text(tanimoto_score)} against a threshold of {_metric_text(threshold)}"
            )
            if float(tanimoto_score) >= float(threshold):
                blocking.append(analogue_note)
                blocking_sources.extend(tanimoto_sources)
            elif novelty_status == "potentially_novel":
                supporting.append(analogue_note)
                supporting_sources.extend(tanimoto_sources)
            else:
                limiting.append(analogue_note)
                limiting_sources.extend(tanimoto_sources)
        else:
            limiting.append("Analogue similarity was checked, but the closest-reference details were incomplete.")
            limiting_sources.extend(tanimoto_sources)
    else:
        skipped.append("Tanimoto analogue check did not run.")
        skipped_sources.extend(_pointer_fields("novelty_provenance", "tanimoto_checked"))

    if provenance.get("pubchem_enabled"):
        if provenance.get("pubchem_checked"):
            pubchem_sources = _pointer_fields(
                "novelty_provenance",
                "pubchem_enabled",
                "pubchem_checked",
                "pubchem_match_found",
            )
            if provenance.get("pubchem_match_found"):
                blocking.append("PubChem lookup found an existing compound match.")
                blocking_sources.extend(pubchem_sources)
            else:
                supporting.append("PubChem lookup found no match.")
                supporting_sources.extend(pubchem_sources)
        else:
            skipped.append("PubChem lookup was enabled but did not complete.")
            skipped_sources.extend(
                _pointer_fields("novelty_provenance", "pubchem_enabled", "pubchem_checked")
            )
    else:
        skipped.append("PubChem lookup was not enabled in this run.")
        skipped_sources.extend(_pointer_fields("novelty_provenance", "pubchem_enabled"))

    if novelty_status == "known":
        blocking.append("The active novelty path classifies this molecule as known or repurposing.")
        blocking_sources.extend(
            _pointer_fields("novelty_provenance", "final_novelty_status", "final_novelty_reason")
        )
    elif novelty_status == "uncertain":
        limiting.append("The active novelty path still treats novelty as uncertain.")
        limiting_sources.extend(
            _pointer_fields("novelty_provenance", "final_novelty_status", "final_novelty_reason")
        )
    elif novelty_status == "potentially_novel":
        supporting.append("The active novelty path did not find evidence strong enough to classify this molecule as known.")
        supporting_sources.extend(
            _pointer_fields("novelty_provenance", "final_novelty_status", "final_novelty_reason")
        )

    return _faculty_section(
        payload.get("novelty_reason"),
        fallback="Novelty explanation is not available.",
        supporting=supporting,
        limiting=limiting,
        blocking=blocking,
        skipped=skipped,
        summary_sources=summary_sources,
        supporting_sources=supporting_sources,
        limiting_sources=limiting_sources,
        blocking_sources=blocking_sources,
        skipped_sources=skipped_sources,
    )


def _build_admet_faculty_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize ADMET evidence roles from the canonical provenance block."""
    provenance = dict(payload.get("admet_provenance") or {})
    overall_flag = str(
        payload.get("overall_safety_flag")
        or provenance.get("overall_safety_flag")
        or "unknown"
    )
    evidence_level = str(
        payload.get("admet_evidence_level")
        or provenance.get("evidence_level")
        or ""
    )

    supporting: list[str] = []
    limiting: list[str] = []
    blocking: list[str] = []
    skipped: list[str] = []
    summary_sources = _pointer_fields(
        "admet_provenance",
        "overall_safety_flag",
        "overall_safety_reason",
        "evidence_level",
        "provenance_explanation",
    )
    supporting_sources: list[str] = []
    limiting_sources: list[str] = []
    blocking_sources: list[str] = []
    skipped_sources: list[str] = []

    def _record_check(
        label: str,
        checked: Any,
        check_flag: str,
        alert_field: str,
        score_field: str,
    ) -> None:
        sources = _pointer_fields("admet_provenance", check_flag, alert_field, score_field)
        if checked is False:
            skipped.append(f"{label} check did not run.")
            skipped_sources.extend(_pointer_fields("admet_provenance", check_flag))
            return
        if checked is not True:
            return

        alert_list = [
            str(alert).strip()
            for alert in list(provenance.get(alert_field) or [])
            if str(alert).strip()
        ]
        score_value = provenance.get(score_field)
        score_suffix = f" Score: {_metric_text(score_value)}." if score_value is not None else ""
        if alert_list:
            limiting.append(f"{label} check ran and raised alert(s): {', '.join(alert_list[:2])}.{score_suffix}")
            limiting_sources.extend(sources)
        else:
            supporting.append(f"{label} check ran without recorded alerts.{score_suffix}")
            supporting_sources.extend(sources)

    _record_check(
        "Hepatotoxicity",
        provenance.get("hepatotoxicity_checked"),
        "hepatotoxicity_checked",
        "hepatotoxicity_alerts",
        "hepatotoxicity_score",
    )
    _record_check(
        "hERG",
        provenance.get("herg_checked"),
        "herg_checked",
        "herg_alerts",
        "herg_score",
    )
    _record_check(
        "CYP interaction",
        provenance.get("cyp_checked"),
        "cyp_checked",
        "cyp_alerts",
        "",
    )

    if overall_flag == "likely_safe":
        supporting.append("The overall ADMET screen stayed in the likely safe bucket.")
        supporting_sources.extend(
            _pointer_fields("admet_provenance", "overall_safety_flag", "overall_safety_reason")
        )
    elif overall_flag == "caution":
        limiting.append("The overall ADMET screen stayed in the caution bucket.")
        limiting_sources.extend(
            _pointer_fields("admet_provenance", "overall_safety_flag", "overall_safety_reason")
        )
    elif overall_flag == "likely_unsafe":
        blocking.append("The overall ADMET screen classified the molecule as likely unsafe.")
        blocking_sources.extend(
            _pointer_fields("admet_provenance", "overall_safety_flag", "overall_safety_reason")
        )
    else:
        limiting.append("The overall ADMET screen remains inconclusive.")
        limiting_sources.extend(
            _pointer_fields("admet_provenance", "overall_safety_flag", "overall_safety_reason")
        )

    if "incomplete" in evidence_level:
        limiting.append("ADMET evidence is incomplete in the active path.")
        limiting_sources.extend(_pointer_fields("admet_provenance", "evidence_level"))
    if "heuristic" in evidence_level or "proxy" in evidence_level:
        limiting.append("ADMET evidence is heuristic screening evidence, not experimental safety data.")
        limiting_sources.extend(_pointer_fields("admet_provenance", "evidence_level", "overall_safety_method"))
    if "regex_fallback" in evidence_level:
        limiting.append("Some ADMET checks relied on regex fallback alerts instead of descriptor-backed screening.")
        limiting_sources.extend(_pointer_fields("admet_provenance", "evidence_level"))

    return _faculty_section(
        payload.get("overall_safety_reason"),
        fallback="ADMET explanation is not available.",
        supporting=supporting,
        limiting=limiting,
        blocking=blocking,
        skipped=skipped,
        summary_sources=summary_sources,
        supporting_sources=supporting_sources,
        limiting_sources=limiting_sources,
        blocking_sources=blocking_sources,
        skipped_sources=skipped_sources,
    )


def _build_binding_faculty_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize binding evidence roles from the canonical provenance block."""
    provenance = dict(payload.get("binding_provenance") or {})
    binding_checked = payload.get("binding_checked")
    if binding_checked is None:
        binding_checked = provenance.get("binding_checked")
    binding_state = str(payload.get("binding_state") or provenance.get("binding_state") or "not_checked")
    binding_mode = str(
        payload.get("binding_mode")
        or provenance.get("binding_mode")
        or payload.get("docking_mode")
        or "unavailable"
    )
    comparator_name = str(payload.get("reference_drug") or provenance.get("comparator_name") or "the comparator")
    candidate_score = provenance.get("candidate_score", payload.get("binding_score"))
    comparator_score = provenance.get("comparator_score", payload.get("reference_score"))
    delta = provenance.get("delta_vs_reference", payload.get("delta_vs_reference"))
    real_docking_status = str(
        payload.get("real_docking_status")
        or provenance.get("real_docking_status")
        or ""
    )

    supporting: list[str] = []
    limiting: list[str] = []
    blocking: list[str] = []
    skipped: list[str] = []
    summary_sources = _pointer_fields(
        "binding_provenance",
        "binding_state",
        "binding_mode",
        "final_binding_reason",
        "provenance_explanation",
    )
    supporting_sources: list[str] = []
    limiting_sources: list[str] = []
    blocking_sources: list[str] = []
    skipped_sources: list[str] = []

    if binding_checked is True:
        supporting.append("The active binding path produced a usable result.")
        supporting_sources.extend(_pointer_fields("binding_provenance", "binding_checked", "binding_state"))
    elif binding_state == "not_checked":
        skipped.append("Binding was not checked in the active path.")
        skipped_sources.extend(_pointer_fields("binding_provenance", "binding_checked", "binding_state"))
    else:
        blocking.append("The active binding path did not return a usable binding result.")
        blocking_sources.extend(_pointer_fields("binding_provenance", "binding_checked", "binding_state"))

    if binding_mode == "real_docking":
        supporting.append("Binding evidence comes from a completed real docking run.")
        supporting_sources.extend(_pointer_fields("binding_provenance", "binding_mode", "real_docking_status"))
    elif binding_mode == "scaffold_proxy":
        limiting.append("Binding evidence comes from a scaffold proxy rather than a completed docking run.")
        limiting_sources.extend(_pointer_fields("binding_provenance", "binding_mode", "binding_mode_reason"))
    elif binding_mode == "fallback_proxy":
        limiting.append("Binding evidence comes from a fallback proxy because the real docking path was blocked or failed.")
        limiting_sources.extend(
            _pointer_fields(
                "binding_provenance",
                "binding_mode",
                "binding_mode_reason",
                "real_docking_status",
                "real_docking_failure",
            )
        )
    else:
        blocking.append("No binding estimate is available for this candidate.")
        blocking_sources.extend(_pointer_fields("binding_provenance", "binding_mode", "binding_state"))

    if candidate_score is not None and comparator_score is not None and delta is not None:
        comparison_note = (
            f"Candidate score was {_metric_text(candidate_score)} versus "
            f"{comparator_name} {_metric_text(comparator_score)} (delta {float(delta):+.2f})"
        )
        comparison_sources = _pointer_fields(
            "binding_provenance",
            "comparator_name",
            "candidate_score",
            "comparator_score",
            "delta_vs_reference",
        )
        if binding_mode == "real_docking" and float(delta) <= 0:
            supporting.append(comparison_note)
            supporting_sources.extend(comparison_sources)
        else:
            limiting.append(comparison_note)
            limiting_sources.extend(comparison_sources)
    elif candidate_score is not None:
        limiting.append(f"Candidate binding score was {_metric_text(candidate_score)}.")
        limiting_sources.extend(_pointer_fields("binding_provenance", "candidate_score"))

    if provenance.get("real_docking_failure"):
        skipped.append(f"Real docking did not produce a usable result: {provenance['real_docking_failure']}.")
        skipped_sources.extend(
            _pointer_fields("binding_provenance", "real_docking_status", "real_docking_failure")
        )
    elif real_docking_status in {"blocked", "unsupported_target"}:
        skipped.append(f"Real docking was unavailable in this run ({real_docking_status.replace('_', ' ')}).")
        skipped_sources.extend(_pointer_fields("binding_provenance", "real_docking_status"))

    if provenance.get("receptor_asset_checked") and not provenance.get("receptor_asset_available"):
        skipped.append("A prepared receptor asset was not available.")
        skipped_sources.extend(
            _pointer_fields("binding_provenance", "receptor_asset_checked", "receptor_asset_available")
        )
    if provenance.get("docking_engine_checked") and not provenance.get("docking_engine_available"):
        skipped.append("A usable docking engine was not available.")
        skipped_sources.extend(
            _pointer_fields("binding_provenance", "docking_engine_checked", "docking_engine_available")
        )
    if provenance.get("key_interactions_available") is False:
        skipped.append("Key interaction residues were not available from the active binding path.")
        skipped_sources.extend(_pointer_fields("binding_provenance", "key_interactions_available"))

    return _faculty_section(
        payload.get("final_binding_reason"),
        fallback="Binding explanation is not available.",
        supporting=supporting,
        limiting=limiting,
        blocking=blocking,
        skipped=skipped,
        summary_sources=summary_sources,
        supporting_sources=supporting_sources,
        limiting_sources=limiting_sources,
        blocking_sources=blocking_sources,
        skipped_sources=skipped_sources,
    )


def _build_decision_faculty_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize the final decision from the canonical decision provenance block."""
    provenance = dict(payload.get("decision_provenance") or {})
    final_decision = str(payload.get("final_decision") or provenance.get("final_decision") or "reject")
    decision_score = payload.get("decision_score", provenance.get("decision_score"))
    confidence_tier = str(
        payload.get("decision_confidence_tier")
        or provenance.get("confidence_tier")
        or ""
    )
    evidence_level = str(
        payload.get("decision_evidence_level")
        or provenance.get("evidence_level")
        or ""
    )
    conditions = list(provenance.get("conditions") or [])
    rejection_reasons = list(provenance.get("rejection_reasons") or [])
    hard_gates = list(provenance.get("hard_gates_triggered") or [])
    ranking_penalties = list(provenance.get("ranking_penalties_applied") or [])

    supporting: list[str] = []
    limiting: list[str] = []
    blocking: list[str] = []
    skipped: list[str] = []
    summary_sources = _pointer_fields(
        "decision_provenance",
        "final_decision",
        "decision_score",
        "final_decision_reason",
        "provenance_explanation",
    )
    supporting_sources: list[str] = []
    limiting_sources: list[str] = []
    blocking_sources: list[str] = []
    skipped_sources: list[str] = []

    if provenance.get("decision_checked") is False:
        skipped.append("The final decision path did not complete.")
        skipped_sources.extend(_pointer_fields("decision_provenance", "decision_checked"))

    if decision_score is not None:
        score_text = f"Composite decision score was {_metric_text(decision_score)} / 1.00"
        decision_score_sources = _pointer_fields(
            "decision_provenance",
            "final_decision",
            "decision_score",
            "final_decision_reason",
        )
        if final_decision == "advance":
            supporting.append(f"{score_text} and the candidate met the advance criteria.")
            supporting_sources.extend(decision_score_sources)
        elif final_decision == "conditional_advance":
            supporting.append(f"{score_text} and the candidate remained conditionally advanceable.")
            supporting_sources.extend(decision_score_sources)
        else:
            blocking.append(f"{score_text} and the candidate did not meet the decision threshold.")
            blocking_sources.extend(decision_score_sources)

    if final_decision == "advance" and not hard_gates:
        supporting.append("No hard rejection gates were reported in the final decision path.")
        supporting_sources.extend(_pointer_fields("decision_provenance", "hard_gates_triggered"))
    if final_decision == "conditional_advance":
        limiting.extend(conditions)
        if conditions:
            limiting_sources.extend(_pointer_fields("decision_provenance", "conditions"))
    if final_decision == "reject":
        blocking.extend(rejection_reasons)
        if rejection_reasons:
            blocking_sources.extend(_pointer_fields("decision_provenance", "rejection_reasons"))

    blocking.extend(hard_gates)
    if hard_gates:
        blocking_sources.extend(_pointer_fields("decision_provenance", "hard_gates_triggered"))
    limiting.extend(f"Ranking penalty applied: {penalty}" for penalty in ranking_penalties)
    if ranking_penalties:
        limiting_sources.extend(_pointer_fields("decision_provenance", "ranking_penalties_applied"))

    if confidence_tier == "medium":
        limiting.append("Final decision confidence is medium.")
        limiting_sources.extend(_pointer_fields("decision_provenance", "confidence_tier"))
    elif confidence_tier == "low":
        limiting.append("Final decision confidence is low.")
        limiting_sources.extend(_pointer_fields("decision_provenance", "confidence_tier"))

    if evidence_level and evidence_level != "full_criteria_met":
        limiting.append(f"Decision evidence level is {evidence_level.replace('_', ' ')}.")
        limiting_sources.extend(_pointer_fields("decision_provenance", "evidence_level"))

    return _faculty_section(
        payload.get("final_decision_reason") or provenance.get("provenance_explanation"),
        fallback="Final decision explanation is not available.",
        supporting=supporting,
        limiting=limiting,
        blocking=blocking,
        skipped=skipped,
        summary_sources=summary_sources,
        supporting_sources=supporting_sources,
        limiting_sources=limiting_sources,
        blocking_sources=blocking_sources,
        skipped_sources=skipped_sources,
    )


def build_faculty_explanation_stack(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Build one canonical faculty-facing explanation stack from existing provenance.

    The builder only reorganizes already-computed novelty, ADMET, binding, and
    decision evidence. It does not create new scientific logic.
    """
    existing = payload.get("faculty_explanation")
    if _faculty_explanation_has_traceability(existing):
        return existing

    novelty_summary = _build_novelty_faculty_section(payload)
    admet_summary = _build_admet_faculty_section(payload)
    binding_summary = _build_binding_faculty_section(payload)
    decision_summary = _build_decision_faculty_section(payload)
    overall_summary = _normalize_sentence(
        " ".join(
            [
                f"Novelty: {novelty_summary['summary']}",
                f"ADMET: {admet_summary['summary']}",
                f"Binding: {binding_summary['summary']}",
                f"Decision: {decision_summary['summary']}",
                "This remains a computational screening result rather than experimental proof.",
            ]
        ),
        "Overall faculty explanation is not available.",
    )
    novelty_pointers = _section_pointer_bundle(novelty_summary)
    admet_pointers = _section_pointer_bundle(admet_summary)
    binding_pointers = _section_pointer_bundle(binding_summary)
    decision_pointers = _section_pointer_bundle(decision_summary)
    overall_summary_provenance_pointers = _pointer_bundle(
        summary_sources=[
            *novelty_pointers["summary_sources"],
            *admet_pointers["summary_sources"],
            *binding_pointers["summary_sources"],
            *decision_pointers["summary_sources"],
        ],
        supporting_sources=[
            *novelty_pointers["supporting_sources"],
            *admet_pointers["supporting_sources"],
            *binding_pointers["supporting_sources"],
            *decision_pointers["supporting_sources"],
        ],
        limiting_sources=[
            *novelty_pointers["limiting_sources"],
            *admet_pointers["limiting_sources"],
            *binding_pointers["limiting_sources"],
            *decision_pointers["limiting_sources"],
        ],
        blocking_sources=[
            *novelty_pointers["blocking_sources"],
            *admet_pointers["blocking_sources"],
            *binding_pointers["blocking_sources"],
            *decision_pointers["blocking_sources"],
        ],
        skipped_sources=[
            *novelty_pointers["skipped_sources"],
            *admet_pointers["skipped_sources"],
            *binding_pointers["skipped_sources"],
            *decision_pointers["skipped_sources"],
        ],
    )

    return {
        "novelty_summary": novelty_summary,
        "admet_summary": admet_summary,
        "binding_summary": binding_summary,
        "decision_summary": decision_summary,
        "overall_summary": overall_summary,
        "overall_summary_provenance_pointers": overall_summary_provenance_pointers,
    }


def _clean_text_items(items: Any) -> list[str]:
    """Return a stable list of non-empty text items for presentation payloads."""
    if isinstance(items, list):
        source = items
    elif items in (None, ""):
        source = []
    else:
        source = [items]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in source:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _collect_faculty_highlights(
    faculty_explanation: dict[str, Any],
    keys: tuple[str, ...],
    *,
    limit: int = 3,
) -> list[str]:
    """Collect a few unique evidence lines in the canonical faculty section order."""
    highlights: list[str] = []
    seen: set[str] = set()
    for section_key in ("novelty_summary", "admet_summary", "binding_summary", "decision_summary"):
        section = faculty_explanation.get(section_key) or {}
        for key in keys:
            for item in _clean_text_items(section.get(key)):
                if item in seen:
                    continue
                seen.add(item)
                highlights.append(item)
                if len(highlights) >= limit:
                    return highlights
    return highlights


def _placeholder_faculty_item(item: Any) -> bool:
    """Identify rollup fallback lines so conclusions can favor real evidence."""
    text = str(item or "").strip()
    return text.startswith("No clear supporting evidence") or text.startswith(
        "No explicit limiting or blocking checks"
    )


def _comparison_rank(candidate: dict[str, Any]) -> float:
    """Return the evidence-weighted score used in compare-mode ordering."""
    return float(candidate.get("rank_score") or candidate.get("clinical_score") or 0.0)


def _faculty_explanation_path(explanation: dict[str, Any]) -> str:
    """Render the canonical explanation stack as one readable sentence chain."""
    return (
        f"Novelty: {(explanation.get('novelty_summary') or {}).get('summary', 'Not available.')} "
        f"ADMET: {(explanation.get('admet_summary') or {}).get('summary', 'Not available.')} "
        f"Binding: {(explanation.get('binding_summary') or {}).get('summary', 'Not available.')} "
        f"Decision: {(explanation.get('decision_summary') or {}).get('summary', 'Not available.')}"
    )


def build_faculty_summary_rollup(
    payload: dict[str, Any],
    *,
    label: str | None = None,
) -> dict[str, Any]:
    """
    Build one reusable faculty-summary rollup from the canonical explanation stack.

    This only reorganizes existing candidate and faculty explanation fields into a
    compact presentation payload. It does not add new scientific logic.
    """
    explanation = build_faculty_explanation_stack(payload)
    strengths = _collect_faculty_highlights(explanation, ("supporting_evidence",))
    limitations = _collect_faculty_highlights(
        explanation,
        ("blocking_evidence", "limiting_evidence", "skipped_or_unavailable_checks"),
    )

    return {
        "label": label or payload.get("label"),
        "smiles": payload.get("smiles"),
        "rank_score": payload.get("rank_score") or payload.get("clinical_score"),
        "rank_label": payload.get("rank_label") or payload.get("recommendation"),
        "candidate_status": payload.get("final_decision") or payload.get("validation_status"),
        "confidence_tier": (
            payload.get("decision_confidence_tier")
            or payload.get("confidence_level")
            or ((payload.get("decision_provenance") or {}).get("confidence_tier"))
        ),
        "main_strengths": strengths
        or ["No clear supporting evidence was highlighted in the current explanation stack."],
        "main_limitations": limitations
        or ["No explicit limiting or blocking checks were highlighted in the current explanation stack."],
        "final_recommendation": (
            payload.get("rank_label")
            or payload.get("recommendation")
            or payload.get("final_decision")
        ),
        "overall_summary": (
            explanation.get("overall_summary")
            or payload.get("summary")
            or "No overall faculty summary is available."
        ),
        "overall_summary_provenance_pointers": (
            explanation.get("overall_summary_provenance_pointers") or _pointer_bundle()
        ),
        "decision_summary": explanation.get("decision_summary")
        or _faculty_section(
            "",
            fallback="Final decision explanation is not available.",
        ),
        "faculty_explanation": explanation,
    }


def build_comparison_presentation(
    left_candidate: dict[str, Any],
    right_candidate: dict[str, Any],
    *,
    left_label: str = "Molecule A",
    right_label: str = "Molecule B",
) -> dict[str, Any]:
    """
    Build one canonical compare-mode presentation payload for UI and report output.

    The payload carries the plain-language comparison conclusion, per-candidate
    faculty summary rollups, and the ordered section-level content reused by both
    active compare surfaces.
    """
    left_summary = build_faculty_summary_rollup(left_candidate, label=left_label)
    right_summary = build_faculty_summary_rollup(right_candidate, label=right_label)
    left_explanation = left_summary["faculty_explanation"]
    right_explanation = right_summary["faculty_explanation"]

    left_score = _comparison_rank(left_candidate)
    right_score = _comparison_rank(right_candidate)
    left_is_preferred = left_score >= right_score
    preferred_summary = left_summary if left_is_preferred else right_summary
    other_summary = right_summary if left_is_preferred else left_summary
    preferred_candidate = left_candidate if left_is_preferred else right_candidate
    other_candidate = right_candidate if left_is_preferred else left_candidate

    reasons: list[str] = [
        (
            f"{preferred_summary['label'] or 'Preferred candidate'} has the higher evidence-weighted score "
            f"({_comparison_rank(preferred_candidate):.4f} vs {_comparison_rank(other_candidate):.4f})."
        )
    ]
    if preferred_summary.get("candidate_status") and other_summary.get("candidate_status"):
        reasons.append(
            "Current final decisions are "
            f"{_pretty_label(preferred_summary['candidate_status'])} versus {_pretty_label(other_summary['candidate_status'])}."
        )
    top_strength = next(
        (
            item
            for item in _clean_text_items(preferred_summary.get("main_strengths"))
            if not _placeholder_faculty_item(item)
        ),
        "",
    )
    if top_strength:
        reasons.append(f"Key favorable point: {top_strength}")

    confidence_limits = [
        item
        for item in _clean_text_items(
            [
                *_clean_text_items(preferred_summary.get("main_limitations")),
                *_clean_text_items(other_summary.get("main_limitations")),
            ]
        )
        if not _placeholder_faculty_item(item)
    ][:2]
    if not confidence_limits:
        confidence_limits = [
            "Current preference remains limited by the available screening evidence rather than experimental confirmation."
        ]

    comparison_sections = {
        "novelty": {
            "step": "Step 2",
            "title": "Novelty",
            "left_candidate": {
                "label": left_summary.get("label"),
                "smiles": left_summary.get("smiles"),
                "is_preferred": left_is_preferred,
                "section": left_explanation.get("novelty_summary") or {},
            },
            "right_candidate": {
                "label": right_summary.get("label"),
                "smiles": right_summary.get("smiles"),
                "is_preferred": not left_is_preferred,
                "section": right_explanation.get("novelty_summary") or {},
            },
        },
        "admet": {
            "step": "Step 3",
            "title": "ADMET",
            "left_candidate": {
                "label": left_summary.get("label"),
                "smiles": left_summary.get("smiles"),
                "is_preferred": left_is_preferred,
                "section": left_explanation.get("admet_summary") or {},
            },
            "right_candidate": {
                "label": right_summary.get("label"),
                "smiles": right_summary.get("smiles"),
                "is_preferred": not left_is_preferred,
                "section": right_explanation.get("admet_summary") or {},
            },
        },
        "binding": {
            "step": "Step 4",
            "title": "Binding",
            "left_candidate": {
                "label": left_summary.get("label"),
                "smiles": left_summary.get("smiles"),
                "is_preferred": left_is_preferred,
                "section": left_explanation.get("binding_summary") or {},
            },
            "right_candidate": {
                "label": right_summary.get("label"),
                "smiles": right_summary.get("smiles"),
                "is_preferred": not left_is_preferred,
                "section": right_explanation.get("binding_summary") or {},
            },
        },
        "final_decision": {
            "step": "Step 5",
            "title": "Final Decision",
            "left_candidate": {
                "label": left_summary.get("label"),
                "smiles": left_summary.get("smiles"),
                "is_preferred": left_is_preferred,
                "section": left_explanation.get("decision_summary") or {},
            },
            "right_candidate": {
                "label": right_summary.get("label"),
                "smiles": right_summary.get("smiles"),
                "is_preferred": not left_is_preferred,
                "section": right_explanation.get("decision_summary") or {},
            },
        },
    }

    pref_exp = preferred_summary["faculty_explanation"]
    other_exp = other_summary["faculty_explanation"]
    pref_name = preferred_summary.get("label") or "Preferred candidate"
    other_name = other_summary.get("label") or "Other candidate"

    def _paired(section_key: str, display: str) -> str:
        pref_text = (pref_exp.get(section_key) or {}).get("summary") or "Not available."
        other_text = (other_exp.get(section_key) or {}).get("summary") or "Not available."
        return f"{pref_name} {display}: {pref_text} {other_name} {display}: {other_text}"

    pref_rank_label = preferred_summary.get("rank_label") or "preferred"
    other_rank_label = other_summary.get("rank_label") or "other"

    return {
        "preferred_candidate": {
            "side": "left" if left_is_preferred else "right",
            "label": preferred_summary.get("label"),
            "smiles": preferred_summary.get("smiles"),
        },
        "preferred_reason": " ".join(reasons)
        or "The current workflow prefers one candidate, but a plain-language reason was not available.",
        "confidence_limits": confidence_limits,
        "full_comparison_note": (
            f"{preferred_summary.get('label') or 'Preferred candidate'} is currently preferred over "
            f"{other_summary.get('label') or 'the other candidate'}. "
            f"Evidence-weighted scores: {_comparison_rank(preferred_candidate):.4f} vs {_comparison_rank(other_candidate):.4f}. "
            f"Final decisions: {_pretty_label(preferred_summary.get('candidate_status'))} vs "
            f"{_pretty_label(other_summary.get('candidate_status'))}. "
            f"{_faculty_explanation_path(preferred_summary['faculty_explanation'])}"
        ),
        "left_candidate_summary": left_summary,
        "right_candidate_summary": right_summary,
        "comparison_sections": comparison_sections,
        "section_summaries": {
            "novelty": _paired("novelty_summary", "novelty"),
            "admet": _paired("admet_summary", "ADMET"),
            "binding": _paired("binding_summary", "binding"),
            "decision": _paired("decision_summary", "decision"),
        },
        "score_note": (
            f"Candidate ranked '{pref_rank_label}' "
            f"(evidence-weighted score {_comparison_rank(preferred_candidate):.4f}) is preferred over "
            f"the candidate ranked '{other_rank_label}' "
            f"(score {_comparison_rank(other_candidate):.4f})."
        ),
    }


def _descriptor_payload(smiles: str) -> dict[str, Any]:
    """Compute stable RDKit descriptor fields for a valid SMILES string."""
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, QED

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Invalid SMILES string")

    mw = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)
    tpsa = Descriptors.TPSA(mol)
    qed = QED.qed(mol)
    rotatable_bonds = Descriptors.NumRotatableBonds(mol)
    rings = Descriptors.RingCount(mol)
    fraction_csp3 = Descriptors.FractionCSP3(mol)
    lipinski_violations = int(mw > 500) + int(logp > 5) + int(hbd > 5) + int(hba > 10)

    return {
        "smiles": smiles,
        "molecular_weight": round(mw, 2),
        "logp": round(logp, 3),
        "h_bond_donors": hbd,
        "h_bond_acceptors": hba,
        "tpsa": round(tpsa, 2),
        "qed_score": round(qed, 4),
        "passes_lipinski": lipinski_violations == 0,
        "lipinski_violations": lipinski_violations,
        "rotatable_bonds": rotatable_bonds,
        "ring_count": rings,
        "fraction_csp3": round(fraction_csp3, 3),
    }


def _legacy_score(smiles: str) -> float | None:
    """Return the legacy Genorova score when it is available."""
    try:
        from scorer import genorova_clinical_score

        return round(float(genorova_clinical_score(smiles)), 4)
    except Exception:
        return None


def _novelty_bucket(novelty_flag: str) -> str:
    """Backward-compatible wrapper around the canonical sanitizer novelty mapping."""
    return novelty_status_from_flag(novelty_flag)


def _major_risks(validation: dict[str, Any], *, fallback_used: bool, result_source: str) -> list[str]:
    chem = validation.get("chemistry", {})
    bind = validation.get("binding", {})
    admet = validation.get("admet", {})
    novelty = chem.get("novelty", {})
    admet_evidence = build_admet_evidence(admet)
    admet_provenance = admet_evidence.get("admet_provenance", {})
    binding_evidence = build_binding_evidence(bind)
    binding_provenance = binding_evidence.get("binding_provenance", {})

    risks: list[str] = []
    novelty_flag = novelty.get("flag", "local_only_checked")
    novelty_bucket = _novelty_bucket(novelty_flag)

    if novelty_bucket == "known":
        risks.append("Candidate appears to be a known or repurposing lead, not a novel discovery.")
    elif novelty_bucket == "uncertain":
        risks.append("Novelty is still uncertain because the active path does not confirm PubChem status by default.")

    if chem.get("is_pains"):
        risks.append("PAINS structural alert detected; assay interference risk needs follow-up.")

    binding_mode = bind.get("mode")
    binding_reason = bind.get("mode_reason") or bind.get("real_docking_failure")
    if not binding_evidence.get("binding_checked", False):
        risks.append("Binding was not checked because the active binding path could not evaluate the input.")
    elif binding_mode == "fallback_proxy":
        risks.append(
            "Binding evidence is fallback-proxy only because the real docking path is blocked or failed."
        )
        if binding_reason:
            risks.append(f"Docking blocker: {binding_reason}")
    elif binding_mode != "real_docking":
        risks.append("Binding evidence is proxy-based rather than a completed real-docking result.")

    hepatotoxicity = admet.get("hepatotoxicity_risk", {}).get("level")
    if hepatotoxicity in {"medium", "high"}:
        risks.append(f"Hepatotoxicity risk is flagged as {hepatotoxicity}.")

    herg = admet.get("herg_risk", {}).get("level")
    if herg in {"medium", "high"}:
        risks.append(f"hERG risk is flagged as {herg}.")

    cyp = admet.get("cyp_risk", {}).get("level")
    if cyp in {"medium", "high"}:
        risks.append(f"CYP interaction risk is flagged as {cyp}.")
    missing_checks = [
        label
        for label, checked in (
            ("hepatotoxicity", admet_provenance.get("hepatotoxicity_checked")),
            ("hERG", admet_provenance.get("herg_checked")),
            ("CYP interaction", admet_provenance.get("cyp_checked")),
        )
        if checked is False
    ]
    if missing_checks:
        risks.append(f"ADMET evidence is incomplete because {', '.join(missing_checks)} was not checked.")

    if fallback_used:
        risks.append("This candidate came through a fallback path rather than a fresh trusted generation run.")

    if result_source == "known_reference_fallback":
        risks.append("This molecule is being shown as a comparator reference, not as a newly discovered lead.")

    return risks


def _confidence_metadata(
    validation: dict[str, Any],
    *,
    fallback_used: bool,
    result_source: str,
) -> CandidateConfidence:
    """Summarize confidence and evidence level conservatively."""
    chemistry = validation.get("chemistry", {})
    binding = validation.get("binding", {})
    admet = validation.get("admet", {})
    novelty = chemistry.get("novelty", {})

    docking_mode = binding.get("mode", "unavailable")
    novelty_flag = novelty.get("flag", "local_only_checked")
    safety_flag = admet.get("overall_safety_flag", "unknown")

    if docking_mode == "real_docking" and novelty.get("pubchem_checked") and safety_flag == "likely_safe":
        return CandidateConfidence(
            level="high",
            evidence_level="computed_descriptors_plus_real_docking",
            note="Higher-confidence computational evidence: descriptors are computed and binding includes a real docking result.",
        )

    if docking_mode == "scaffold_proxy":
        note = "Moderate-confidence screening evidence: descriptors are computed, but binding remains a scaffold proxy."
        if novelty_flag == "local_only_checked":
            note += " Novelty remains uncertain without external lookup."
        return CandidateConfidence(
            level="medium",
            evidence_level="computed_descriptors_plus_proxy_binding",
            note=note,
        )

    if docking_mode == "fallback_proxy":
        note = (
            "Low-confidence screening evidence: descriptors are computed, but the real docking path is blocked "
            "and the system is using fallback proxy binding."
        )
        if novelty_flag == "local_only_checked":
            note += " Novelty also remains uncertain without external lookup."
        return CandidateConfidence(
            level="low",
            evidence_level="computed_descriptors_plus_fallback_proxy",
            note=note,
        )

    note = "Low-confidence evidence: no real docking result is available and the candidate should be treated as a screening-only result."
    if fallback_used or result_source == "known_reference_fallback":
        note += " The molecule also came from a fallback/comparator path."
    return CandidateConfidence(
        level="low",
        evidence_level="screening_only",
        note=note,
    )


def _adjusted_model_score(
    validation: dict[str, Any],
    *,
    fallback_used: bool,
    result_source: str,
) -> float:
    """
    Compute the evidence-weighted rank score for a candidate.

    Delegates entirely to validation.ranking.evidence_rank_score so that
    the penalty logic lives in exactly one place.  The 'validation' dict is
    supplemented with source-quality fields before scoring.
    """
    # Build a flat candidate dict that ranking.evidence_rank_score can read
    chemistry = validation.get("chemistry", {})
    binding   = validation.get("binding", {})
    admet     = validation.get("admet", {})
    clinical  = validation.get("clinical", {})

    flat = {
        "decision_score":       clinical.get("decision_score", 0.0),
        "final_decision":       clinical.get("decision", "reject"),
        "novelty_status":       _novelty_bucket(
                                    chemistry.get("novelty", {}).get("flag", "local_only_checked")
                                ),
        "novelty_flag":         chemistry.get("novelty", {}).get("flag", "local_only_checked"),
        "is_pains":             chemistry.get("is_pains", False),
        "docking_mode":         binding.get("mode", "unavailable"),
        "overall_safety_flag":  admet.get("overall_safety_flag", "unknown"),
        "hepatotoxicity_risk":  admet.get("hepatotoxicity_risk", {}),
        "herg_risk":            admet.get("herg_risk", {}),
        "cyp_interaction_risk": admet.get("cyp_risk", {}),
        "confidence_level":     (
                                    "high"
                                    if binding.get("mode") == "real_docking"
                                    else ("medium" if binding.get("mode") == "scaffold_proxy" else "low")
                                ),
        "fallback_used":        fallback_used,
        "result_source":        result_source,
        "pipeline_warnings":    validation.get("pipeline_warnings", []),
    }

    score, _ = evidence_rank_score(flat)
    return score


def _recommendation(adjusted_score: float, decision: str, candidate: dict | None = None) -> str:
    """
    Return a human-readable recommendation string.

    Delegates label logic to ranking.best_candidate_label when a full candidate
    dict is available; falls back to a simple tier map otherwise.
    """
    if candidate is not None:
        return best_candidate_label(candidate)
    if decision == "reject":
        return "rejected by evidence screen"
    if decision == "advance":
        return "provisional best candidate"
    if adjusted_score >= 0.60:
        return "conditional computational lead"
    return "low-priority computational result"


def evaluate_candidate(
    smiles: str,
    *,
    result_source: str,
    fallback_used: bool = False,
    validation_status: str | None = None,
    confidence_note: str | None = None,
    limitations: list[str] | None = None,
    recommended_next_step: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate a single candidate under the canonical active Genorova science path.

    The returned payload is intentionally API-friendly: it preserves legacy
    fields like `clinical_score` for frontend compatibility while adding a
    richer evidence ledger and validation snapshot.
    """
    from validation.pipeline import validate_molecule
    from validation.chemistry.sanitizer import calculate_sa_score

    descriptor_payload = _descriptor_payload(smiles)
    validation = validate_molecule(
        smiles=smiles,
        target=ACTIVE_TARGET,
        disease=ACTIVE_DISEASE,
        reference_drug=ACTIVE_REFERENCE_DRUG,
        pubchem_lookup=False,
    )

    chemistry = validation["chemistry"]
    binding = validation["binding"]
    admet = validation["admet"]
    clinical = validation["clinical"]
    novelty_evidence = build_novelty_evidence(chemistry.get("novelty", {}))
    novelty_provenance = novelty_evidence["novelty_provenance"]
    binding_evidence = build_binding_evidence(binding)
    binding_provenance = binding_evidence["binding_provenance"]
    admet_evidence = build_admet_evidence(admet)
    admet_provenance = admet_evidence["admet_provenance"]
    decision_provenance = clinical.get("decision_provenance") or {}
    confidence = _confidence_metadata(
        validation,
        fallback_used=fallback_used,
        result_source=result_source,
    )
    adjusted_score = _adjusted_model_score(
        validation,
        fallback_used=fallback_used,
        result_source=result_source,
    )
    novelty_flag = chemistry.get("novelty", {}).get("flag", "local_only_checked")
    novelty_status = novelty_evidence["novelty_status"]
    legacy_score = _legacy_score(smiles)
    sa_score, sa_source = calculate_sa_score(smiles)
    major_risks = _major_risks(
        validation,
        fallback_used=fallback_used,
        result_source=result_source,
    )

    notes = list(validation.get("binding", {}).get("notes", []))
    notes.extend(validation.get("chemistry", {}).get("notes", []))
    notes.extend(validation.get("admet", {}).get("notes", []))

    default_limitations = [
        ACTIVE_SCOPE_NOTE,
        "Outputs combine exact descriptor calculations with heuristic or proxy screening signals.",
        "This result is not experimental proof or clinical validation.",
    ]
    if binding.get("mode") == "fallback_proxy":
        default_limitations.append(
            "Binding evidence is fallback-proxy only because the real docking path is currently blocked."
        )
    elif binding.get("mode") != "real_docking":
        default_limitations.append("Binding evidence is proxy-based unless real docking is explicitly available.")
    if not binding_evidence["binding_checked"]:
        default_limitations.append("Binding was not checked because the active binding path could not evaluate the input structure.")
    if novelty_status == "uncertain":
        default_limitations.append("Novelty remains uncertain because the active path does not run external novelty lookup by default.")
    if admet_evidence["admet_evidence_level"] == "incomplete_heuristic_proxy":
        default_limitations.append("ADMET evidence is incomplete because one or more safety checks could not be completed.")
    elif admet_evidence["admet_evidence_level"] == "heuristic_proxy_regex_fallback":
        default_limitations.append("ADMET evidence relied on regex fallback alerts because RDKit descriptors were unavailable.")

    confidence_text = confidence_note or confidence.note

    # --- Canonical rank score and breakdown (from ranking module) ---
    # Build a minimal candidate-like dict so ranking.evidence_rank_score can score it
    _rank_input = {
        "decision_score":       clinical.get("decision_score", 0.0),
        "final_decision":       clinical.get("decision", "reject"),
        "novelty_status":       novelty_status,
        "novelty_flag":         novelty_flag,
        "is_pains":             chemistry.get("is_pains", False),
        "docking_mode":         binding.get("mode", "unavailable"),
        "overall_safety_flag":  admet.get("overall_safety_flag", "unknown"),
        "hepatotoxicity_risk":  admet.get("hepatotoxicity_risk", {}),
        "herg_risk":            admet.get("herg_risk", {}),
        "cyp_interaction_risk": admet.get("cyp_risk", {}),
        "confidence_level":     confidence.level,
        "fallback_used":        fallback_used,
        "result_source":        result_source,
        "pipeline_warnings":    validation.get("pipeline_warnings", []),
    }
    rank_score, rank_bd = evidence_rank_score(_rank_input)
    rank_label = best_candidate_label({**_rank_input, "rank_score": rank_score})
    faculty_explanation = build_faculty_explanation_stack(
        {
            "reference_drug": ACTIVE_REFERENCE_DRUG,
            "novelty_status": novelty_status,
            "novelty_closest_reference": novelty_evidence["novelty_closest_reference"],
            "novelty_tanimoto_score": novelty_evidence["novelty_tanimoto_score"],
            "novelty_threshold": novelty_evidence["novelty_threshold"],
            "novelty_reason": novelty_evidence["novelty_reason"],
            "novelty_provenance": novelty_provenance,
            "binding_checked": binding_evidence["binding_checked"],
            "binding_state": binding_evidence["binding_state"],
            "binding_mode": binding_evidence["binding_mode"],
            "binding_score": binding.get("docking_score"),
            "reference_score": binding.get("reference_score"),
            "delta_vs_reference": binding.get("delta_vs_reference"),
            "real_docking_status": binding.get("real_docking_status"),
            "real_docking_failure": binding.get("real_docking_failure"),
            "final_binding_reason": binding_evidence["final_binding_reason"],
            "binding_provenance": binding_provenance,
            "overall_safety_flag": admet.get("overall_safety_flag"),
            "overall_safety_reason": admet_evidence["overall_safety_reason"],
            "admet_evidence_level": admet_evidence["admet_evidence_level"],
            "admet_provenance": admet_provenance,
            "hepatotoxicity_risk": admet.get("hepatotoxicity_risk", {}).get("level"),
            "herg_risk": admet.get("herg_risk", {}).get("level"),
            "cyp_interaction_risk": admet.get("cyp_risk", {}).get("level"),
            "final_decision": clinical.get("decision"),
            "decision_score": clinical.get("decision_score"),
            "decision_confidence_tier": decision_provenance.get("confidence_tier"),
            "decision_evidence_level": decision_provenance.get("evidence_level"),
            "final_decision_reason": decision_provenance.get("final_decision_reason"),
            "decision_provenance": decision_provenance,
        }
    )

    evidence_ledger = {
        "program_id": ACTIVE_PROGRAM_ID,
        "program_label": ACTIVE_PROGRAM_LABEL,
        "target": ACTIVE_TARGET,
        "disease": ACTIVE_DISEASE,
        "reference_drug": ACTIVE_REFERENCE_DRUG,
        "reference_strategy": "Single canonical comparator against acetazolamide in the bacterial carbonic anhydrase workflow.",
        "known_vs_uncertain_vs_potentially_novel": novelty_status,
        "novelty_flag": novelty_flag,
        "novelty_closest_reference": novelty_evidence["novelty_closest_reference"],
        "novelty_tanimoto_score": novelty_evidence["novelty_tanimoto_score"],
        "novelty_threshold": novelty_evidence["novelty_threshold"],
        "novelty_reason": novelty_evidence["novelty_reason"],
        "novelty_provenance": novelty_provenance,
        "novelty_provenance_explanation": novelty_evidence["novelty_provenance_explanation"],
        "binding_checked": binding_evidence["binding_checked"],
        "binding_mode": binding_evidence["binding_mode"],
        "binding_evidence_level": binding_evidence["binding_evidence_level"],
        "final_binding_reason": binding_evidence["final_binding_reason"],
        "binding_provenance": binding_provenance,
        "binding_provenance_explanation": binding_evidence["binding_provenance_explanation"],
        "overall_safety_flag": admet.get("overall_safety_flag"),
        "overall_safety_reason": admet_evidence["overall_safety_reason"],
        "overall_safety_method": admet_evidence["overall_safety_method"],
        "admet_evidence_level": admet_evidence["admet_evidence_level"],
        "admet_provenance": admet_provenance,
        "admet_provenance_explanation": admet_evidence["admet_provenance_explanation"],
        "proxy_vs_real_docking": binding.get("mode"),
        "binding_mode_reason": binding.get("mode_reason"),
        "binding_score": binding.get("docking_score"),
        "reference_score": binding.get("reference_score"),
        "delta_vs_reference": binding.get("delta_vs_reference"),
        "real_docking_status": binding.get("real_docking_status"),
        "real_docking_failure": binding.get("real_docking_failure"),
        "real_docking_probe_blockers": list((binding.get("real_docking_probe") or {}).get("blockers") or []),
        "computed_fields": COMPUTED_FIELD_NAMES,
        "heuristic_fields": HEURISTIC_FIELD_NAMES,
        "major_risks": major_risks,
        "final_decision": clinical.get("decision"),
        "decision_score": clinical.get("decision_score"),
        "rank_score": rank_score,
        "rank_breakdown": rank_bd.to_dict(),
        "rank_label": rank_label,
        "confidence_level": confidence.level,
        "evidence_level": confidence.evidence_level,
        "recommendation_rationale": validation.get("summary"),
        "decision_provenance": decision_provenance,
        "decision_provenance_explanation": decision_provenance.get("provenance_explanation"),
        "final_decision_reason": decision_provenance.get("final_decision_reason"),
        "decision_confidence_tier": decision_provenance.get("confidence_tier"),
        "decision_evidence_level": decision_provenance.get("evidence_level"),
        "faculty_explanation": faculty_explanation,
    }

    validation_snapshot = {
        "sa_score": round(float(sa_score), 4),
        "sa_score_source": sa_source,
        "novelty_status": novelty_status,
        "novelty_flag": novelty_flag,
        "novelty_closest_reference": novelty_evidence["novelty_closest_reference"],
        "novelty_tanimoto_score": novelty_evidence["novelty_tanimoto_score"],
        "novelty_threshold": novelty_evidence["novelty_threshold"],
        "novelty_reason": novelty_evidence["novelty_reason"],
        "novelty_provenance": novelty_provenance,
        "novelty_provenance_explanation": novelty_evidence["novelty_provenance_explanation"],
        "binding_checked": binding_evidence["binding_checked"],
        "binding_mode": binding_evidence["binding_mode"],
        "binding_evidence_level": binding_evidence["binding_evidence_level"],
        "final_binding_reason": binding_evidence["final_binding_reason"],
        "binding_provenance": binding_provenance,
        "binding_provenance_explanation": binding_evidence["binding_provenance_explanation"],
        "overall_safety_flag": admet.get("overall_safety_flag"),
        "overall_safety_reason": admet_evidence["overall_safety_reason"],
        "overall_safety_method": admet_evidence["overall_safety_method"],
        "admet_evidence_level": admet_evidence["admet_evidence_level"],
        "admet_provenance": admet_provenance,
        "admet_provenance_explanation": admet_evidence["admet_provenance_explanation"],
        "is_pains": chemistry.get("is_pains"),
        "pains_matches": chemistry.get("pains_matches", []),
        "docking_mode": binding.get("mode"),
        "binding_mode_reason": binding.get("mode_reason"),
        "binding_score": binding.get("docking_score"),
        "reference_score": binding.get("reference_score"),
        "delta_vs_reference": binding.get("delta_vs_reference"),
        "real_docking_status": binding.get("real_docking_status"),
        "real_docking_failure": binding.get("real_docking_failure"),
        "real_docking_probe_blockers": list((binding.get("real_docking_probe") or {}).get("blockers") or []),
        "hepatotoxicity_risk": admet.get("hepatotoxicity_risk", {}).get("level"),
        "hERG_risk": admet.get("herg_risk", {}).get("level"),
        "cyp_interaction_risk": admet.get("cyp_risk", {}).get("level"),
        "final_decision": clinical.get("decision"),
        "decision_score": clinical.get("decision_score"),
        "rank_score": rank_score,
        "rank_label": rank_label,
        "confidence_level": confidence.level,
        "evidence_level": confidence.evidence_level,
        "decision_provenance": decision_provenance,
        "decision_provenance_explanation": decision_provenance.get("provenance_explanation"),
        "final_decision_reason": decision_provenance.get("final_decision_reason"),
        "decision_confidence_tier": decision_provenance.get("confidence_tier"),
        "decision_evidence_level": decision_provenance.get("evidence_level"),
        "faculty_explanation": faculty_explanation,
    }

    return {
        **descriptor_payload,
        "smiles": smiles,
        "sa_score": round(float(sa_score), 4),
        # canonical rank_score is the authoritative ordering field
        "rank_score": rank_score,
        "rank_breakdown": rank_bd.to_dict(),
        "rank_label": rank_label,
        # clinical_score kept for backward compat with API / frontend
        "clinical_score": rank_score,
        "model_score": rank_score,
        "legacy_clinical_score": legacy_score,
        "recommendation": rank_label,
        "program_id": ACTIVE_PROGRAM_ID,
        "program_label": ACTIVE_PROGRAM_LABEL,
        "target": ACTIVE_TARGET,
        "target_label": ACTIVE_PROGRAM_LABEL,
        "target_disease": ACTIVE_DISEASE,
        "reference_drug": ACTIVE_REFERENCE_DRUG,
        **binding_evidence,
        "novelty_status": novelty_status,
        "novelty_flag": novelty_flag,
        **novelty_evidence,
        "overall_safety_flag": admet.get("overall_safety_flag"),
        "overall_safety_reason": admet_evidence["overall_safety_reason"],
        "overall_safety_method": admet_evidence["overall_safety_method"],
        "admet_evidence_level": admet_evidence["admet_evidence_level"],
        "admet_provenance": admet_provenance,
        "admet_provenance_explanation": admet_evidence["admet_provenance_explanation"],
        "is_pains": chemistry.get("is_pains"),
        "pains_matches": chemistry.get("pains_matches", []),
        "docking_mode": binding.get("mode"),
        "binding_mode_reason": binding.get("mode_reason"),
        "binding_score": binding.get("docking_score"),
        "reference_score": binding.get("reference_score"),
        "delta_vs_reference": binding.get("delta_vs_reference"),
        "real_docking_status": binding.get("real_docking_status"),
        "real_docking_failure": binding.get("real_docking_failure"),
        "hepatotoxicity_risk": admet.get("hepatotoxicity_risk", {}).get("level"),
        "herg_risk": admet.get("herg_risk", {}).get("level"),
        "cyp_interaction_risk": admet.get("cyp_risk", {}).get("level"),
        "final_decision": clinical.get("decision"),
        "decision_score": clinical.get("decision_score"),
        "evidence_level": confidence.evidence_level,
        "confidence_level": confidence.level,
        "validation_status": validation_status or "canonical_validation_complete",
        "confidence_note": confidence_text,
        "limitations": limitations or default_limitations,
        "recommended_next_step": recommended_next_step or clinical.get("recommended_next_step"),
        "result_source": result_source,
        "fallback_used": fallback_used,
        "major_risks": major_risks,
        "summary": validation.get("summary"),
        "notes": notes,
        "validation": validation_snapshot,
        "evidence_ledger": evidence_ledger,
        "faculty_explanation": faculty_explanation,
        "decision_provenance": decision_provenance,
        "decision_provenance_explanation": decision_provenance.get("provenance_explanation"),
        "final_decision_reason": decision_provenance.get("final_decision_reason"),
        "decision_confidence_tier": decision_provenance.get("confidence_tier"),
        "decision_evidence_level": decision_provenance.get("evidence_level"),
    }


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, float, int]:
    """
    Sort key for evaluated candidates — delegates to the canonical ranking module.

    Kept for backward compatibility with any external callers.
    All internal code should use `validation.ranking.sort_key` directly.
    """
    return canonical_sort_key(candidate)


def evaluate_candidate_rows(
    rows: list[dict[str, Any]],
    *,
    result_source: str,
    fallback_used: bool,
    max_candidates: int,
    confidence_note: str,
    validation_status: str,
    limitations: list[str],
    recommended_next_step: str,
) -> list[dict[str, Any]]:
    """
    Re-evaluate a ranked source row list under the canonical active workflow.

    Only a bounded pool is evaluated to keep the live path practical.
    """
    unique_smiles: list[str] = []
    seen: set[str] = set()
    for row in rows:
        smiles = str(row.get("smiles") or "").strip()
        if not smiles or smiles in seen:
            continue
        seen.add(smiles)
        unique_smiles.append(smiles)

    pool_size = max(max_candidates, min(max_candidates * 3, 24))
    evaluated: list[dict[str, Any]] = []
    for smiles in unique_smiles[:pool_size]:
        try:
            evaluated.append(
                evaluate_candidate(
                    smiles,
                    result_source=result_source,
                    fallback_used=fallback_used,
                    validation_status=validation_status,
                    confidence_note=confidence_note,
                    limitations=limitations,
                    recommended_next_step=recommended_next_step,
                )
            )
        except Exception:
            continue

    # Use the canonical rank_batch so rank_score, rank_label, and rank are
    # set consistently regardless of which consumer calls this function.
    evaluated = rank_batch(evaluated)
    preferred = [c for c in evaluated if c.get("final_decision") != "reject"]
    result = preferred[:max_candidates] if preferred else evaluated[:max_candidates]
    return result
