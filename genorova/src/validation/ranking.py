"""
Genorova AI - Canonical Evidence-Weighted Ranking
=================================================

PURPOSE:
Single authoritative module for ranking evaluated drug candidates.

Design principles:
1. Evidence quality affects rank.
2. Proxy-only candidates can still be compared, but they cannot earn the
   strongest label without real docking.
3. Penalties are explicit and inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


NOVELTY_PENALTY_KNOWN = 0.15
NOVELTY_PENALTY_UNCERTAIN = 0.05
PAINS_PENALTY = 0.10
SCAFFOLD_PROXY_BINDING_PENALTY = 0.08
FALLBACK_PROXY_BINDING_PENALTY = 0.12
UNAVAILABLE_BINDING_PENALTY = 0.15
SAFETY_CAUTION_PENALTY = 0.05
SAFETY_UNSAFE_PENALTY = 0.20
CONFIDENCE_TIER_LOW_PENALTY = 0.08
SOURCE_FALLBACK_PENALTY = 0.08
SOURCE_REFERENCE_PENALTY = 0.07
MISMATCH_PENALTY = 0.10

LABEL_PROVISIONAL_BEST_THRESHOLD = 0.65
LABEL_CONDITIONAL_LEAD_THRESHOLD = 0.45


@dataclass
class RankBreakdown:
    base_score: float = 0.0
    novelty_penalty: float = 0.0
    pains_penalty: float = 0.0
    binding_penalty: float = 0.0
    safety_penalty: float = 0.0
    confidence_penalty: float = 0.0
    source_penalty: float = 0.0
    mismatch_penalty: float = 0.0
    rank_score: float = 0.0
    penalties_applied: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "base_score": round(self.base_score, 4),
            "novelty_penalty": round(-self.novelty_penalty, 4),
            "pains_penalty": round(-self.pains_penalty, 4),
            "binding_penalty": round(-self.binding_penalty, 4),
            "safety_penalty": round(-self.safety_penalty, 4),
            "confidence_penalty": round(-self.confidence_penalty, 4),
            "source_penalty": round(-self.source_penalty, 4),
            "mismatch_penalty": round(-self.mismatch_penalty, 4),
            "rank_score": round(self.rank_score, 4),
            "penalties_applied": self.penalties_applied,
        }


def _binding_penalty_for_mode(mode: str) -> tuple[float, str]:
    if mode == "real_docking":
        return 0.0, ""
    if mode == "scaffold_proxy":
        return (
            SCAFFOLD_PROXY_BINDING_PENALTY,
            f"binding=scaffold_proxy (-{SCAFFOLD_PROXY_BINDING_PENALTY}): no real docking result",
        )
    if mode == "fallback_proxy":
        return (
            FALLBACK_PROXY_BINDING_PENALTY,
            f"binding=fallback_proxy (-{FALLBACK_PROXY_BINDING_PENALTY}): docking path blocked or failed",
        )
    return (
        UNAVAILABLE_BINDING_PENALTY,
        f"binding=unavailable (-{UNAVAILABLE_BINDING_PENALTY}): no usable binding evidence",
    )


def evidence_rank_score(candidate: dict[str, Any]) -> tuple[float, RankBreakdown]:
    bd = RankBreakdown()

    raw = (
        candidate.get("decision_score")
        or candidate.get("clinical", {}).get("decision_score")
        or candidate.get("clinical_score")
        or 0.0
    )
    bd.base_score = float(raw)
    score = bd.base_score

    novelty = candidate.get("novelty_status") or candidate.get("novelty_flag", "local_only_checked")
    if novelty in ("known", "known_repurposing_lead"):
        bd.novelty_penalty = NOVELTY_PENALTY_KNOWN
        bd.penalties_applied.append(
            f"novelty=known (-{NOVELTY_PENALTY_KNOWN}): molecule matches a known compound"
        )
    elif novelty in ("uncertain", "local_only_checked"):
        bd.novelty_penalty = NOVELTY_PENALTY_UNCERTAIN
        bd.penalties_applied.append(
            f"novelty=uncertain (-{NOVELTY_PENALTY_UNCERTAIN}): PubChem not checked"
        )
    score -= bd.novelty_penalty

    if candidate.get("is_pains", False):
        bd.pains_penalty = PAINS_PENALTY
        bd.penalties_applied.append(f"PAINS alert detected (-{PAINS_PENALTY})")
    score -= bd.pains_penalty

    docking_mode = candidate.get("docking_mode") or candidate.get("binding", {}).get("mode", "unavailable")
    bd.binding_penalty, binding_note = _binding_penalty_for_mode(docking_mode)
    if binding_note:
        bd.penalties_applied.append(binding_note)
    score -= bd.binding_penalty

    safety = candidate.get("overall_safety_flag") or candidate.get("admet", {}).get("overall_safety_flag", "unknown")
    hep = candidate.get("hepatotoxicity_risk") or candidate.get("admet", {}).get("hepatotoxicity_risk", {})
    herg = candidate.get("herg_risk") or candidate.get("admet", {}).get("herg_risk", {})
    cyp = candidate.get("cyp_interaction_risk") or candidate.get("admet", {}).get("cyp_risk", {})

    hep_level = hep.get("level", hep) if isinstance(hep, dict) else hep
    herg_level = herg.get("level", herg) if isinstance(herg, dict) else herg
    cyp_level = cyp.get("level", cyp) if isinstance(cyp, dict) else cyp

    if safety == "likely_unsafe" or any(level == "high" for level in (hep_level, herg_level, cyp_level)):
        bd.safety_penalty = SAFETY_UNSAFE_PENALTY
        bd.penalties_applied.append(f"safety=likely_unsafe/high (-{SAFETY_UNSAFE_PENALTY})")
    elif safety == "caution" or any(level == "medium" for level in (hep_level, herg_level, cyp_level)):
        bd.safety_penalty = SAFETY_CAUTION_PENALTY
        bd.penalties_applied.append(f"safety=caution/medium (-{SAFETY_CAUTION_PENALTY})")
    score -= bd.safety_penalty

    confidence = candidate.get("confidence_level") or candidate.get("confidence_tier", "")
    if confidence in ("low", "tier_3_low", "none"):
        bd.confidence_penalty = CONFIDENCE_TIER_LOW_PENALTY
        bd.penalties_applied.append(
            f"confidence=low/tier_3 (-{CONFIDENCE_TIER_LOW_PENALTY}): evidence remains screening-only"
        )
    score -= bd.confidence_penalty

    fallback = candidate.get("fallback_used", False)
    source = candidate.get("result_source", "")
    if source == "known_reference_fallback":
        bd.source_penalty = SOURCE_REFERENCE_PENALTY
        bd.penalties_applied.append(
            f"source=known_reference (-{SOURCE_REFERENCE_PENALTY}): comparator reference, not a generated lead"
        )
    elif fallback:
        bd.source_penalty = SOURCE_FALLBACK_PENALTY
        bd.penalties_applied.append(
            f"source=fallback (-{SOURCE_FALLBACK_PENALTY}): came from a fallback path"
        )
    score -= bd.source_penalty

    dt_warnings = (
        candidate.get("pipeline_warnings")
        or candidate.get("dt_warnings")
        or candidate.get("evidence_ledger", {}).get("dt_warnings", [])
    )
    if dt_warnings:
        bd.mismatch_penalty = MISMATCH_PENALTY
        bd.penalties_applied.append(
            f"disease-target mismatch (-{MISMATCH_PENALTY}): {dt_warnings[0][:80]}"
        )
    score -= bd.mismatch_penalty

    bd.rank_score = round(max(0.0, min(1.0, score)), 4)
    return bd.rank_score, bd


_DECISION_ORDER = {"advance": 2, "conditional_advance": 1, "reject": 0}
_CONFIDENCE_ORDER = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "none": 0,
    "tier_1_high": 3,
    "tier_2_medium": 2,
    "tier_3_low": 1,
}


def sort_key(candidate: dict[str, Any]) -> tuple[int, float, int]:
    decision = candidate.get("final_decision", "reject")
    rank_score = float(candidate.get("rank_score") or candidate.get("clinical_score") or 0.0)
    confidence = candidate.get("confidence_level") or candidate.get("confidence_tier", "low")
    return (
        _DECISION_ORDER.get(decision, 0),
        rank_score,
        _CONFIDENCE_ORDER.get(confidence, 0),
    )


def _passes_evidence_gates(candidate: dict[str, Any]) -> bool:
    decision = candidate.get("final_decision", "reject")
    if decision == "reject":
        return False

    safety = candidate.get("overall_safety_flag") or candidate.get("admet", {}).get("overall_safety_flag", "unknown")
    if safety == "likely_unsafe":
        return False

    if candidate.get("is_pains", False):
        return False

    docking = candidate.get("docking_mode") or candidate.get("binding", {}).get("mode", "unavailable")
    return docking == "real_docking"


def best_candidate_label(candidate: dict[str, Any]) -> str:
    decision = candidate.get("final_decision", "reject")
    safety = candidate.get("overall_safety_flag") or candidate.get("admet", {}).get("overall_safety_flag", "unknown")
    rank_score = float(candidate.get("rank_score") or candidate.get("clinical_score") or 0.0)

    if decision == "reject" or safety == "likely_unsafe":
        return "rejected by evidence screen"

    if _passes_evidence_gates(candidate) and rank_score >= LABEL_PROVISIONAL_BEST_THRESHOLD:
        return "provisional best candidate"

    if rank_score >= LABEL_CONDITIONAL_LEAD_THRESHOLD:
        return "conditional computational lead"

    if rank_score > 0.0:
        return "low-priority computational result"

    return "rejected by evidence screen"


def rank_batch(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for candidate in candidates:
        score, breakdown = evidence_rank_score(candidate)
        candidate["rank_score"] = score
        candidate["rank_breakdown"] = breakdown.to_dict()
        candidate["rank_label"] = best_candidate_label(candidate)

    candidates.sort(key=sort_key, reverse=True)
    for index, candidate in enumerate(candidates, 1):
        candidate["rank"] = index
    return candidates


def best_candidate_rationale(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return ""

    top = candidates[0]
    label = top.get("rank_label", best_candidate_label(top))
    rank_score = float(top.get("rank_score") or top.get("clinical_score") or 0.0)
    smiles_short = str(top.get("smiles", ""))[:40]
    target = top.get("target", "dpp4")
    ref_drug = top.get("reference_drug", "sitagliptin")
    decision = top.get("final_decision", "unknown")
    docking = top.get("docking_mode", "unavailable")
    confidence = top.get("confidence_level", "low")
    novelty = top.get("novelty_status", "uncertain")
    breakdown = top.get("rank_breakdown", {})
    penalties = breakdown.get("penalties_applied", [])
    base = breakdown.get("base_score", rank_score)

    if len(candidates) == 1:
        why = "It is the only candidate in this evaluation run."
    elif rank_score == float(candidates[1].get("rank_score") or 0.0):
        why = "It ties with the next candidate on evidence-weighted score."
    else:
        gap = round(rank_score - float(candidates[1].get("rank_score") or 0.0), 4)
        why = f"It scored {gap:.4f} higher than the next candidate on the evidence-weighted scale."

    if docking == "real_docking":
        evidence = f"Binding evidence includes a real docking result against {target}."
    elif docking == "fallback_proxy":
        evidence = (
            f"Binding evidence is a fallback proxy because the real docking path is blocked. "
            f"Reference comparator: {ref_drug}."
        )
    else:
        evidence = (
            f"Binding evidence is a scaffold-similarity proxy against {target} "
            f"(no real docking). Reference comparator: {ref_drug}."
        )

    evidence += f" Pipeline decision: {decision.replace('_', ' ')}. Base score: {base:.4f}."

    if penalties:
        limitations = "Evidence penalties applied: " + "; ".join(f"[{item}]" for item in penalties[:4]) + "."
    else:
        limitations = "No penalties were applied in this run."

    confidence_note = (
        "Confidence is medium-to-high."
        if confidence in ("medium", "high", "tier_2_medium", "tier_1_high")
        else "Confidence is low because the result remains screening-only."
    )

    novelty_note = (
        "Novelty appears potentially novel vs the local database."
        if novelty == "potentially_novel"
        else "Novelty is uncertain or this is a known compound."
    )

    return (
        f"Top-ranked candidate ({smiles_short}...) labelled '{label}' with evidence-weighted score {rank_score:.4f}. "
        f"{why} {evidence} {confidence_note} {novelty_note} {limitations} "
        f"This result is a computational screen only and requires wet-lab confirmation."
    )


if __name__ == "__main__":
    test_candidate = {
        "smiles": "Cc1ccc(NC(=O)c2ccc(N)cc2)cc1",
        "final_decision": "conditional_advance",
        "clinical_score": 0.72,
        "decision_score": 0.72,
        "novelty_status": "uncertain",
        "is_pains": False,
        "docking_mode": "fallback_proxy",
        "overall_safety_flag": "caution",
        "confidence_level": "low",
        "fallback_used": False,
        "result_source": "precomputed_ranked_candidates",
    }

    score, breakdown = evidence_rank_score(test_candidate)
    print(f"rank_score = {score}")
    print(f"breakdown  = {breakdown.to_dict()}")
    print(f"label      = {best_candidate_label(test_candidate)}")
