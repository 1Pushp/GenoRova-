import { useEffect, useMemo, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const BACKEND_ORIGIN = API_BASE_URL || "http://localhost:8000";
const API_PREFIX = API_BASE_URL ? `${API_BASE_URL}/api` : "/api";

const defaultStats = {
  total_molecules: 0,
  best_score: null,
  best_molecule: null,
  best_molecular_weight: null,
  prototype_status: "prototype_research_support",
  trust_note: "Computational research-support outputs only. Not experimentally validated.",
};

const apiExamples = [
  { label: "GET /health", snippet: "GET /health" },
  {
    label: "POST /generate",
    snippet: 'POST /generate\n{\n  "disease": "diabetes",\n  "count": 10\n}',
  },
  {
    label: "POST /score",
    snippet: 'POST /score\n{\n  "smiles": "YOUR_SMILES_HERE"\n}',
  },
  { label: "GET /best_molecules", snippet: "GET /best_molecules" },
];

const pricingPlans = [
  { name: "Free", price: "10 molecules/day", subtitle: "basic scoring" },
  {
    name: "Research",
    price: "$49/mo",
    subtitle: "1000 molecules, scoring, comparison, and analysis",
    featured: true,
  },
  { name: "Enterprise", price: "Contact us", subtitle: "unlimited, custom models" },
];

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function recommendationClasses(recommendation) {
  const normalized = String(recommendation || "").toLowerCase();
  if (normalized.includes("strong")) {
    return "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-400/30";
  }
  if (normalized.includes("border")) {
    return "bg-amber-400/15 text-amber-100 ring-1 ring-amber-300/30";
  }
  return "bg-slate-700 text-slate-200 ring-1 ring-slate-500/50";
}

function LoadingSpinner({ label }) {
  return (
    <div className="inline-flex items-center gap-2 text-sm text-slate-300">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
      {label}
    </div>
  );
}

function CopyButton({ value, label = "Copy", className = "" }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={`rounded-full border border-slate-600 px-3 py-1 text-xs font-medium text-slate-200 transition hover:border-teal-400 hover:text-white ${className}`}
    >
      {copied ? "Copied" : label}
    </button>
  );
}

function PropertyGrid({ scoreData }) {
  const properties = [
    ["MW", scoreData.molecular_weight],
    ["LogP", scoreData.logp],
    ["QED", scoreData.qed_score],
    ["SA Score", scoreData.sa_score],
    ["Lipinski", scoreData.passes_lipinski ? "Pass" : "Fail"],
    ["Model Score", scoreData.clinical_score],
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {properties.map(([label, value]) => (
        <div key={label} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
          <div className="mt-2 break-all text-lg font-semibold text-slate-900">{String(value)}</div>
        </div>
      ))}
    </div>
  );
}

export default function PlatformApp() {
  const [stats, setStats] = useState(defaultStats);
  const [generateForm, setGenerateForm] = useState({
    disease: "diabetes",
    count: 20,
    referenceSmiles: "",
  });
  const [generateResults, setGenerateResults] = useState([]);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [generateError, setGenerateError] = useState("");

  const [scoreInput, setScoreInput] = useState("");
  const [scoreData, setScoreData] = useState(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [scoreError, setScoreError] = useState("");

  useEffect(() => {
    fetchStats();
  }, []);

  async function fetchStats() {
    try {
      const response = await fetch(`${API_PREFIX}/stats`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to load platform statistics.");
      }
      setStats(payload);
    } catch {
      setStats(defaultStats);
    }
  }

  function updateGenerateForm(key, value) {
    setGenerateForm((current) => ({ ...current, [key]: value }));
  }

  async function handleGenerate(event) {
    event.preventDefault();
    setGenerateLoading(true);
    setGenerateError("");

    try {
      const response = await fetch(`${API_PREFIX}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          disease: generateForm.disease,
          count: Number(generateForm.count),
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to generate candidates right now.");
      }

      setGenerateResults(payload.molecules || []);
      if (!payload.molecules?.length && payload.message) {
        setGenerateError(payload.message);
      }
    } catch (error) {
      setGenerateResults([]);
      setGenerateError(error.message);
    } finally {
      setGenerateLoading(false);
    }
  }

  async function handleScore(event) {
    event.preventDefault();
    if (!scoreInput.trim()) {
      setScoreError("Please enter a SMILES string to score.");
      return;
    }

    setScoreLoading(true);
    setScoreError("");

    try {
      const response = await fetch(`${API_PREFIX}/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ smiles: scoreInput.trim() }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to score that molecule.");
      }

      setScoreData(payload);
    } catch (error) {
      setScoreData(null);
      setScoreError(error.message);
    } finally {
      setScoreLoading(false);
    }
  }

  function downloadCsv() {
    if (!generateResults.length) return;

    const rows = [
      ["smiles", "molecular_weight", "qed_score", "clinical_score", "recommendation"],
      ...generateResults.map((row) => [
        row.smiles,
        row.molecular_weight,
        row.qed_score,
        row.clinical_score,
        row.recommendation,
      ]),
    ];

    const csvContent = rows
      .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `genorova_${generateForm.disease}_candidates.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const bestMoleculeProperties = useMemo(
    () => [
      ["SMILES", stats.best_molecule],
      ["Model Score", formatNumber(stats.best_score, 4)],
      ["Molecular Weight", stats.best_molecular_weight ? `${stats.best_molecular_weight} Da` : "-"],
      ["Validation", "Computational ranking only"],
      ["Status", stats.prototype_status || "prototype_research_support"],
    ],
    [stats]
  );

  return (
    <div className="min-h-screen bg-[#0A0F1E] text-white">
      <section className="border-b border-white/10 bg-[#0A0F1E]">
        <div className="mx-auto max-w-7xl px-6 py-20 lg:px-8">
          <div className="max-w-4xl">
            <div className="inline-flex rounded-full border border-teal-400/30 bg-teal-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] text-teal-200">
              Genorova AI
            </div>
            <h1 className="mt-8 text-4xl font-semibold tracking-tight text-white sm:text-6xl">
              Genorova AI - Computational Molecule Analysis Platform
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
              Score, compare, and review computational molecule outputs with explicit scientific caveats.
            </p>
            <div className="mt-6 max-w-3xl rounded-3xl border border-amber-400/30 bg-amber-400/10 px-5 py-4 text-sm leading-7 text-amber-100">
              Prototype status: generation quality is currently limited. The most reliable demo path is scoring, explaining, and comparing known valid molecules or previously scored results.
            </div>
          </div>

          <div className="mt-12 grid gap-4 sm:grid-cols-3">
            <div className="rounded-3xl border border-white/10 bg-white/5 p-6 backdrop-blur transition hover:border-teal-400/30 hover:bg-white/10">
              <div className="text-3xl font-semibold text-white">{stats.total_molecules}</div>
              <div className="mt-2 text-sm text-slate-300">molecules</div>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/5 p-6 backdrop-blur transition hover:border-teal-400/30 hover:bg-white/10">
              <div className="text-3xl font-semibold text-white">{formatNumber(stats.best_score, 4)}</div>
              <div className="mt-2 text-sm text-slate-300">best score</div>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/5 p-6 backdrop-blur transition hover:border-teal-400/30 hover:bg-white/10">
              <div className="text-3xl font-semibold text-white">{stats.prototype_status || "prototype"}</div>
              <div className="mt-2 text-sm text-slate-300">status</div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-slate-50 text-slate-900">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:px-8">
          <div className="grid gap-8 xl:grid-cols-[1.1fr,1.4fr]">
            <div className="rounded-[32px] bg-[#0A0F1E] p-8 text-white shadow-2xl">
              <div className="text-sm font-semibold uppercase tracking-[0.24em] text-teal-300">Live Demo</div>
              <h2 className="mt-4 text-3xl font-semibold">Show Ranked Molecules</h2>
              <p className="mt-4 text-sm leading-6 text-slate-300">
                If no trustworthy fresh generation is available, Genorova will explicitly fall back to previously scored valid molecules or known references instead of inventing a success.
              </p>
              <form className="mt-8 space-y-6" onSubmit={handleGenerate}>
                <div>
                  <label className="text-sm font-medium text-slate-200">Disease</label>
                  <select
                    value={generateForm.disease}
                    onChange={(event) => updateGenerateForm("disease", event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none ring-0 transition focus:border-teal-400"
                  >
                    <option value="diabetes" className="text-slate-900">Diabetes</option>
                    <option value="infection" className="text-slate-900">Infectious Disease</option>
                  </select>
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-200">Molecule count</label>
                    <span className="text-sm text-teal-300">{generateForm.count}</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="100"
                    step="10"
                    value={generateForm.count}
                    onChange={(event) => updateGenerateForm("count", event.target.value)}
                    className="mt-3 w-full accent-[#1D9E75]"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-200">SMILES input (optional)</label>
                  <textarea
                    rows={3}
                    value={generateForm.referenceSmiles}
                    onChange={(event) => updateGenerateForm("referenceSmiles", event.target.value)}
                    placeholder="Optional reference molecule, for example: COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"
                    className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-teal-400"
                  />
                </div>

                <button
                  type="submit"
                  disabled={generateLoading}
                  className="flex w-full items-center justify-center rounded-2xl bg-[#1D9E75] px-6 py-4 text-base font-semibold text-white transition hover:bg-[#178663] disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {generateLoading ? <LoadingSpinner label="Loading safe results..." /> : "Show Ranked Molecules"}
                </button>

                {generateError ? (
                  <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                    {generateError}
                  </div>
                ) : null}
              </form>
            </div>

            <div className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-xl">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Results</div>
                  <h3 className="mt-2 text-2xl font-semibold text-slate-900">Ranked molecule table</h3>
                </div>
                <button
                  type="button"
                  onClick={downloadCsv}
                  disabled={!generateResults.length}
                  className="rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Download CSV
                </button>
              </div>

              <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200">
                <div className="overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-slate-100 text-slate-600">
                      <tr>
                        <th className="px-4 py-3">SMILES</th>
                        <th className="px-4 py-3">MW</th>
                        <th className="px-4 py-3">QED</th>
                        <th className="px-4 py-3">Model Score</th>
                        <th className="px-4 py-3">Recommendation</th>
                        <th className="px-4 py-3">Validation</th>
                        <th className="px-4 py-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white">
                      {generateResults.length ? (
                        generateResults.map((row, index) => (
                          <tr key={`${row.smiles}-${index}`} className="border-t border-slate-100">
                            <td className="max-w-xs px-4 py-4 font-mono text-xs text-slate-700">{row.smiles}</td>
                            <td className="px-4 py-4">{row.molecular_weight}</td>
                            <td className="px-4 py-4">{row.qed_score}</td>
                            <td className="px-4 py-4">{row.clinical_score}</td>
                            <td className="px-4 py-4">
                              <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${recommendationClasses(row.recommendation)}`}>
                                {row.recommendation}
                              </span>
                            </td>
                            <td className="px-4 py-4 text-xs text-slate-600">{row.validation_status || "computational_only"}</td>
                            <td className="px-4 py-4">
                              <CopyButton value={row.smiles} label="Copy SMILES" className="border-slate-300 text-slate-700" />
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan="7" className="px-4 py-10 text-center text-slate-500">
                            Run the live demo to load safe ranked molecules or honest fallback results here.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white text-slate-900">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:px-8">
          <div className="grid gap-8 lg:grid-cols-[1.1fr,1fr]">
            <div className="rounded-[32px] border border-slate-200 bg-slate-50 p-8 shadow-sm">
              <div className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Score Any Molecule</div>
              <h2 className="mt-4 text-3xl font-semibold text-slate-900">Instant molecule profiling</h2>
              <form className="mt-8 space-y-5" onSubmit={handleScore}>
                <textarea
                  rows={5}
                  value={scoreInput}
                  onChange={(event) => setScoreInput(event.target.value)}
                  placeholder="Paste a SMILES string here"
                  className="w-full rounded-3xl border border-slate-300 bg-white px-4 py-4 text-sm text-slate-900 outline-none transition focus:border-[#1D9E75]"
                />
                <button
                  type="submit"
                  disabled={scoreLoading}
                  className="flex w-full items-center justify-center rounded-2xl bg-[#1D9E75] px-6 py-4 text-base font-semibold text-white transition hover:bg-[#178663] disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {scoreLoading ? <LoadingSpinner label="Scoring..." /> : "Score This Molecule"}
                </button>
                {scoreError ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    {scoreError}
                  </div>
                ) : null}
              </form>
            </div>

            <div className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Property Card</div>
                  <h3 className="mt-2 text-2xl font-semibold text-slate-900">Scoring output</h3>
                </div>
                {scoreData ? (
                  <span className={`inline-flex rounded-full px-4 py-2 text-sm font-semibold ${recommendationClasses(scoreData.recommendation)}`}>
                    {scoreData.recommendation}
                  </span>
                ) : null}
              </div>

              <div className="mt-6">
                {scoreData ? (
                  <PropertyGrid scoreData={scoreData} />
                ) : (
                  <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-12 text-center text-slate-500">
                    Score a molecule to see MW, LogP, QED, SA Score, Lipinski, and the current model score.
                  </div>
                )}
              </div>
              {scoreData?.confidence_note ? (
                <div className="mt-6 rounded-3xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-900">
                  {scoreData.confidence_note}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="bg-[#0A0F1E]">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:px-8">
          <div className="rounded-[36px] border border-white/10 bg-white/5 p-8 shadow-2xl backdrop-blur">
            <div className="grid gap-8 lg:grid-cols-[1.4fr,1fr]">
              <div>
                <div className="text-sm font-semibold uppercase tracking-[0.24em] text-teal-300">Current Top Ranked Molecule</div>
                <h2 className="mt-4 max-w-3xl text-3xl font-semibold text-white sm:text-4xl">
                  {stats.best_molecule || "No ranked molecule currently available"}
                </h2>
                <p className="mt-6 max-w-2xl text-base leading-7 text-slate-300">
                  {stats.trust_note || "This surface reports computational ranking results only. It does not imply docking confirmation, biological efficacy, or experimental validation."}
                </p>
                <div className="mt-8 grid gap-4 sm:grid-cols-3">
                  <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
                    <div className="text-sm text-slate-400">Score</div>
                    <div className="mt-2 text-2xl font-semibold text-white">{formatNumber(stats.best_score, 4)}</div>
                  </div>
                  <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
                    <div className="text-sm text-slate-400">Validation</div>
                    <div className="mt-2 text-2xl font-semibold text-white">Computational only</div>
                  </div>
                  <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
                    <div className="text-sm text-slate-400">MW</div>
                    <div className="mt-2 text-2xl font-semibold text-white">{stats.best_molecular_weight ? `${stats.best_molecular_weight} Da` : "-"}</div>
                  </div>
                </div>
              </div>

              <div className="rounded-[28px] border border-white/10 bg-slate-950/50 p-6">
                <div className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">Properties</div>
                <div className="mt-6 space-y-4">
                  {bestMoleculeProperties.map(([label, value]) => (
                    <div key={label} className="flex items-start justify-between gap-4 border-b border-white/10 pb-4 last:border-b-0 last:pb-0">
                      <div className="text-sm text-slate-400">{label}</div>
                      <div className="max-w-[70%] break-all text-right text-sm font-medium text-white">{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-slate-50 text-slate-900">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:px-8">
          <div>
            <div className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">API Documentation</div>
            <h2 className="mt-4 text-3xl font-semibold">Platform endpoints</h2>
          </div>

          <div className="mt-10 grid gap-6 lg:grid-cols-2">
            {apiExamples.map((example) => (
              <div key={example.label} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
                <div className="flex items-center justify-between gap-4">
                  <div className="text-base font-semibold text-slate-900">{example.label}</div>
                  <CopyButton value={example.snippet} />
                </div>
                <pre className="mt-4 overflow-x-auto rounded-2xl bg-[#0A0F1E] p-5 text-sm text-slate-100">
                  <code>{example.snippet}</code>
                </pre>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white text-slate-900">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:px-8">
          <div className="text-center">
            <div className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Pricing</div>
            <h2 className="mt-4 text-3xl font-semibold">Choose the Genorova plan that fits your lab</h2>
            <p className="mt-4 text-sm leading-6 text-slate-600">
              Current demos should emphasize scoring, comparison, explanation, and properties rather than claiming robust de novo generation.
            </p>
          </div>

          <div className="mt-10 grid gap-6 lg:grid-cols-3">
            {pricingPlans.map((plan) => (
              <div
                key={plan.name}
                className={`rounded-[30px] border p-8 shadow-sm transition hover:-translate-y-1 hover:shadow-xl ${
                  plan.featured
                    ? "border-[#1D9E75] bg-[#0A0F1E] text-white"
                    : "border-slate-200 bg-slate-50 text-slate-900"
                }`}
              >
                <div className="text-sm font-semibold uppercase tracking-[0.22em] opacity-70">{plan.name}</div>
                <div className="mt-6 text-4xl font-semibold">{plan.price}</div>
                <p className={`mt-4 text-sm leading-6 ${plan.featured ? "text-slate-300" : "text-slate-600"}`}>
                  {plan.subtitle}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-white/10 bg-[#0A0F1E]">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-8 text-sm text-slate-300 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>Built by Pushp Dwivedi. Prototype research-support outputs only.</div>
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:gap-6">
            <a href="mailto:pushpdwivedi911@gmail.com" className="transition hover:text-white">
              pushpdwivedi911@gmail.com
            </a>
            <a href="https://github.com/1Pushp/GenoRova-" target="_blank" rel="noreferrer" className="transition hover:text-white">
              github.com/1Pushp/GenoRova-
            </a>
            <a href={`${BACKEND_ORIGIN}/docs`} target="_blank" rel="noreferrer" className="transition hover:text-white">
              API Docs
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
