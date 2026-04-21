"""
Genorova AI - Validation: Target Engagement Module
==================================================

PURPOSE:
Evaluate whether a candidate is likely to bind the declared target and compare
it against the canonical reference drug for that target.

BACKEND MODES:
  1. real_docking   -- A real docking run completed successfully against a
                       prepared receptor asset.
  2. scaffold_proxy -- A proxy score is used because the target does not have
                       an active real-docking path.
  3. fallback_proxy -- The target does have a nominal real-docking path, but
                       the runtime is blocked or failed, so the module falls
                       back to a structural proxy.
  4. unavailable    -- Neither real docking nor proxy scoring can produce a
                       usable result.

The result always includes:
  - mode
  - confidence
  - mode_reason
  - real_docking_status
  - real_docking_failure
  - real_docking_probe
  - binding_provenance

This keeps downstream consumers honest about what really happened.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import sys as _sys

_VALIDATION_DIR = Path(__file__).resolve().parents[1]
if str(_VALIDATION_DIR) not in _sys.path:
    _sys.path.insert(0, str(_VALIDATION_DIR.parent))

from validation.reference_data import (  # noqa: E402
    ACCEPTABLE_DELTA_VS_REFERENCE,
    BETTER_THAN_REFERENCE_DELTA,
    KNOWN_TARGETS,
)


_RDKIT_LOADED = None
_Chem = None
_AllChem = None
_DataStructs = None
_Descriptors = None


def _try_load_rdkit() -> bool:
    """Load RDKit once and cache the result."""
    global _RDKIT_LOADED, _Chem, _AllChem, _DataStructs, _Descriptors

    if _RDKIT_LOADED is not None:
        return _RDKIT_LOADED

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            from rdkit import Chem as _c
            from rdkit import RDLogger as _rl
            from rdkit.Chem import AllChem as _ac
            from rdkit.Chem import DataStructs as _ds
            from rdkit.Chem import Descriptors as _d

            _rl.DisableLog("rdApp.*")

        _Chem = _c
        _AllChem = _ac
        _DataStructs = _ds
        _Descriptors = _d
        _RDKIT_LOADED = True
        return True
    except Exception:
        _RDKIT_LOADED = False
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _src_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _docking_dir() -> Path:
    return _repo_root() / "docking"


def _normalize_target_key(target: str) -> str:
    return target.lower().replace("-", "_").replace(" ", "_")


def _resolve_vina_executable() -> Optional[str]:
    """Resolve a Vina executable path without claiming it is runnable."""
    for candidate in (
        shutil.which("vina"),
        shutil.which("vina.exe"),
        str(_repo_root() / "vina.exe"),
        str(_repo_root() / "vina"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _resolve_receptor_asset(target_key: str) -> tuple[Optional[Path], List[str]]:
    """Return the prepared receptor asset for the target when present."""
    blockers: List[str] = []
    target_info = KNOWN_TARGETS.get(target_key)
    if target_info is None:
        return None, blockers

    pdb_id = target_info.get("pdb_id", "")
    if not pdb_id:
        blockers.append(f"Target '{target_key}' does not declare a PDB identifier.")
        return None, blockers

    docking_dir = _docking_dir()
    candidates = [
        docking_dir / f"{pdb_id.lower()}_prepared.pdbqt",
        docking_dir / f"{pdb_id}_prepared.pdbqt",
        docking_dir / f"{pdb_id.lower()}.pdbqt",
        docking_dir / f"{pdb_id}.pdbqt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate, blockers

    blockers.append(
        f"Prepared receptor asset missing for {target_key} ({pdb_id}); "
        f"expected one of {[path.name for path in candidates]} in {docking_dir}."
    )
    return None, blockers


def _build_real_docking_probe(target_key: str) -> dict[str, Any]:
    """
    Inspect whether the declared real-docking path is truly executable.

    The probe is deliberately strict. We only call the mode 'real_docking'
    when all required pieces are present and the docking helper exposes the
    expected callable entrypoint.
    """
    probe: dict[str, Any] = {
        "target_key": target_key,
        "target_supported": target_key in KNOWN_TARGETS,
        "rdkit_available": _try_load_rdkit(),
        "vina_executable": _resolve_vina_executable(),
        "vina_available": False,
        "receptor_asset_checked": False,
        "receptor_asset_available": False,
        "docking_engine_checked": False,
        "docking_engine_available": False,
        "docking_import_ok": False,
        "dock_molecule_available": False,
        "receptor_asset": None,
        "status": "blocked",
        "blockers": [],
    }

    if not probe["target_supported"]:
        probe["status"] = "unsupported_target"
        probe["blockers"].append(
            f"Target '{target_key}' is not in KNOWN_TARGETS, so no target-specific docking path exists."
        )
        return probe

    if not probe["rdkit_available"]:
        probe["blockers"].append("RDKit is unavailable, so proxy preparation and chemistry validation are limited.")

    if probe["vina_executable"]:
        probe["vina_available"] = True
    else:
        probe["blockers"].append("AutoDock Vina executable was not found in PATH or the repo-local Genorova bundle.")

    receptor_asset, receptor_blockers = _resolve_receptor_asset(target_key)
    probe["receptor_asset_checked"] = True
    probe["receptor_asset"] = str(receptor_asset) if receptor_asset else None
    probe["receptor_asset_available"] = receptor_asset is not None
    probe["blockers"].extend(receptor_blockers)

    try:
        src_dir = str(_src_root())
        if src_dir not in _sys.path:
            _sys.path.insert(0, src_dir)

        import docking.docking_engine as docking_engine  # noqa: PLC0415

        probe["docking_engine_checked"] = True
        probe["docking_import_ok"] = True
        dock_callable = getattr(docking_engine, "dock_molecule", None)
        if callable(dock_callable):
            probe["dock_molecule_available"] = True
            probe["docking_engine_available"] = True
        else:
            probe["blockers"].append(
                "docking.docking_engine imports successfully but does not expose a callable dock_molecule(smiles, protein_pdbqt)."
            )
    except Exception as exc:
        probe["docking_engine_checked"] = True
        probe["blockers"].append(f"Could not import docking.docking_engine: {exc}")

    if (
        probe["vina_available"]
        and probe["dock_molecule_available"]
        and probe["receptor_asset"]
    ):
        probe["status"] = "ready"

    return probe


def _detect_mode(target_key: str, probe: dict[str, Any]) -> str:
    """
    Detect the binding mode conservatively.

    real_docking  -- runtime probe says the real path is ready
    fallback_proxy -- target is supported but the real path is blocked or fails
    scaffold_proxy -- target is unsupported, but RDKit can still estimate
    unavailable    -- nothing trustworthy can be returned
    """
    rdkit_ok = probe.get("rdkit_available", False)
    target_supported = probe.get("target_supported", False)

    if probe.get("status") == "ready":
        return "real_docking"
    if target_supported and rdkit_ok:
        return "fallback_proxy"
    if rdkit_ok:
        return "scaffold_proxy"
    return "unavailable"


def _scaffold_proxy_score(smiles: str, target_key: str) -> Tuple[Optional[float], str]:
    """
    Estimate a target-binding proxy score for a molecule.

    This is not a physical docking calculation. It is a structural similarity
    interpolation anchored on the target reference drug when available.
    """
    if not _try_load_rdkit():
        return None, "RDKit unavailable; cannot compute proxy score."

    target_info = KNOWN_TARGETS.get(target_key)
    if target_info is None:
        return _generic_property_proxy(smiles)

    mol = _Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, "Invalid SMILES."

    ref_mol = _Chem.MolFromSmiles(target_info["reference_smiles"])
    if ref_mol is None:
        return _generic_property_proxy(smiles)

    fp_candidate = _AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
    fp_reference = _AllChem.GetMorganFingerprintAsBitVect(ref_mol, 2, nBits=2048)
    tanimoto = _DataStructs.TanimotoSimilarity(fp_candidate, fp_reference)

    ref_energy = target_info["known_binding_kcal_mol"]
    weak_baseline = -4.0
    proxy_score = weak_baseline + tanimoto * (ref_energy - weak_baseline)

    try:
        mw = _Descriptors.MolWt(mol)
        logp = _Descriptors.MolLogP(mol)
        hba = _Descriptors.NumHAcceptors(mol)
        hbd = _Descriptors.NumHDonors(mol)

        if 250 <= mw <= 400:
            proxy_score -= 0.4
        elif 150 <= mw <= 500:
            proxy_score -= 0.2

        if 1 <= logp <= 4:
            proxy_score -= 0.3
        if 2 <= hba <= 7:
            proxy_score -= 0.2
        if 1 <= hbd <= 4:
            proxy_score -= 0.1
    except Exception:
        pass

    proxy_score = round(max(-12.0, min(-2.0, proxy_score)), 2)

    explanation = (
        f"Tanimoto similarity to {target_info['reference_drug']} = {tanimoto:.3f}. "
        f"Reference literature anchor = {ref_energy:.1f} kcal/mol. "
        f"Proxy estimate = {proxy_score:.2f}. This is not a docking calculation."
    )
    return proxy_score, explanation


def _generic_property_proxy(smiles: str) -> Tuple[Optional[float], str]:
    """Fallback proxy when no target-specific anchor is available."""
    if not _try_load_rdkit():
        return None, "RDKit unavailable."

    mol = _Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, "Invalid SMILES."

    try:
        mw = _Descriptors.MolWt(mol)
        logp = _Descriptors.MolLogP(mol)
        hba = _Descriptors.NumHAcceptors(mol)
        hbd = _Descriptors.NumHDonors(mol)
        aromatic_rings = _Descriptors.NumAromaticRings(mol)

        score = -4.0
        if 200 <= mw <= 500:
            score -= 0.5
        if 1 <= logp <= 4:
            score -= 0.5
        if hba >= 2:
            score -= 0.3
        if hbd >= 1:
            score -= 0.2
        if aromatic_rings >= 1:
            score -= 0.3

        score = round(max(-9.0, score), 2)
        return score, "Generic property-based proxy; no target-specific docking anchor is available."
    except Exception as exc:
        return None, f"Property calculation failed: {exc}"


def _run_real_docking(
    smiles: str,
    target_key: str,
    probe: dict[str, Any],
) -> Tuple[Optional[float], List[str], Optional[str]]:
    """
    Attempt a real docking run through the existing docking helper.

    Returns:
        (score_kcal_mol, h_bond_residues, failure_reason)
    """
    if probe.get("status") != "ready":
        blockers = probe.get("blockers") or ["Real docking is not ready."]
        return None, [], _collapse_blockers(blockers)

    try:
        src_dir = str(_src_root())
        if src_dir not in _sys.path:
            _sys.path.insert(0, src_dir)

        from docking.docking_engine import dock_molecule  # noqa: PLC0415

        receptor_asset = probe.get("receptor_asset")
        result = dock_molecule(smiles, receptor_asset)
        score = result.get("binding_affinity") or result.get("score")
        if score is None:
            return None, [], "Docking returned no binding_affinity or score field."

        h_bonds = result.get("h_bond_residues", [])
        return float(score), h_bonds, None
    except Exception as exc:
        return None, [], str(exc)


def _get_reference_score(target_key: str, mode: str) -> Tuple[Optional[float], str]:
    """Return the comparison score for the target reference drug."""
    target_info = KNOWN_TARGETS.get(target_key)
    if target_info is None:
        return None, "unknown_target"

    literature_value = target_info["known_binding_kcal_mol"]
    if mode == "real_docking":
        return literature_value, "literature_benchmark_kcal_mol"
    return literature_value, "literature_anchor_for_proxy"


def _mode_reason(mode: str, probe: dict[str, Any]) -> str:
    """Explain in plain language why the selected mode was used."""
    blockers = probe.get("blockers") or []
    blocker_text = _collapse_blockers(blockers) or "No additional context available."

    if probe.get("status") == "not_checked_invalid_smiles":
        return "Binding was not checked because the SMILES could not be parsed."
    if mode == "real_docking":
        return "Real docking executed against a prepared receptor asset."
    if mode == "fallback_proxy":
        return (
            "Proxy score used because the target has a nominal real-docking path, "
            f"but it is currently blocked or failed: {blocker_text}"
        )
    if mode == "scaffold_proxy":
        return (
            "Proxy score used because no active target-specific real-docking path is available "
            f"for this request: {blocker_text}"
        )
    return blocker_text


def _binding_evidence_level(mode: str) -> str:
    if mode == "real_docking":
        return "real_docking"
    if mode == "scaffold_proxy":
        return "proxy_screening"
    if mode == "fallback_proxy":
        return "fallback_proxy"
    return "unavailable"


def _collapse_blockers(blockers: List[str]) -> str:
    return "; ".join(item for item in blockers if item)


def _binding_checked(mode: str, real_docking_status: str, candidate_score: Optional[float]) -> bool:
    """Distinguish true not-checked states from checked-but-unavailable paths."""
    if real_docking_status == "not_checked_invalid_smiles":
        return False
    if candidate_score is not None:
        return True
    if mode in {"real_docking", "scaffold_proxy", "fallback_proxy"}:
        return True
    return real_docking_status in {"blocked", "runtime_failed", "unsupported_target"}


def _interpret_binding(
    candidate_score: Optional[float],
    reference_score: Optional[float],
    delta: Optional[float],
    mode: str,
    target_key: str,
    mode_reason: str,
) -> str:
    """Generate a plain-language interpretation of the binding result."""
    if candidate_score is None:
        return (
            "Binding could not be estimated. The molecule may be invalid, RDKit may be unavailable, "
            f"or the docking path is blocked. Reason: {mode_reason}"
        )

    target_info = KNOWN_TARGETS.get(target_key, {})
    reference_drug = target_info.get("reference_drug", "reference drug")

    if mode == "real_docking":
        if delta is not None and delta <= BETTER_THAN_REFERENCE_DELTA:
            return (
                f"AutoDock Vina predicts this molecule binds {abs(delta):.1f} kcal/mol better than "
                f"{reference_drug} at {target_info.get('description', target_key)}. "
                "This is a computational docking result, not experimental proof."
            )
        if delta is not None and delta <= ACCEPTABLE_DELTA_VS_REFERENCE:
            return (
                f"Predicted binding ({candidate_score:.1f} kcal/mol) is comparable to "
                f"{reference_drug} ({reference_score:.1f} kcal/mol). This supports follow-up modeling."
            )
        return (
            f"Predicted binding ({candidate_score:.1f} kcal/mol) is weaker than "
            f"{reference_drug} ({reference_score:.1f} kcal/mol)."
        )

    if mode == "fallback_proxy":
        if candidate_score <= -7.0:
            return (
                f"Structural proxy suggests moderate binding potential (proxy={candidate_score:.1f}), "
                f"but the real docking path is currently blocked. Do not treat this as demonstrated "
                f"target engagement. Reason: {mode_reason}"
            )
        return (
            f"Only a fallback structural proxy was available (proxy={candidate_score:.1f}). "
            f"Reason: {mode_reason}"
        )

    if mode == "scaffold_proxy":
        if candidate_score <= -7.0:
            return (
                f"Scaffold similarity proxy suggests moderate binding potential (proxy={candidate_score:.1f}). "
                "This is a structural estimate only, not a docking result."
            )
        if candidate_score <= -5.5:
            return (
                f"Scaffold proxy suggests weak-to-moderate binding potential (proxy={candidate_score:.1f}). "
                f"Structural similarity to {reference_drug} is limited."
            )
        return (
            f"Scaffold proxy suggests poor binding potential (proxy={candidate_score:.1f}). "
            f"Structural similarity to {reference_drug} is low."
        )

    return f"Binding is unavailable. Reason: {mode_reason}"


def _canonical_binding_state(
    binding_checked: bool,
    mode: str,
    real_docking_status: str,
) -> str:
    """
    Map the binding path outcome to one of five canonical state labels.

    not_checked           — binding path never evaluated (e.g. invalid SMILES)
    checked_unavailable   — binding was inspected but no score or proxy could be produced
    attempted_failed      — real docking was attempted but the runtime failed; fell back to proxy
    proxy_intentional     — a proxy path was used intentionally (no active real-docking path exists,
                            or the nominal path is blocked and the system fell to structural proxy)
    real_docking_executed — AutoDock Vina completed and returned a usable binding score
    """
    if not binding_checked:
        return "not_checked"
    if mode == "real_docking" and real_docking_status == "executed":
        return "real_docking_executed"
    if mode == "fallback_proxy" and real_docking_status == "runtime_failed":
        return "attempted_failed"
    if mode in {"fallback_proxy", "scaffold_proxy"}:
        return "proxy_intentional"
    # mode == "unavailable" with binding_checked=True: the path ran but produced nothing usable
    return "checked_unavailable"


def build_binding_provenance(binding_result: dict) -> dict:
    """
    Build one canonical binding provenance block from the active binding result.

    This is the only place that converts internal binding-path state into the
    outward-facing provenance record used by pipeline, API, chat, and reports.
    """
    probe = dict(binding_result.get("real_docking_probe") or {})
    mode = str(binding_result.get("mode", "unavailable"))
    real_docking_status = str(binding_result.get("real_docking_status", "blocked"))
    candidate_score = binding_result.get("docking_score")
    comparator_score = binding_result.get("reference_score")
    delta = binding_result.get("delta_vs_reference")
    final_reason = str(
        binding_result.get("interpretation")
        or binding_result.get("mode_reason")
        or "Binding interpretation not available."
    )
    binding_checked = _binding_checked(mode, real_docking_status, candidate_score)
    key_interactions_available = bool(
        list(binding_result.get("key_h_bonds") or []) or list(binding_result.get("key_hydrophobic") or [])
    )
    evidence_level = str(binding_result.get("evidence_level", _binding_evidence_level(mode)))
    comparator_name = str(binding_result.get("reference_drug", "unknown"))
    blocking_detail = (
        str(binding_result.get("real_docking_failure") or "").strip()
        or _collapse_blockers(list(probe.get("blockers") or []))
    )
    binding_state = _canonical_binding_state(binding_checked, mode, real_docking_status)

    if not binding_checked:
        path_summary = "Binding was not checked because the SMILES could not be parsed."
    elif mode == "real_docking" and real_docking_status == "executed":
        path_summary = "Real docking executed successfully against a prepared receptor asset."
    elif mode == "fallback_proxy" and real_docking_status == "runtime_failed":
        path_summary = (
            "Real docking was attempted but failed at runtime, so the module fell back to a structural proxy."
        )
    elif mode == "fallback_proxy":
        path_summary = (
            "Fallback proxy path was used because the nominal real-docking path is currently blocked "
            "(not attempted and failed, but confirmed blocked before any run)."
        )
    elif mode == "scaffold_proxy":
        path_summary = (
            "Scaffold proxy path was used intentionally because no active target-specific real-docking path was available."
        )
    else:
        # binding_checked=True, mode=unavailable: the path ran fully but produced no usable score or proxy.
        path_summary = (
            "Binding was checked but no usable score or proxy could be produced. "
            "This is distinct from 'not checked': the path ran to completion but returned nothing actionable."
        )

    comparator_summary = (
        f"Comparator: {comparator_name} scored {_format_score(comparator_score)} and the candidate scored "
        f"{_format_score(candidate_score)} (delta {_format_delta(delta)})."
        if comparator_score is not None or candidate_score is not None or delta is not None
        else f"Comparator: {comparator_name}; no candidate/comparator score pair was available."
    )

    blocker_summary = ""
    if mode != "real_docking" and blocking_detail:
        blocker_summary = f" Real-docking blocker or failure: {blocking_detail}."

    interaction_summary = (
        " Key interaction residues were returned."
        if key_interactions_available
        else " Key interaction residues were not available."
    )

    provenance = {
        "binding_checked": binding_checked,
        "binding_state": binding_state,
        "binding_mode": mode,
        "binding_mode_reason": str(binding_result.get("mode_reason", "")),
        "real_docking_status": real_docking_status,
        "real_docking_probe": probe,
        "real_docking_failure": binding_result.get("real_docking_failure"),
        "receptor_asset_checked": bool(probe.get("receptor_asset_checked", False)),
        "receptor_asset_available": bool(probe.get("receptor_asset_available", False)),
        "docking_engine_checked": bool(probe.get("docking_engine_checked", False)),
        "docking_engine_available": bool(probe.get("docking_engine_available", False)),
        "comparator_name": comparator_name,
        "comparator_score": comparator_score,
        "candidate_score": candidate_score,
        "delta_vs_reference": delta,
        "key_interactions_available": key_interactions_available,
        "evidence_level": evidence_level,
        "final_binding_reason": final_reason,
    }
    provenance["provenance_explanation"] = (
        f"{path_summary} {comparator_summary} Evidence strength: {evidence_level.replace('_', ' ')}."
        f"{blocker_summary}{interaction_summary} Final binding interpretation: {final_reason}"
    )
    return provenance


def build_binding_evidence(binding_result: dict) -> dict:
    """Expose stable binding evidence fields for validation, API, and reports."""
    provenance = build_binding_provenance(binding_result)
    return {
        "binding_checked": provenance["binding_checked"],
        "binding_state": provenance["binding_state"],
        "binding_mode": provenance["binding_mode"],
        "binding_evidence_level": provenance["evidence_level"],
        "final_binding_reason": provenance["final_binding_reason"],
        "binding_provenance": provenance,
        "binding_provenance_explanation": provenance["provenance_explanation"],
    }


def _format_score(score: Optional[float]) -> str:
    if score is None:
        return "N/A"
    return f"{score:.2f}"


def _format_delta(delta: Optional[float]) -> str:
    if delta is None:
        return "N/A"
    return f"{delta:+.2f}"


def run_binding_evaluation(
    smiles: str,
    target: str,
    reference_drug: Optional[str] = None,
) -> dict:
    """
    Evaluate target engagement for a molecule and compare it to the reference.

    real_docking is reported only when the docking runtime was actually ready
    and returned a score. Otherwise the mode falls back conservatively.
    """
    print(f"\n[TargetEngagement] Evaluating {smiles[:50]} vs {target}...")

    target_key = _normalize_target_key(target)
    rdkit_ok = _try_load_rdkit()
    notes: List[str] = []
    invalid_smiles = False

    target_info = KNOWN_TARGETS.get(target_key, {})
    reference_name = reference_drug or target_info.get("reference_drug", "unknown")

    probe = _build_real_docking_probe(target_key)
    if rdkit_ok and _Chem is not None and _Chem.MolFromSmiles(smiles) is None:
        invalid_smiles = True
        probe["status"] = "not_checked_invalid_smiles"
        blockers = list(probe.get("blockers") or [])
        if "Input SMILES could not be parsed." not in blockers:
            blockers.append("Input SMILES could not be parsed.")
        probe["blockers"] = blockers
        mode = "unavailable"
        notes.append("Binding was not checked because the SMILES could not be parsed.")
    else:
        mode = _detect_mode(target_key, probe)
    print(f"   [Binding] Mode selected: {mode}")

    docking_score: Optional[float] = None
    reference_score_val: Optional[float] = None
    delta: Optional[float] = None
    h_bonds: List[str] = []
    hydrophobic: List[str] = []
    confidence = "none"
    data_source = "heuristic_proxy"
    real_docking_status = probe.get("status", "blocked")
    real_docking_failure: Optional[str] = None

    if mode == "real_docking":
        docking_score, h_bonds, runtime_failure = _run_real_docking(smiles, target_key, probe)
        if docking_score is not None:
            reference_score_val, _ = _get_reference_score(target_key, mode)
            if reference_score_val is not None:
                delta = round(docking_score - reference_score_val, 2)

            confidence = "high"
            data_source = "real_docking"
            real_docking_status = "executed"
            print(
                f"   [Binding] Real docking score = {docking_score:.2f} kcal/mol, "
                f"ref = {reference_score_val}, delta = {delta}"
            )
        else:
            mode = "fallback_proxy" if rdkit_ok else "unavailable"
            real_docking_status = "runtime_failed"
            real_docking_failure = runtime_failure or "Real docking failed without a detailed error."
            probe_blockers = list(probe.get("blockers") or [])
            if real_docking_failure not in probe_blockers:
                probe_blockers.append(real_docking_failure)
            probe["blockers"] = probe_blockers
            probe["status"] = real_docking_status
            notes.append(
                "Real docking was attempted but did not return a usable result. "
                f"Failure: {real_docking_failure}"
            )

    if mode in {"fallback_proxy", "scaffold_proxy"}:
        docking_score, proxy_explanation = _scaffold_proxy_score(smiles, target_key)
        reference_score_val, _ = _get_reference_score(target_key, mode)

        if docking_score is not None and reference_score_val is not None:
            delta = round(docking_score - reference_score_val, 2)

        confidence = "medium" if mode == "scaffold_proxy" and target_key in KNOWN_TARGETS else "low"
        data_source = "heuristic_proxy"

        if mode == "fallback_proxy" and not real_docking_failure:
            blockers = probe.get("blockers") or []
            real_docking_failure = _collapse_blockers(blockers) or "Real docking path is blocked."

        notes.append(
            (
                "FALLBACK PROXY MODE: real docking for this target is currently blocked or failed. "
                "Scores are structural estimates, not physical binding energies."
            )
            if mode == "fallback_proxy"
            else
            "SCAFFOLD PROXY MODE: no active target-specific real-docking path is available. "
            "Scores are structural estimates, not physical binding energies."
        )
        notes.append(proxy_explanation)
        if real_docking_failure:
            notes.append(f"Real docking failure/blocker: {real_docking_failure}")
        print(f"   [Binding] Proxy score = {docking_score}, ref = {reference_score_val}")

    if mode == "unavailable":
        confidence = "none"
        data_source = "external_unavailable" if probe.get("target_supported") else "heuristic_proxy"
        if invalid_smiles:
            real_docking_failure = "Invalid SMILES"
        elif not rdkit_ok:
            notes.append("RDKit is unavailable, so no proxy score could be produced.")
        blockers = probe.get("blockers") or []
        if blockers:
            real_docking_failure = _collapse_blockers(blockers)
            notes.extend(blockers)
        else:
            notes.append("Binding could not be estimated with the current tooling.")

    mode_reason = _mode_reason(mode, probe)
    if not real_docking_failure and mode == "fallback_proxy":
        blockers = probe.get("blockers") or []
        real_docking_failure = _collapse_blockers(blockers) or "Real docking path is blocked."

    interpretation = _interpret_binding(
        docking_score,
        reference_score_val,
        delta,
        mode,
        target_key,
        mode_reason,
    )
    print(f"   [Binding] {interpretation[:100]}...")

    result = {
        "smiles": smiles,
        "target": target,
        "reference_drug": reference_name,
        "docking_score": docking_score,
        "reference_score": reference_score_val,
        "delta_vs_reference": delta,
        "key_h_bonds": h_bonds,
        "key_hydrophobic": hydrophobic,
        "mode": mode,
        "confidence": confidence,
        "data_source": data_source,
        "evidence_level": _binding_evidence_level(mode),
        "mode_reason": mode_reason,
        "real_docking_status": real_docking_status,
        "real_docking_failure": real_docking_failure,
        "real_docking_probe": probe,
        "interpretation": interpretation,
        "rdkit_available": rdkit_ok,
        "notes": notes,
    }
    result.update(build_binding_evidence(result))

    print(
        f"[TargetEngagement] Done. mode={mode}, score={docking_score}, "
        f"delta={delta}, confidence={confidence}, docking_status={real_docking_status}"
    )
    return result


if __name__ == "__main__":
    test_cases = [
        ("CN(C)C(=N)NC(=N)N", "insulin_receptor"),
        ("Fc1cc(c(F)cc1F)CC(N)CC(=O)N1CCn2c(nnc2CC1)C(F)(F)F", "dpp4"),
        ("Cc1ccc(NC(=O)c2ccc(N)cc2)cc1", "insulin_receptor"),
    ]

    for smiles, target in test_cases:
        print(f"\n{'=' * 60}")
        print(f"SMILES: {smiles[:50]}")
        print(f"Target: {target}")
        result = run_binding_evaluation(smiles, target)
        print(
            f"  mode={result['mode']}, score={result['docking_score']}, "
            f"ref={result['reference_score']}, delta={result['delta_vs_reference']}, "
            f"confidence={result['confidence']}"
        )
        print(f"  reason={result['mode_reason']}")
