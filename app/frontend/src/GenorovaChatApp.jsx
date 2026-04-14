import { startTransition, useEffect, useRef, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const BACKEND_ORIGIN = API_BASE_URL || "http://localhost:8000";
const API_PREFIX = API_BASE_URL ? `${API_BASE_URL}/api` : "/api";

const defaultStats = {
  total_molecules: 100,
  best_score: 0.9649,
  best_molecule: "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2",
  best_molecular_weight: 286,
  best_docking_affinity: -5.041,
  best_ca7_ki: "6.4 nM",
};

const starterPrompts = [
  "Generate a drug candidate for tuberculosis with good oral drug-likeness and low toxicity",
  "Score this molecule: CCO",
  "Explain this molecule simply: COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2",
  "Compare these two molecules: CCO vs CCN",
  "Suggest a safer analog for COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2",
  "Show full chemical and pharmacological profile for the best Genorova molecule",
];

const modeOptions = ["simple", "scientific", "expert"];

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function formatLabel(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function recommendationTone(recommendation) {
  const normalized = String(recommendation || "").toLowerCase();
  if (normalized.includes("strong")) return "border-emerald-300 bg-emerald-50 text-emerald-700";
  if (normalized.includes("border")) return "border-amber-300 bg-amber-50 text-amber-700";
  return "border-slate-300 bg-slate-100 text-slate-700";
}

function PropertySection({ title, data }) {
  const entries = Object.entries(data || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!entries.length) return null;

  return (
    <section className="rounded-[28px] border border-slate-200 bg-slate-50/90 p-5">
      <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">{title}</div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {entries.map(([key, value]) => (
          <div key={key} className="rounded-2xl border border-white bg-white p-4 shadow-sm">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{formatLabel(key)}</div>
            <div className="mt-2 break-words text-sm font-semibold text-slate-900">{formatValue(value)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ListSection({ title, items, tone = "default" }) {
  if (!items?.length) return null;

  const tones = {
    default: "border-slate-200 bg-white",
    warn: "border-amber-200 bg-amber-50/70",
    danger: "border-rose-200 bg-rose-50/70",
  };

  return (
    <section className={`rounded-[28px] border p-5 ${tones[tone]}`}>
      <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">{title}</div>
      <div className="mt-4 space-y-3">
        {items.map((item, index) => (
          <div key={`${title}-${index}`} className="rounded-2xl bg-white/90 px-4 py-3 text-sm leading-6 text-slate-700 shadow-sm">
            {item}
          </div>
        ))}
      </div>
    </section>
  );
}

function CandidatePreview({ candidate }) {
  if (!candidate?.smiles) return null;

  return (
    <section className="rounded-[30px] border border-teal-200 bg-gradient-to-br from-teal-50 via-white to-cyan-50 p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.24em] text-teal-700">Candidate Molecule</div>
          <div className="mt-3 max-w-3xl break-all font-mono text-sm text-slate-900">{candidate.smiles}</div>
        </div>
        <div className={`rounded-full border px-3 py-1 text-xs font-semibold ${recommendationTone(candidate.recommendation)}`}>
          {candidate.recommendation || "Model-ranked"}
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-2xl bg-white/90 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Score</div>
          <div className="mt-2 text-xl font-semibold text-slate-900">{formatValue(candidate.score)}</div>
        </div>
        <div className="rounded-2xl bg-white/90 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Label</div>
          <div className="mt-2 text-sm font-semibold text-slate-900">{formatValue(candidate.name || "Candidate")}</div>
        </div>
        <div className="rounded-2xl bg-white/90 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Interpretation</div>
          <div className="mt-2 text-sm font-semibold text-slate-900">{formatValue(candidate.recommendation || "Needs review")}</div>
        </div>
      </div>
    </section>
  );
}

function ComparisonSection({ comparison }) {
  if (!comparison?.molecules?.length) return null;

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Comparison</div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {comparison.molecules.map((molecule) => (
          <div key={`${molecule.label}-${molecule.smiles}`} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm font-semibold text-slate-900">{molecule.label}</div>
            <div className="mt-3 break-all font-mono text-xs text-slate-700">{molecule.smiles}</div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-700">
              <div>Clinical: {formatValue(molecule.clinical_score)}</div>
              <div>QED: {formatValue(molecule.qed_score)}</div>
              <div>LogP: {formatValue(molecule.logp)}</div>
              <div>MW: {formatValue(molecule.molecular_weight)}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-2xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">
        {comparison.why}
      </div>
    </section>
  );
}

function GeneratedCandidatesSection({ molecules }) {
  if (!molecules?.length) return null;

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Generated Candidates</div>
        <div className="text-xs text-slate-500">{molecules.length} returned</div>
      </div>
      <div className="mt-4 space-y-3">
        {molecules.slice(0, 5).map((molecule) => (
          <div key={`${molecule.rank}-${molecule.smiles}`} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm font-semibold text-slate-900">Rank {formatValue(molecule.rank)}</div>
              <div className={`rounded-full border px-3 py-1 text-xs font-semibold ${recommendationTone(molecule.recommendation)}`}>
                {molecule.recommendation}
              </div>
            </div>
            <div className="mt-3 break-all font-mono text-xs text-slate-700">{molecule.smiles}</div>
            <div className="mt-4 grid gap-3 sm:grid-cols-4 text-sm text-slate-700">
              <div>Score: {formatValue(molecule.clinical_score)}</div>
              <div>MW: {formatValue(molecule.molecular_weight)}</div>
              <div>LogP: {formatValue(molecule.logp)}</div>
              <div>QED: {formatValue(molecule.qed_score)}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AssistantCard({ payload }) {
  return (
    <div className="w-full max-w-4xl rounded-[32px] border border-slate-200 bg-white/95 p-4 shadow-[0_24px_90px_-40px_rgba(15,23,42,0.35)] backdrop-blur sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.28em] text-teal-700">Genorova Chat</div>
          <div className="mt-2 text-sm text-slate-500">
            {formatLabel(payload.intent)} mode • {formatLabel(payload.mode)} detail
          </div>
        </div>
        <a
          href={`${BACKEND_ORIGIN}/docs`}
          target="_blank"
          rel="noreferrer"
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
        >
          API Docs
        </a>
      </div>

      <section className="mt-6 rounded-[28px] bg-[radial-gradient(circle_at_top,_rgba(13,148,136,0.16),_transparent_45%),linear-gradient(135deg,#082f49,#0f172a_55%,#111827)] p-6 text-white">
        <div className="text-xs font-bold uppercase tracking-[0.24em] text-teal-200">Summary</div>
        <div className="mt-4 text-base leading-7 text-slate-100">{payload.summary || "No summary returned."}</div>
      </section>

      <div className="mt-6 space-y-5">
        <CandidatePreview candidate={payload.candidate} />
        {payload.why ? (
          <section className="rounded-[28px] border border-slate-200 bg-slate-50/90 p-5">
            <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Why This Was Selected</div>
            <div className="mt-4 text-sm leading-7 text-slate-700">{payload.why}</div>
          </section>
        ) : null}
        <PropertySection title="Chemical Properties" data={payload.chemical_properties} />
        <PropertySection title="Physical Properties" data={payload.physical_properties} />
        <PropertySection title="Pharmacological Profile" data={payload.pharmacology} />
        <ComparisonSection comparison={payload.comparison} />
        <GeneratedCandidatesSection molecules={payload.generated_candidates} />
        <ListSection title="Strengths" items={payload.strengths} />
        <ListSection title="Risks / Warnings" items={payload.risks} tone="warn" />
        <ListSection title="Optimization Suggestions" items={payload.optimization_suggestions} />
        <ListSection title="Recommended Next Steps" items={payload.next_steps} />
        <ListSection title="Scientific Responsibility" items={payload.warnings} tone="danger" />
      </div>
    </div>
  );
}

function EmptyState({ stats, onPromptClick }) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-4 py-12 text-center">
      <div className="rounded-full border border-teal-200 bg-white px-4 py-2 text-xs font-bold uppercase tracking-[0.28em] text-teal-700 shadow-sm">
        Genorova Chat v1
      </div>
      <h1 className="mt-8 max-w-4xl text-4xl font-semibold tracking-tight text-slate-900 sm:text-6xl">
        Ask Genorova like you would ask a scientist.
      </h1>
      <p className="mt-5 max-w-3xl text-base leading-8 text-slate-600 sm:text-lg">
        Natural-language drug discovery support for students, researchers, founders, labs, and scientific teams.
        Genorova turns model outputs into understandable, structured answers with responsible caveats.
      </p>

      <div className="mt-10 grid w-full gap-4 sm:grid-cols-3">
        <div className="rounded-[28px] border border-slate-200 bg-white p-5 text-left shadow-sm">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Platform Reach</div>
          <div className="mt-3 text-3xl font-semibold text-slate-900">{formatValue(stats.total_molecules)}</div>
          <div className="mt-2 text-sm text-slate-600">ranked molecules currently available in the deployed dataset</div>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-white p-5 text-left shadow-sm">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Best Score</div>
          <div className="mt-3 text-3xl font-semibold text-slate-900">{formatValue(stats.best_score)}</div>
          <div className="mt-2 text-sm text-slate-600">top computational ranking currently exposed by the API</div>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-white p-5 text-left shadow-sm">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Best Molecule</div>
          <div className="mt-3 break-all font-mono text-xs text-slate-700">{stats.best_molecule}</div>
          <div className="mt-2 text-sm text-slate-600">ready to inspect, explain, compare, or optimize conversationally</div>
        </div>
      </div>

      <div className="mt-10 grid w-full gap-3">
        {starterPrompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPromptClick(prompt)}
            className="rounded-[24px] border border-slate-200 bg-white px-5 py-4 text-left text-sm text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-md"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function GenorovaChatApp() {
  const [stats, setStats] = useState(defaultStats);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("scientific");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function loadStats() {
    try {
      const response = await fetch(`${API_PREFIX}/stats`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to load stats.");
      }
      setStats(payload);
    } catch {
      setStats(defaultStats);
    }
  }

  async function submitPrompt(promptText) {
    const trimmed = promptText.trim();
    if (!trimmed || loading) return;

    setError("");
    startTransition(() => {
      setMessages((current) => [...current, { role: "user", content: trimmed }]);
    });
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_PREFIX}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, mode }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Genorova could not process that request.");
      }

      startTransition(() => {
        setMessages((current) => [...current, { role: "assistant", payload }]);
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    submitPrompt(input);
  }

  const showEmptyState = messages.length === 0;

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.18),_transparent_24%),linear-gradient(180deg,#f7fbfd_0%,#eef4f8_48%,#f7fafc_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px] flex-col lg:flex-row">
        <aside className="border-b border-white/60 bg-slate-950 px-5 py-6 text-slate-100 shadow-[0_20px_80px_-60px_rgba(15,23,42,0.8)] lg:min-h-screen lg:w-[320px] lg:border-b-0 lg:border-r lg:px-6">
          <div className="flex items-center justify-between gap-4 lg:block">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.32em] text-teal-300">Genorova</div>
              <div className="mt-3 text-3xl font-semibold tracking-tight text-white">Chat v1</div>
              <div className="mt-3 max-w-xs text-sm leading-6 text-slate-300">
                Natural-language drug discovery support with structured scientific outputs and honest computational caveats.
              </div>
            </div>
            <a
              href={`${BACKEND_ORIGIN}/docs`}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-200 transition hover:border-teal-400 hover:text-white"
            >
              Docs
            </a>
          </div>

          <div className="mt-8 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Best Score</div>
              <div className="mt-3 text-2xl font-semibold text-white">{formatValue(stats.best_score)}</div>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Molecules</div>
              <div className="mt-3 text-2xl font-semibold text-white">{formatValue(stats.total_molecules)}</div>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 backdrop-blur sm:col-span-3 lg:col-span-1">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Best Molecule</div>
              <div className="mt-3 break-all font-mono text-xs text-slate-200">{stats.best_molecule}</div>
            </div>
          </div>

          <div className="mt-8">
            <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-400">Suggested Prompts</div>
            <div className="mt-4 flex flex-wrap gap-2 lg:flex-col">
              {starterPrompts.slice(0, 4).map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => submitPrompt(prompt)}
                  className="rounded-full border border-slate-700 px-4 py-2 text-left text-xs text-slate-200 transition hover:border-teal-400 hover:bg-teal-400/10"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <main className="flex min-h-screen flex-1 flex-col">
          <header className="sticky top-0 z-10 border-b border-white/60 bg-white/80 px-4 py-4 backdrop-blur sm:px-6">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.28em] text-teal-700">Genorova Chat</div>
                <div className="mt-2 text-2xl font-semibold text-slate-900">
                  Conversational molecule discovery for real teams
                </div>
              </div>
              <div className="inline-flex rounded-full border border-slate-200 bg-slate-100 p-1">
                {modeOptions.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setMode(option)}
                    className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                      mode === option
                        ? "bg-white text-slate-900 shadow-sm"
                        : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {formatLabel(option)}
                  </button>
                ))}
              </div>
            </div>
          </header>

          <section className="flex flex-1 flex-col">
            <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 pb-36 pt-6 sm:px-6">
              {showEmptyState ? (
                <EmptyState stats={stats} onPromptClick={submitPrompt} />
              ) : (
                <div className="space-y-6">
                  {messages.map((message, index) => (
                    <div key={`${message.role}-${index}`} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                      {message.role === "user" ? (
                        <div className="max-w-2xl rounded-[28px] bg-slate-950 px-5 py-4 text-sm leading-7 text-white shadow-lg">
                          {message.content}
                        </div>
                      ) : (
                        <AssistantCard payload={message.payload} />
                      )}
                    </div>
                  ))}

                  {loading ? (
                    <div className="flex justify-start">
                      <div className="max-w-2xl rounded-[28px] border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
                        <div className="inline-flex items-center gap-3">
                          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-teal-500" />
                          Genorova is reviewing the request, routing the intent, and assembling a structured scientific answer.
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {error ? (
                    <div className="rounded-[24px] border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
                      {error}
                    </div>
                  ) : null}
                </div>
              )}
              <div ref={endRef} />
            </div>
          </section>

          <footer className="fixed inset-x-0 bottom-0 z-20 border-t border-white/60 bg-white/88 px-4 py-4 backdrop-blur sm:px-6 lg:left-[320px]">
            <div className="mx-auto w-full max-w-5xl">
              <form onSubmit={handleSubmit} className="rounded-[32px] border border-slate-200 bg-white p-3 shadow-[0_24px_80px_-45px_rgba(15,23,42,0.45)]">
                <textarea
                  rows={3}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Ask Genorova in plain English. Example: Generate a drug candidate for tuberculosis with good oral drug-likeness and low toxicity."
                  className="w-full resize-none rounded-[24px] border-0 bg-transparent px-3 py-3 text-sm leading-7 text-slate-900 outline-none placeholder:text-slate-400"
                />
                <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap gap-2">
                    {starterPrompts.slice(0, 3).map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => setInput(prompt)}
                        className="rounded-full border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-teal-300 hover:text-slate-900"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                  <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="rounded-full bg-slate-950 px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                  >
                    {loading ? "Thinking..." : "Send to Genorova"}
                  </button>
                </div>
              </form>
              <div className="mt-3 text-center text-xs leading-5 text-slate-500">
                Genorova outputs are computational predictions for research support only and are not experimentally validated.
              </div>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
