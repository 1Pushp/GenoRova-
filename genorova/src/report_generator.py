"""
Conservative HTML report generator for the active Genorova science path.

The active report is intentionally standardized to one canonical workflow:

- disease program: diabetes
- target: DPP4
- comparator: sitagliptin

This keeps the report aligned with the live API and chat surfaces and avoids
mixing legacy diabetes/infection stories in the same outward-facing artifact.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from datetime import datetime

import pandas as pd

from science_evidence import (
    ACTIVE_DISEASE,
    ACTIVE_PROGRAM_LABEL,
    ACTIVE_PROGRAM_SUMMARY,
    ACTIVE_REFERENCE_DRUG,
    ACTIVE_SCOPE_NOTE,
    evaluate_candidate_rows,
)
from validation.ranking import best_candidate_rationale

ROOT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = ROOT_DIR / "outputs"
REPORT_PATH = OUTPUT_DIR / "genorova_report.html"
GENERATED_DIR = OUTPUT_DIR / "generated"


def _load_active_candidates() -> tuple[list[dict], str, bool]:
    """Load the active candidate source rows for report generation."""
    candidates_path = GENERATED_DIR / f"{ACTIVE_DISEASE}_candidates_validated.csv"
    cli_path = GENERATED_DIR / f"{ACTIVE_DISEASE}_cli_generated.csv"

    if candidates_path.exists():
        df = pd.read_csv(candidates_path)
        return df.to_dict("records"), "precomputed_ranked_candidates", False

    if cli_path.exists():
        df = pd.read_csv(cli_path)
        return df.to_dict("records"), "cli_ranked_candidates", False

    from api import _reference_smiles_for_disease  # noqa: PLC0415

    rows = [{"smiles": smiles} for smiles in _reference_smiles_for_disease(ACTIVE_DISEASE)]
    return rows, "known_reference_fallback", True


def _report_candidates() -> list[dict]:
    """Evaluate the report candidate pool under the active workflow."""
    rows, result_source, fallback_used = _load_active_candidates()
    if not rows:
        return []

    return evaluate_candidate_rows(
        rows,
        result_source=result_source,
        fallback_used=fallback_used,
        max_candidates=12,
        confidence_note=(
            "Report generated under the active DPP4 comparator workflow. "
            "This is a computational evidence screen, not experimental proof."
        ),
        validation_status="canonical_report_review",
        limitations=[
            ACTIVE_SCOPE_NOTE,
            "The report is intentionally limited to the active diabetes / DPP4 path.",
            "Proxy, heuristic, and fallback fields are labeled conservatively.",
        ],
        recommended_next_step="Use this report for computational review only, then confirm with orthogonal modeling or experiment.",
    )


def _summary_cards(candidates: list[dict]) -> str:
    non_rejected = sum(1 for c in candidates if c.get("final_decision") != "reject")
    top = candidates[0] if candidates else {}
    top_score = top.get("rank_score") or top.get("clinical_score") or 0.0
    top_label = top.get("rank_label") or top.get("recommendation") or "no candidates"
    return f"""
    <section class="cards">
      <div class="card">
        <div class="card-value">{len(candidates)}</div>
        <div class="card-label">Candidates Revalidated</div>
      </div>
      <div class="card">
        <div class="card-value">{non_rejected}</div>
        <div class="card-label">Non-Rejected Candidates</div>
      </div>
      <div class="card">
        <div class="card-value">{top_score:.4f}</div>
        <div class="card-label">Top Evidence-Weighted Score</div>
      </div>
      <div class="card">
        <div class="card-value" style="font-size:1rem">{escape(top_label)}</div>
        <div class="card-label">Top Candidate Label</div>
      </div>
      <div class="card">
        <div class="card-value">{escape(ACTIVE_REFERENCE_DRUG)}</div>
        <div class="card-label">Canonical Comparator</div>
      </div>
    </section>
    """


def _candidate_table(candidates: list[dict]) -> str:
    if not candidates:
        return "<p class='empty'>No candidate rows were available for the active report path.</p>"

    rows = []
    for index, candidate in enumerate(candidates, 1):
        risks = candidate.get("major_risks", [])
        risks_text = "; ".join(risks[:2]) if risks else "None highlighted"
        rank_label = candidate.get("rank_label", candidate.get("recommendation", "unknown"))
        rows.append(
            f"""
            <tr>
              <td>{index}</td>
              <td class="mono" title="{escape(candidate['smiles'])}">{escape(candidate['smiles'][:42])}</td>
              <td>{candidate.get('rank_score', candidate.get('clinical_score', 0)):.4f}</td>
              <td>{escape(str(candidate.get('final_decision', 'unknown')).replace('_', ' '))}</td>
              <td>{escape(str(candidate.get('novelty_status', 'uncertain')))}</td>
              <td>{escape(str(candidate.get('docking_mode', 'unavailable')))}</td>
              <td>{candidate.get('delta_vs_reference')}</td>
              <td>{escape(str(candidate.get('hepatotoxicity_risk', 'unknown')))}</td>
              <td>{escape(str(candidate.get('herg_risk', 'unknown')))}</td>
              <td>{escape(str(candidate.get('cyp_interaction_risk', 'unknown')))}</td>
              <td>{escape(str(candidate.get('evidence_level', 'screening_only')))}</td>
              <td>{escape(risks_text)}</td>
            </tr>
            """
        )

    return f"""
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>SMILES</th>
          <th>Model Score</th>
          <th>Final Decision</th>
          <th>Novelty</th>
          <th>Docking Mode</th>
          <th>Delta vs {escape(ACTIVE_REFERENCE_DRUG)}</th>
          <th>DILI</th>
          <th>hERG</th>
          <th>CYP</th>
          <th>Evidence Level</th>
          <th>Highlighted Risks</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def _best_candidate_section(candidates: list[dict]) -> str:
    if not candidates:
        return """
        <section>
          <h2>No Active Candidate Available</h2>
          <p>The current active workflow did not find a candidate suitable for display.</p>
        </section>
        """

    best = candidates[0]
    ledger = best.get("evidence_ledger", {})
    risks = best.get("major_risks", [])
    risk_items = "".join(f"<li>{escape(risk)}</li>" for risk in risks) or "<li>None highlighted</li>"

    # Use canonical rank_label — never say "best molecule" without evidence gates
    rank_label   = best.get("rank_label") or best.get("recommendation", "low-priority computational result")
    rank_score   = best.get("rank_score") or best.get("clinical_score", 0.0)

    # Canonical rationale from ranking module
    rationale = best_candidate_rationale(candidates)

    # Penalty breakdown for transparency
    breakdown = best.get("rank_breakdown", {})
    penalties = breakdown.get("penalties_applied", [])
    penalty_items = "".join(f"<li>{escape(p)}</li>" for p in penalties) or "<li>None applied</li>"

    ledger_rows = [
        ("Program", best.get("program_label")),
        ("Target", best.get("target")),
        ("Reference drug", best.get("reference_drug")),
        ("Evidence-weighted rank score", f"{rank_score:.4f}"),
        ("Rank label", rank_label),
        ("Final decision", best.get("final_decision")),
        ("Novelty status", best.get("novelty_status")),
        ("PAINS", "alert detected" if best.get("is_pains") else "none detected"),
        ("Docking mode", best.get("docking_mode")),
        ("Binding mode reason", best.get("binding_mode_reason")),
        ("Real docking status", best.get("real_docking_status")),
        ("Real docking failure", best.get("real_docking_failure")),
        ("Comparator delta", best.get("delta_vs_reference")),
        ("Hepatotoxicity", best.get("hepatotoxicity_risk")),
        ("hERG", best.get("herg_risk")),
        ("CYP interaction", best.get("cyp_interaction_risk")),
        ("Confidence level", best.get("confidence_level")),
        ("Evidence level", best.get("evidence_level")),
        ("Legacy score (reference only)", best.get("legacy_clinical_score")),
    ]

    rows_html = "".join(
        f"<tr><td>{escape(str(label))}</td><td>{escape(str(value))}</td></tr>"
        for label, value in ledger_rows
    )

    return f"""
    <section>
      <h2>Top-Ranked Candidate — <em>{escape(rank_label)}</em></h2>
      <p class="summary">{escape(best.get('summary', 'No summary available.'))}</p>
      <div class="best-layout">
        <div>
          <div class="mono best-smiles">{escape(best.get('smiles', ''))}</div>
          <p class="caption">
            Evidence-weighted rank score: {rank_score:.4f}.
            This label is assigned by the canonical evidence-quality gate
            (validation.ranking), not by raw score alone.
          </p>
        </div>
        <div>
          <table class="detail-table">
            <tbody>{rows_html}</tbody>
          </table>
        </div>
      </div>
      <div class="ledger">
        <h3>Evidence Ledger</h3>
        <p>{escape(rationale)}</p>
        <h4>Major risks</h4>
        <ul>{risk_items}</ul>
        <h4>Rank penalties applied</h4>
        <ul>{penalty_items}</ul>
      </div>
    </section>
    """


def _limitations_section() -> str:
    items = [
        ACTIVE_SCOPE_NOTE,
        "The live report does not claim novelty unless that status is explicitly supported.",
        "Binding may still be scaffold_proxy or fallback_proxy if real docking is unavailable or blocked.",
        "ADMET outputs are heuristic screening signals, not validated safety data.",
        "This report is appropriate for faculty/demo review, not clinical or investment claims of proof.",
    ]
    list_items = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"""
    <section>
      <h2>Scientific Boundaries</h2>
      <ul>{list_items}</ul>
    </section>
    """


def _html(candidates: list[dict], generated_at: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GenorovaAI Active Workflow Report</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: #f4f6f8;
      color: #14202b;
    }}
    header {{
      background: linear-gradient(135deg, #0f172a, #134e4a);
      color: white;
      padding: 40px 24px 28px;
    }}
    header h1 {{ margin: 0 0 8px; font-size: 2rem; }}
    header p {{ margin: 8px 0 0; max-width: 920px; line-height: 1.6; }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 20px 48px;
    }}
    section {{
      background: white;
      border-radius: 20px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow: 0 14px 42px -28px rgba(15, 23, 42, 0.35);
    }}
    .cards {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}
    .card {{
      background: linear-gradient(180deg, #0f172a, #1f2937);
      color: white;
      border-radius: 18px;
      padding: 18px;
    }}
    .card-value {{ font-size: 1.6rem; font-weight: 700; }}
    .card-label {{ font-size: 0.85rem; color: #cbd5e1; margin-top: 4px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #0f172a;
      color: white;
      position: sticky;
      top: 0;
    }}
    .mono {{
      font-family: "Cascadia Mono", "Consolas", monospace;
      word-break: break-all;
    }}
    .best-layout {{
      display: grid;
      gap: 24px;
      grid-template-columns: minmax(280px, 1.2fr) minmax(280px, 1fr);
      align-items: start;
    }}
    .best-smiles {{
      font-size: 1rem;
      padding: 14px;
      border-radius: 14px;
      background: #f8fafc;
      border: 1px solid #dbe4ea;
    }}
    .detail-table td:first-child {{
      width: 38%;
      font-weight: 600;
      color: #334155;
    }}
    .ledger {{
      margin-top: 18px;
      padding: 16px;
      border-radius: 14px;
      background: #eefbf7;
      border: 1px solid #b7e5d6;
    }}
    .summary {{
      line-height: 1.7;
    }}
    .caption {{
      color: #475569;
      line-height: 1.6;
    }}
    .empty {{
      color: #475569;
    }}
    footer {{
      padding: 0 20px 36px;
      text-align: center;
      color: #64748b;
      font-size: 0.9rem;
    }}
    @media (max-width: 860px) {{
      .best-layout {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>GenorovaAI Active Workflow Report</h1>
    <p>{escape(ACTIVE_PROGRAM_SUMMARY)}</p>
    <p>
      Generated: {escape(generated_at)}<br>
      This report is intentionally constrained to one evidence-backed story so the live product,
      API, and HTML outputs use the same scientific framing.
    </p>
  </header>
  <main>
    {_summary_cards(candidates)}
    <section>
      <h2>Candidate Review Table</h2>
      <p class="summary">
        Candidates are re-evaluated under the active workflow before being shown here. Scores are adjusted
        downward when novelty is uncertain, binding remains proxy-only, or the source path is a fallback.
      </p>
      {_candidate_table(candidates)}
    </section>
    {_best_candidate_section(candidates)}
    {_limitations_section()}
  </main>
  <footer>
    GenorovaAI computational research-support report. Outputs remain screening signals only.
  </footer>
</body>
</html>"""


def generate_report(
    diabetes_df: pd.DataFrame | None = None,
    infection_df: pd.DataFrame | None = None,
    runtime_min: float = 0.0,
    output_path: str | None = None,
) -> str:
    """
    Generate the active Genorova HTML report.

    The signature is kept stable for existing callers, but the report now
    intentionally ignores the legacy infection story and rebuilds the active
    candidate table from the canonical diabetes / DPP4 workflow.
    """
    del diabetes_df, infection_df, runtime_min

    candidates = _report_candidates()
    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")
    html = _html(candidates, generated_at)

    destination = Path(output_path) if output_path else REPORT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return str(destination)


if __name__ == "__main__":
    path = generate_report()
    print(f"Report generated: {path}")
