import { startTransition, useEffect, useRef, useState } from "react";
import { useAuth } from "./auth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const BACKEND_ORIGIN = API_BASE_URL || "http://localhost:8000";
const API_PREFIX = API_BASE_URL ? `${API_BASE_URL}/api` : "/api";
const STORAGE_KEY = "genorova-chat-v11-session";

const defaultStats = {
  total_molecules: 0,
  best_score: null,
  best_molecule: null,
  best_molecule_note: "No ranked molecule available yet.",
  best_molecular_weight: null,
  prototype_status: "prototype_research_support",
  trust_note:
    "Computational research-support platform. Active workflow: diabetes / DPP4 / sitagliptin comparator. Outputs are evidence-weighted heuristic and proxy signals only, not experimental proof or clinical validation.",
};

const guidedDemoActions = [
  {
    badge: "Recommended first demo",
    label: "Review ranked candidate set",
    prompt: "Show the top computational candidates in the active diabetes workflow",
    description: "Returns the current evidence-weighted candidate set with the validation ledger and trust boundaries.",
  },
  {
    badge: "Plain-language readout",
    label: "Explain the best molecule",
    prompt: "Explain the best molecule simply",
    description: "Walks through the current top shared candidate without requiring a pasted SMILES string.",
  },
  {
    badge: "Input example",
    label: "Score a sample molecule",
    prompt: "Score this molecule: CCO",
    description: "Shows the direct scoring path and how the validation ledger is presented for a simple example.",
  },
  {
    badge: "Follow-up demo",
    label: "Optimize for oral delivery",
    prompt: "Optimize the best molecule for oral delivery",
    description: "Demonstrates comparator-based decision support and conservative optimization guidance.",
  },
];

const modeOptions = ["simple", "scientific", "expert"];

function buildNetworkError(message) {
  const error = new Error(message);
  error.status = 0;
  error.code = "backend_unavailable";
  return error;
}

function createSessionId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `session-${crypto.randomUUID()}`;
  }
  return `session-${Date.now()}`;
}

function loadStoredSession() {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        sessionId: createSessionId(),
        messages: [],
        conversationState: {},
      };
    }

    const parsed = JSON.parse(raw);
    return {
      sessionId: parsed.sessionId || createSessionId(),
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
      conversationState: parsed.conversationState || {},
    };
  } catch {
    return {
      sessionId: createSessionId(),
      messages: [],
      conversationState: {},
    };
  }
}

function clearStoredSession() {
  window.sessionStorage.removeItem(STORAGE_KEY);
}

async function readJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch {
    throw buildNetworkError("Genorova could not reach the backend service.");
  }
  const payload = await readJson(response);

  if (!response.ok) {
    const error = new Error(payload.detail || "Request failed.");
    error.status = response.status;
    throw error;
  }

  return payload;
}

function buildNotice({ eyebrow, title, message, actions = [], tone = "slate" }) {
  return { eyebrow, title, message, actions, tone };
}

function describeWorkspaceIssue(error) {
  if (!error) return null;
  const message = String(error.message || "").trim();
  const normalized = message.toLowerCase();

  if (error.status === 401) {
    return buildNotice({
      eyebrow: "Session expired",
      title: "Your workspace session ended.",
      message: "Sign in again to restore access to the protected chat workspace and start a fresh session-safe demo flow.",
      actions: [
        "Return to the login screen and sign in again.",
        "Start with the recommended first demo after re-entering the workspace.",
      ],
      tone: "rose",
    });
  }

  if (error.status === 0 || error.code === "backend_unavailable" || normalized.includes("failed to fetch")) {
    return buildNotice({
      eyebrow: "Backend unavailable",
      title: "Genorova could not reach the API.",
      message: "The frontend is running, but the backend service did not respond. This usually means the local API or deployment is unavailable.",
      actions: [
        "Check that the FastAPI backend is running and reachable.",
        "Refresh the page after the backend is healthy.",
      ],
      tone: "amber",
    });
  }

  if (error.status === 429 || normalized.includes("limit")) {
    return buildNotice({
      eyebrow: "Usage limit reached",
      title: "This workspace request was blocked by a limit.",
      message: "Genorova could not complete the action because a rate, usage, or quota limit was hit.",
      actions: [
        "Try again shortly or reset the conversation.",
        "Use a lighter scoring or explanation request while limits are being tuned.",
      ],
      tone: "amber",
    });
  }

  if (normalized.includes("please include a smiles")) {
    return buildNotice({
      eyebrow: "Input needed",
      title: "Scoring needs a SMILES string.",
      message: "Paste a molecule string such as `CCO`, or use the recommended first demo if you want a guided starting point.",
      actions: [
        "Try: Score this molecule: CCO",
        "Or run the recommended ranked-candidate demo instead.",
      ],
      tone: "amber",
    });
  }

  if (normalized.includes("please provide two smiles")) {
    return buildNotice({
      eyebrow: "Comparison needs two molecules",
      title: "Genorova needs two explicit structures to compare.",
      message: "Provide two SMILES strings or first ask Genorova to explain a candidate so a follow-up comparison has context.",
      actions: [
        "Try a scoring or explanation prompt first.",
        "Then use a follow-up comparison action from the result card.",
      ],
      tone: "amber",
    });
  }

  if (normalized.includes("scoring failed") || normalized.includes("validation")) {
    return buildNotice({
      eyebrow: "Validation issue",
      title: "Genorova could not complete the computational evaluation.",
      message: "A scoring or validation step failed before a trustworthy result could be shown.",
      actions: [
        "Retry with a simpler scoring request.",
        "If this repeats, use the ranked-candidate demo path instead of a custom molecule.",
      ],
      tone: "rose",
    });
  }

  return buildNotice({
    eyebrow: "Request interrupted",
    title: "Genorova could not finish this request.",
    message: message || "The workspace hit an unexpected error before returning a usable result.",
    actions: [
      "Try the recommended first demo or reset the conversation.",
      "If the issue repeats, refresh the workspace and retry.",
    ],
    tone: "rose",
  });
}

function describeAuthIssue(error, authMode = "login") {
  if (!error) return null;
  const message = String(error.message || "").trim();
  const normalized = message.toLowerCase();

  if (error.status === 0 || error.code === "backend_unavailable" || normalized.includes("failed to fetch")) {
    return buildNotice({
      eyebrow: "Backend unavailable",
      title: "Sign-in could not reach the Genorova backend.",
      message: "The account system depends on the API being live. Once the backend is available, this page will work normally.",
      actions: [
        "Keep the backend running during demos.",
        "Refresh and try sign-in again after the API is healthy.",
      ],
      tone: "amber",
    });
  }

  if (error.status === 409) {
    return buildNotice({
      eyebrow: "Account already exists",
      title: "That email is already registered.",
      message: "Use the login tab for this account, or sign up with a different email address.",
      actions: [
        "Switch to login and try the same email.",
        "Use a new email if you intended to create a separate demo account.",
      ],
      tone: "amber",
    });
  }

  if (error.status === 401) {
    return buildNotice({
      eyebrow: "Sign-in failed",
      title: "The email or password did not match an existing account.",
      message: "Double-check your credentials, or create a new account if this is your first time using the workspace.",
      actions: [
        "Re-enter the email and password carefully.",
        authMode === "login" ? "If needed, switch to signup to create an account." : "If the account already exists, switch back to login.",
      ],
      tone: "rose",
    });
  }

  if (normalized.includes("password")) {
    return buildNotice({
      eyebrow: "Password issue",
      title: "The password did not meet the current requirements.",
      message: message,
      actions: [
        "Use at least 8 characters.",
        "Retry after updating the password field.",
      ],
      tone: "amber",
    });
  }

  return buildNotice({
    eyebrow: authMode === "signup" ? "Signup issue" : "Login issue",
    title: authMode === "signup" ? "Genorova could not create the account." : "Genorova could not complete sign-in.",
    message: message || "The authentication request did not finish successfully.",
    actions: [
      "Check the form fields and try again.",
      "If this repeats, refresh the page and retry.",
    ],
    tone: "rose",
  });
}

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

function CopyButton({ value, label = "Copy SMILES" }) {
  const [copied, setCopied] = useState(false);

  async function handleClick() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-teal-300 hover:text-slate-900"
    >
      {copied ? "Copied" : label}
    </button>
  );
}

function MoleculeVisual({ svg, smiles, compact = false }) {
  return (
    <div className={`overflow-hidden rounded-[24px] border border-slate-200 bg-white ${compact ? "p-3" : "p-4"}`}>
      {svg ? (
        <div className="molecule-svg text-slate-800" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <div className="flex h-[180px] items-center justify-center rounded-[18px] border border-dashed border-slate-200 bg-slate-50 px-4 text-center text-sm text-slate-500">
          Structure rendering unavailable for this molecule. The SMILES string is still shown below.
        </div>
      )}
      {smiles ? <div className="mt-3 break-all font-mono text-xs text-slate-600">{smiles}</div> : null}
    </div>
  );
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

function NoticeBanner({ notice }) {
  if (!notice) return null;

  const tones = {
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    rose: "border-rose-200 bg-rose-50 text-rose-800",
  };

  const style = tones[notice.tone] || tones.slate;

  return (
    <section className={`rounded-[28px] border px-5 py-4 shadow-sm ${style}`}>
      {notice.eyebrow ? (
        <div className="text-xs font-bold uppercase tracking-[0.24em]">{notice.eyebrow}</div>
      ) : null}
      <div className="mt-2 text-base font-semibold">{notice.title}</div>
      <div className="mt-2 text-sm leading-7">{notice.message}</div>
      {notice.actions?.length ? (
        <div className="mt-3 space-y-2 text-sm leading-6">
          {notice.actions.map((action) => (
            <div key={action}>- {action}</div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function DemoActionGrid({ actions, onPrompt, previewOnly = false }) {
  if (!actions?.length) return null;

  return (
    <div className="grid w-full gap-3 lg:grid-cols-2">
      {actions.map((action) => (
        <button
          key={action.prompt}
          type="button"
          disabled={previewOnly}
          onClick={previewOnly || !onPrompt ? undefined : () => onPrompt(action.prompt)}
          className={`rounded-[28px] border px-5 py-5 text-left shadow-sm transition ${
            previewOnly
              ? "cursor-not-allowed border-slate-200 bg-slate-100/80 text-slate-500"
              : "border-slate-200 bg-white text-slate-700 hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-md"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.22em] text-teal-700">
              {action.badge}
            </div>
            {previewOnly ? <div className="text-xs font-semibold uppercase tracking-[0.18em]">Sign in to run</div> : null}
          </div>
          <div className="mt-4 text-lg font-semibold text-slate-900">{action.label}</div>
          <div className="mt-3 text-sm leading-7">{action.description}</div>
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-xs text-slate-500">
            {action.prompt}
          </div>
        </button>
      ))}
    </div>
  );
}

function WorkspaceStatusGrid({ stats, hasMessages }) {
  const cards = [
    {
      title: "Conversations",
      value: hasMessages ? "Active" : "None yet",
      description: hasMessages
        ? "This workspace already has a live conversation thread."
        : "Run the recommended first demo to create the first conversation in this session.",
    },
    {
      title: "Candidate Results",
      value: hasMessages ? "Available" : "None yet",
      description: hasMessages
        ? "Use follow-up actions to explain, compare, or optimize the current candidate."
        : "The first ranked candidate appears after you run a scoring or ranked-candidate prompt.",
    },
    {
      title: "Reports / History",
      value: "Empty",
      description:
        "No report export or persistent history is shown in this workspace yet. Review the validation ledger inside each result first.",
    },
    {
      title: "Usage Trail",
      value: hasMessages ? "Session-only" : "No activity yet",
      description:
        "Workspace history begins after the first prompt and is currently tied to the active signed-in browser session.",
    },
    {
      title: "Ranked Molecule",
      value: stats?.best_molecule ? "Available" : "Unavailable",
      description: stats?.best_molecule
        ? stats.best_molecule_note || "A ranked molecule exists in the shared dataset and can be explained or compared."
        : "No ranked molecule is available in the shared dataset right now. Use scoring on a known molecule instead.",
    },
  ];

  return (
    <section className="w-full rounded-[30px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Current Workspace Status</div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {cards.map((card) => (
          <div key={card.title} className="rounded-[24px] border border-slate-200 bg-slate-50 p-4 text-left">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{card.title}</div>
            <div className="mt-3 text-lg font-semibold text-slate-900">{card.value}</div>
            <div className="mt-2 text-sm leading-6 text-slate-600">{card.description}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResultEmptyState({ payload, onFollowUp }) {
  if (payload?.candidate?.smiles || payload?.generated_candidates?.length) return null;

  return (
    <section className="rounded-[28px] border border-amber-200 bg-amber-50/90 p-5">
      <div className="text-xs font-bold uppercase tracking-[0.24em] text-amber-800">No ranked molecule available</div>
      <div className="mt-3 text-lg font-semibold text-amber-950">
        Genorova did not return a trustworthy candidate for this request.
      </div>
      <div className="mt-3 text-sm leading-7 text-amber-900">
        {payload?.why ||
          "The active validation path rejected the available candidates, so the workspace is explicitly surfacing the empty result instead of pretending a weak molecule is usable."}
      </div>
      {payload?.follow_up_actions?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {payload.follow_up_actions.map((action) => (
            <button
              key={`${action.label}-${action.prompt}`}
              type="button"
              onClick={() => onFollowUp(action.prompt)}
              className="rounded-full border border-amber-300 bg-white px-4 py-2 text-sm font-semibold text-amber-900 transition hover:border-amber-400"
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function CandidateHero({ candidate }) {
  if (!candidate?.smiles) return null;

  return (
    <section className="rounded-[30px] border border-teal-200 bg-gradient-to-br from-teal-50 via-white to-cyan-50 p-5 shadow-sm">
      <div className="grid gap-5 lg:grid-cols-[1.1fr,1fr]">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs font-bold uppercase tracking-[0.24em] text-teal-700">Candidate Molecule</div>
            <div className={`rounded-full border px-3 py-1 text-xs font-semibold ${recommendationTone(candidate.recommendation)}`}>
              {candidate.recommendation || "Model-ranked"}
            </div>
          </div>
          <div className="mt-4 break-all font-mono text-sm text-slate-900">{candidate.smiles}</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <CopyButton value={candidate.smiles} />
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-white/90 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Evidence-Weighted Score</div>
              <div className="mt-2 text-xl font-semibold text-slate-900">{formatValue(candidate.score)}</div>
            </div>
            <div className="rounded-2xl bg-white/90 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Candidate Label</div>
              <div className="mt-2 text-sm font-semibold text-slate-900">{formatValue(candidate.name || "Candidate")}</div>
            </div>
            <div className="rounded-2xl bg-white/90 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Current Decision</div>
              <div className="mt-2 text-sm font-semibold text-slate-900">{formatValue(candidate.validation_status || candidate.recommendation)}</div>
            </div>
          </div>
          {candidate.confidence_note ? (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {candidate.confidence_note}
            </div>
          ) : null}
        </div>
        <MoleculeVisual svg={candidate.molecule_svg} smiles={candidate.smiles} />
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
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-slate-900">{molecule.label}</div>
              <CopyButton value={molecule.smiles} label="Copy" />
            </div>
            <div className="mt-4">
              <MoleculeVisual svg={molecule.molecule_svg} smiles={molecule.smiles} compact />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-700">
              <div>Model score: {formatValue(molecule.clinical_score)}</div>
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
        <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Ranked Candidate Set</div>
        <div className="text-xs text-slate-500">{molecules.length} returned</div>
      </div>
      <div className="mt-3 text-sm leading-6 text-slate-600">
        These are evidence-weighted computational priorities for review, not experimental proof or validated lead claims.
      </div>
      <div className="mt-4 grid gap-4">
        {molecules.slice(0, 4).map((molecule) => (
          <div key={`${molecule.rank}-${molecule.smiles}`} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="grid gap-4 lg:grid-cols-[220px,1fr]">
              <MoleculeVisual svg={molecule.molecule_svg} smiles={molecule.smiles} compact />
              <div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-slate-900">Rank {formatValue(molecule.rank)}</div>
                  <div className={`rounded-full border px-3 py-1 text-xs font-semibold ${recommendationTone(molecule.recommendation)}`}>
                    {molecule.recommendation}
                  </div>
                </div>
                <div className="mt-4 grid gap-3 text-sm text-slate-700 sm:grid-cols-4">
                  <div>Evidence-weighted score: {formatValue(molecule.clinical_score)}</div>
                  <div>MW: {formatValue(molecule.molecular_weight)}</div>
                  <div>LogP: {formatValue(molecule.logp)}</div>
                  <div>QED: {formatValue(molecule.qed_score)}</div>
                </div>
                {molecule.confidence_note ? (
                  <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    {molecule.confidence_note}
                  </div>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <CopyButton value={molecule.smiles} />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function QuickActions({ actions, onPrompt }) {
  if (!actions?.length) return null;
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Follow-Up Actions</div>
      <div className="mt-4 flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={`${action.label}-${action.prompt}`}
            type="button"
            onClick={() => onPrompt(action.prompt)}
            className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-teal-300 hover:bg-teal-50 hover:text-slate-900"
          >
            {action.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function AssistantCard({ payload, onFollowUp }) {
  return (
    <div className="w-full max-w-4xl rounded-[32px] border border-slate-200 bg-white/96 p-4 shadow-[0_24px_90px_-40px_rgba(15,23,42,0.35)] backdrop-blur sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.28em] text-teal-700">Genorova Research Workspace</div>
          <div className="mt-2 text-sm text-slate-500">
            {formatLabel(payload.intent)} mode / {formatLabel(payload.mode)} detail
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
        <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm leading-6 text-slate-200">
          Evidence-weighted view only: Genorova combines computed descriptors, comparator-based screening, and
          heuristic or proxy signals. The result is not experimental proof or clinical validation.
        </div>
      </section>

      <div className="mt-6 space-y-5">
        <ResultEmptyState payload={payload} onFollowUp={onFollowUp} />
        <CandidateHero candidate={payload.candidate} />
        {payload.why ? (
          <section className="rounded-[28px] border border-slate-200 bg-slate-50/90 p-5">
            <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Why This Was Selected</div>
            <div className="mt-4 text-sm leading-7 text-slate-700">{payload.why}</div>
          </section>
        ) : null}
        {payload.candidate?.smiles || payload.generated_candidates?.length ? (
          <QuickActions actions={payload.follow_up_actions} onPrompt={onFollowUp} />
        ) : null}
        <PropertySection title="Trust & Validation" data={payload.trust} />
        <PropertySection title="Validation Ledger" data={payload.validation} />
        <PropertySection title="Chemical Properties" data={payload.chemical_properties} />
        <PropertySection title="Physical Properties" data={payload.physical_properties} />
        <PropertySection title="Pharmacological Profile" data={payload.pharmacology} />
        <ComparisonSection comparison={payload.comparison} />
        <GeneratedCandidatesSection molecules={payload.generated_candidates} />
        <ListSection title="Strengths" items={payload.strengths} />
        <ListSection title="Risks / Warnings" items={payload.risks} tone="warn" />
        <ListSection title="Limitations" items={payload.limitations} tone="warn" />
        <ListSection title="Optimization Suggestions" items={payload.optimization_suggestions} />
        <ListSection title="Recommended Next Steps" items={payload.next_steps} />
        <ListSection title="Scientific Responsibility" items={payload.warnings} tone="danger" />
      </div>
    </div>
  );
}

function EmptyState({ stats, onPromptClick, previewOnly = false }) {
  const trustNote = stats?.trust_note || defaultStats.trust_note;
  const recommendedDemo = guidedDemoActions[0];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-4 py-12 text-center">
      <div className="rounded-full border border-teal-200 bg-white px-4 py-2 text-xs font-bold uppercase tracking-[0.28em] text-teal-700 shadow-sm">
        Genorova Research Workspace
      </div>
      <h1 className="mt-8 max-w-4xl text-4xl font-semibold tracking-tight text-slate-900 sm:text-6xl">
        Conversational molecular analysis for computational research support.
      </h1>
      <p className="mt-5 max-w-3xl text-base leading-8 text-slate-600 sm:text-lg">
        Genorova keeps session context, shows molecule structures inline, and helps teams score, explain, and compare
        computational results with explicit scientific caveats and transparent limitations.
      </p>

      <div className="mt-10 w-full rounded-[32px] border border-teal-200 bg-gradient-to-br from-teal-50 via-white to-cyan-50 p-6 text-left shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.24em] text-teal-700">Start Here</div>
            <div className="mt-3 text-2xl font-semibold text-slate-900">Recommended first demo flow</div>
          </div>
          <div className="rounded-full border border-teal-200 bg-white px-4 py-2 text-xs font-bold uppercase tracking-[0.22em] text-teal-700">
            Guided path
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <div className="rounded-[24px] border border-white bg-white/90 p-4">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Step 1</div>
            <div className="mt-2 text-sm font-semibold text-slate-900">Run the ranked-candidate demo</div>
            <div className="mt-2 text-sm leading-6 text-slate-600">
              Start with the active diabetes workflow so the first response returns a candidate and evidence ledger.
            </div>
          </div>
          <div className="rounded-[24px] border border-white bg-white/90 p-4">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Step 2</div>
            <div className="mt-2 text-sm font-semibold text-slate-900">Read the candidate and validation ledger</div>
            <div className="mt-2 text-sm leading-6 text-slate-600">
              Focus on SA, novelty, comparator delta, docking mode, safety flags, and the final decision.
            </div>
          </div>
          <div className="rounded-[24px] border border-white bg-white/90 p-4">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Step 3</div>
            <div className="mt-2 text-sm font-semibold text-slate-900">Use a follow-up action</div>
            <div className="mt-2 text-sm leading-6 text-slate-600">
              Ask Genorova to explain or optimize the candidate while keeping the scientific limitations in view.
            </div>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={previewOnly}
            onClick={previewOnly || !onPromptClick ? undefined : () => onPromptClick(recommendedDemo.prompt)}
            className={`rounded-full px-5 py-3 text-sm font-semibold transition ${
              previewOnly
                ? "cursor-not-allowed border border-slate-300 bg-slate-100 text-slate-500"
                : "bg-slate-950 text-white hover:bg-slate-800"
            }`}
          >
            {previewOnly ? "Sign in to run the demo" : "Run recommended first demo"}
          </button>
          <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-mono text-slate-500">
            {recommendedDemo.prompt}
          </div>
        </div>
      </div>

      <div className="mt-10 grid w-full gap-4 sm:grid-cols-3">
        <div className="rounded-[28px] border border-slate-200 bg-white p-5 text-left shadow-sm">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Conversation Memory</div>
          <div className="mt-3 text-3xl font-semibold text-slate-900">Session</div>
          <div className="mt-2 text-sm text-slate-600">Follow-up prompts can refer to the latest candidate as "it" or "that".</div>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-white p-5 text-left shadow-sm">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Live Visuals</div>
          <div className="mt-3 text-3xl font-semibold text-slate-900">{formatValue(stats.best_score)}</div>
          <div className="mt-2 text-sm text-slate-600">Backend-generated SVG structures for generated, scored, and compared molecules.</div>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-white p-5 text-left shadow-sm">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Current Dataset</div>
          <div className="mt-3 text-3xl font-semibold text-slate-900">{formatValue(stats.total_molecules)}</div>
          <div className="mt-2 text-sm text-slate-600">Previously scored valid molecules currently available in the deployed platform.</div>
        </div>
      </div>

      <div className="mt-8 rounded-[28px] border border-amber-200 bg-amber-50 px-6 py-5 text-left text-sm leading-7 text-amber-900">
        {trustNote} Rankings are evidence-weighted, and generation, docking, and confidence fields can include proxy or
        heuristic outputs. The workspace is most reliable today for scoring, explanation, comparison, and reviewing
        previously scored valid molecules.
      </div>

      <WorkspaceStatusGrid stats={stats} hasMessages={false} />

      <div className="mt-10 w-full text-left">
        <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Example Prompts</div>
        <div className="mt-4">
          <DemoActionGrid actions={guidedDemoActions} onPrompt={onPromptClick} previewOnly={previewOnly} />
        </div>
      </div>
    </div>
  );
}

function LoadingGate() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.18),_transparent_24%),linear-gradient(180deg,#f7fbfd_0%,#eef4f8_48%,#f7fafc_100%)] px-4 py-8 text-slate-900">
      <div className="mx-auto flex min-h-[80vh] max-w-4xl items-center justify-center">
        <div className="rounded-[32px] border border-slate-200 bg-white px-8 py-10 text-center shadow-[0_30px_120px_-55px_rgba(15,23,42,0.45)]">
          <div className="text-xs font-bold uppercase tracking-[0.28em] text-teal-700">Genorova</div>
          <div className="mt-4 text-2xl font-semibold text-slate-900">Checking your workspace session</div>
          <div className="mt-3 text-sm leading-7 text-slate-600">
            Verifying the active account before loading protected chat and session state.
          </div>
        </div>
      </div>
    </div>
  );
}

function ProtectedWorkspace({ user, fallback, children }) {
  if (!user) {
    return fallback;
  }
  return children;
}

function AuthGate({
  stats,
  mode,
  authMode,
  authValues,
  authError,
  systemNotice,
  submitting,
  onModeChange,
  onValueChange,
  onSubmit,
}) {
  const trustNote = stats?.trust_note || defaultStats.trust_note;
  const isSignup = authMode === "signup";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.18),_transparent_24%),linear-gradient(180deg,#f7fbfd_0%,#eef4f8_48%,#f7fafc_100%)] text-slate-900">
      <div className="mx-auto grid min-h-screen w-full max-w-[1480px] gap-8 px-4 py-8 lg:grid-cols-[1.1fr,420px] lg:px-8">
        <div className="flex flex-col">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.32em] text-teal-700">Genorova</div>
              <div className="mt-3 text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">
                Research workspace access now runs through account sessions.
              </div>
              <div className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
                Public access remains limited to platform stats and scientific framing. The interactive workspace,
                private chat context, and user-only analysis flow require authentication.
              </div>
            </div>
            <a
              href={`${BACKEND_ORIGIN}/docs`}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-white"
            >
              API Docs
            </a>
          </div>

          <div className="mt-8">
            <EmptyState stats={stats} previewOnly />
          </div>

          <div className="mt-6 rounded-[28px] border border-amber-200 bg-amber-50 px-6 py-5 text-sm leading-7 text-amber-900">
            {trustNote} Workspace chat is authenticated now so private session state is tied to a real user account,
            not just a browser-local identifier. After sign-in, the cleanest first demo is the ranked-candidate path
            shown above.
          </div>
        </div>

        <div className="flex items-center">
          <div className="w-full rounded-[32px] border border-slate-200 bg-white/96 p-6 shadow-[0_30px_120px_-55px_rgba(15,23,42,0.45)] backdrop-blur">
            <div className="rounded-full border border-teal-200 bg-teal-50 px-4 py-2 text-xs font-bold uppercase tracking-[0.28em] text-teal-700">
              Protected Workspace
            </div>
            <div className="mt-6 text-3xl font-semibold tracking-tight text-slate-900">
              {isSignup ? "Create your account" : "Sign in to Genorova"}
            </div>
            <div className="mt-3 text-sm leading-7 text-slate-600">
              Computational research-support platform only. Outputs remain heuristic and proxy signals, not
              experimental proof or clinical validation.
            </div>

            {systemNotice ? <div className="mt-6"><NoticeBanner notice={systemNotice} /></div> : null}

            <div className="mt-6 inline-flex rounded-full border border-slate-200 bg-slate-100 p-1">
              {["login", "signup"].map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => onModeChange(option)}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    authMode === option ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {formatLabel(option)}
                </button>
              ))}
            </div>

            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              {isSignup ? (
                <label className="block">
                  <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Name</div>
                  <input
                    type="text"
                    value={authValues.name}
                    onChange={(event) => onValueChange("name", event.target.value)}
                    placeholder="Your name"
                    className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-teal-400 focus:bg-white"
                  />
                </label>
              ) : null}

              <label className="block">
                <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Email</div>
                <input
                  type="email"
                  value={authValues.email}
                  onChange={(event) => onValueChange("email", event.target.value)}
                  placeholder="you@example.com"
                  className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-teal-400 focus:bg-white"
                />
              </label>

              <label className="block">
                <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Password</div>
                <input
                  type="password"
                  value={authValues.password}
                  onChange={(event) => onValueChange("password", event.target.value)}
                  placeholder="At least 8 characters"
                  className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-teal-400 focus:bg-white"
                />
              </label>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Current workspace mode after sign-in: <span className="font-semibold text-slate-900">{formatLabel(mode)}</span>
              </div>

              <div className="rounded-2xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm leading-7 text-teal-900">
                Recommended first demo after sign-in: run the active diabetes ranked-candidate prompt, then review the
                validation ledger before asking for optimization or comparison.
              </div>

              {authError ? <NoticeBanner notice={authError} /> : null}

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {submitting ? "Working..." : isSignup ? "Create account" : "Sign in"}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function GenorovaChatAppV11() {
  const { user, loading: authLoading, login, logout, signup, bootstrapError } = useAuth();
  const [stats, setStats] = useState(defaultStats);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("scientific");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(() => createSessionId());
  const [conversationState, setConversationState] = useState({});
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [authValues, setAuthValues] = useState({
    name: "",
    email: "",
    password: "",
  });
  const [authError, setAuthError] = useState(null);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const endRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    if (!workspaceReady) return;
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, workspaceReady]);

  useEffect(() => {
    if (!user) {
      clearStoredSession();
      setMessages([]);
      setConversationState({});
      setSessionId(createSessionId());
      setInput("");
      setError(null);
      setWorkspaceReady(false);
      return;
    }

    const restored = loadStoredSession();
    setMessages(restored.messages);
    setConversationState(restored.conversationState);
    setSessionId(restored.sessionId || createSessionId());
    setInput("");
    setError(null);
    setWorkspaceReady(true);
  }, [user]);

  useEffect(() => {
    if (!user || !workspaceReady) return;
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        sessionId,
        messages,
        conversationState,
      })
    );
  }, [user, workspaceReady, sessionId, messages, conversationState]);

  async function loadStats() {
    try {
      const payload = await apiRequest("/stats", { method: "GET" });
      setStats(payload);
    } catch {
      setStats(defaultStats);
    }
  }

  async function submitPrompt(promptText) {
    const trimmed = promptText.trim();
    if (!trimmed || loading || !user) return;

    setError(null);
    const nextUserMessage = { role: "user", content: trimmed };
    startTransition(() => {
      setMessages((current) => [...current, nextUserMessage]);
    });
    setInput("");
    setLoading(true);

    try {
      const payload = await apiRequest("/chat", {
        method: "POST",
        body: JSON.stringify({
          message: trimmed,
          mode,
          session_id: sessionId,
          conversation_state: conversationState,
          history: [...messages.slice(-8), nextUserMessage],
        }),
      });

      startTransition(() => {
        setMessages((current) => [...current, { role: "assistant", payload }]);
      });
      setConversationState(payload.conversation_state || {});
      setSessionId(payload.session_id || sessionId);
    } catch (requestError) {
      if (requestError.status === 401) {
        setAuthMode("login");
        setAuthError(describeAuthIssue(requestError, "login"));
        clearStoredSession();
        setMessages([]);
        setConversationState({});
        setSessionId(createSessionId());
        setWorkspaceReady(false);
        await logout();
        return;
      }
      setError(describeWorkspaceIssue(requestError));
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    submitPrompt(input);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  }

  function resetConversation() {
    const nextSessionId = createSessionId();
    setSessionId(nextSessionId);
    setMessages([]);
    setConversationState({});
    setError(null);
    setInput("");
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ sessionId: nextSessionId, messages: [], conversationState: {} })
    );
  }

  function handleAuthValueChange(field, value) {
    setAuthValues((current) => ({ ...current, [field]: value }));
    if (authError) {
      setAuthError(null);
    }
  }

  function handleAuthModeChange(nextMode) {
    setAuthMode(nextMode);
    setAuthError(null);
  }

  async function handleAuthSubmit(event) {
    event.preventDefault();
    setAuthSubmitting(true);
    setAuthError(null);

    try {
      if (authMode === "signup") {
        await signup(authValues);
      } else {
        await login({
          email: authValues.email,
          password: authValues.password,
        });
      }

      clearStoredSession();
      setMessages([]);
      setConversationState({});
      setSessionId(createSessionId());
      setInput("");
      setError(null);
      setAuthValues({ name: "", email: "", password: "" });
    } catch (requestError) {
      setAuthError(describeAuthIssue(requestError, authMode));
    } finally {
      setAuthSubmitting(false);
    }
  }

  async function handleLogout() {
    clearStoredSession();
    setMessages([]);
    setConversationState({});
    setSessionId(createSessionId());
    setInput("");
    setError(null);
    setWorkspaceReady(false);

    try {
      await logout();
    } catch (requestError) {
      setError(describeWorkspaceIssue(requestError));
    }
  }

  const showEmptyState = messages.length === 0;
  const systemNotice = bootstrapError ? describeAuthIssue(bootstrapError, authMode) : null;

  if (authLoading) {
    return <LoadingGate />;
  }

  return (
    <ProtectedWorkspace
      user={user}
      fallback={
        <AuthGate
          stats={stats}
          mode={mode}
          authMode={authMode}
          authValues={authValues}
          authError={authError}
          systemNotice={systemNotice}
          submitting={authSubmitting}
          onModeChange={handleAuthModeChange}
          onValueChange={handleAuthValueChange}
          onSubmit={handleAuthSubmit}
        />
      }
    >
      <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.18),_transparent_24%),linear-gradient(180deg,#f7fbfd_0%,#eef4f8_48%,#f7fafc_100%)] text-slate-900">
        <div className="mx-auto flex min-h-screen w-full max-w-[1600px] flex-col lg:flex-row">
          <aside className="border-b border-white/60 bg-slate-950 px-5 py-6 text-slate-100 shadow-[0_20px_80px_-60px_rgba(15,23,42,0.8)] lg:min-h-screen lg:w-[320px] lg:border-b-0 lg:border-r lg:px-6">
            <div className="flex items-center justify-between gap-4 lg:block">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.32em] text-teal-300">Genorova</div>
                <div className="mt-3 text-3xl font-semibold tracking-tight text-white">Research Workspace</div>
                <div className="mt-3 max-w-xs text-sm leading-6 text-slate-300">
                  Authenticated computational research-support workspace with visual structures, follow-up actions, and
                  explicit scientific limitations.
                </div>
                <div className="mt-5 rounded-[24px] border border-white/10 bg-white/5 p-4 backdrop-blur">
                  <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Signed In</div>
                  <div className="mt-3 text-sm font-semibold text-white">{user?.name || user?.email}</div>
                  <div className="mt-1 text-xs text-slate-400">{user?.email}</div>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={resetConversation}
                  className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-200 transition hover:border-teal-400 hover:text-white"
                >
                  New Chat
                </button>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-200 transition hover:border-teal-400 hover:text-white"
                >
                  Logout
                </button>
                <a
                  href={`${BACKEND_ORIGIN}/docs`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-200 transition hover:border-teal-400 hover:text-white"
                >
                  Docs
                </a>
              </div>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 backdrop-blur">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Top Ranked Score</div>
                <div className="mt-3 text-2xl font-semibold text-white">{formatValue(stats.best_score)}</div>
              </div>
              <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 backdrop-blur">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Molecules</div>
                <div className="mt-3 text-2xl font-semibold text-white">{formatValue(stats.total_molecules)}</div>
              </div>
              <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 backdrop-blur sm:col-span-3 lg:col-span-1">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Current Topic</div>
                <div className="mt-3 text-sm font-semibold text-white">{formatValue(conversationState.latest_topic || "No active topic")}</div>
              </div>
            </div>

            <div className="mt-8">
              <div className="text-xs font-bold uppercase tracking-[0.24em] text-slate-400">Demo Prompts</div>
              <div className="mt-4 flex flex-wrap gap-2 lg:flex-col">
                {guidedDemoActions.map((action) => (
                  <button
                    key={action.prompt}
                    type="button"
                    onClick={() => submitPrompt(action.prompt)}
                    className="rounded-full border border-slate-700 px-4 py-2 text-left text-xs text-slate-200 transition hover:border-teal-400 hover:bg-teal-400/10"
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </div>
          </aside>

          <main className="flex min-h-screen flex-1 flex-col">
            <header className="sticky top-0 z-10 border-b border-white/60 bg-white/80 px-4 py-4 backdrop-blur sm:px-6">
              <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="text-xs font-bold uppercase tracking-[0.28em] text-teal-700">Genorova Workspace</div>
                  <div className="mt-2 text-2xl font-semibold text-slate-900">
                    Evidence-weighted molecule analysis with session memory and explicit trust boundaries
                  </div>
                </div>
                <div className="inline-flex rounded-full border border-slate-200 bg-slate-100 p-1">
                  {modeOptions.map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => setMode(option)}
                      className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                        mode === option ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      {formatLabel(option)}
                    </button>
                  ))}
                </div>
              </div>
            </header>

            <section className="flex flex-1 flex-col">
              <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 pb-40 pt-6 sm:px-6">
                {showEmptyState ? (
                  <div className="space-y-6">
                    <EmptyState stats={stats} onPromptClick={submitPrompt} />
                    {error ? <NoticeBanner notice={error} /> : null}
                  </div>
                ) : (
                  <div className="space-y-6">
                    {messages.map((message, index) => (
                      <div key={`${message.role}-${index}`} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                        {message.role === "user" ? (
                          <div className="max-w-2xl rounded-[28px] bg-slate-950 px-5 py-4 text-sm leading-7 text-white shadow-lg">
                            {message.content}
                          </div>
                        ) : (
                          <AssistantCard payload={message.payload} onFollowUp={submitPrompt} />
                        )}
                      </div>
                    ))}

                    {loading ? (
                      <div className="flex justify-start">
                        <div className="max-w-2xl rounded-[28px] border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
                          <div className="flex items-center gap-3">
                            <span className="inline-flex gap-1">
                              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-teal-500" />
                              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-teal-400 [animation-delay:120ms]" />
                              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-teal-300 [animation-delay:240ms]" />
                            </span>
                            Genorova is using the current session context, reviewing the latest molecule, and assembling
                            a conservative research-support response from computational proxy and heuristic signals.
                          </div>
                        </div>
                      </div>
                    ) : null}

                    {error ? <NoticeBanner notice={error} /> : null}
                  </div>
                )}
                <div ref={endRef} />
              </div>
            </section>

            <footer className="fixed inset-x-0 bottom-0 z-20 border-t border-white/60 bg-white/88 px-4 py-4 backdrop-blur sm:px-6 lg:left-[320px]">
              <div className="mx-auto w-full max-w-5xl">
                <form onSubmit={handleSubmit} className="rounded-[32px] border border-slate-200 bg-white p-3 shadow-[0_24px_80px_-45px_rgba(15,23,42,0.45)]">
                  <textarea
                    ref={textareaRef}
                    rows={3}
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Start with the recommended ranked-candidate demo, or paste a SMILES string such as CCO for direct scoring."
                    className="w-full resize-none rounded-[24px] border-0 bg-transparent px-3 py-3 text-sm leading-7 text-slate-900 outline-none placeholder:text-slate-400"
                  />
                  <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex flex-wrap gap-2">
                      {guidedDemoActions.slice(0, 3).map((action) => (
                        <button
                          key={action.prompt}
                          type="button"
                          onClick={() => setInput(action.prompt)}
                          className="rounded-full border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-teal-300 hover:text-slate-900"
                        >
                          {action.label}
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
                  Genorova is a computational research-support platform. Rankings are evidence-weighted, and outputs can
                  include proxy or heuristic signals only, not experimental proof or clinical validation.
                </div>
              </div>
            </footer>
          </main>
        </div>
      </div>
    </ProtectedWorkspace>
  );
}
