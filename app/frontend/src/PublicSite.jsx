import { Link } from "react-router-dom";
import { useState } from "react";
import GenorovaLogo from "./components/GenorovaLogo";

const BLUE = "#0F2D6E";
const BLUE2 = "#1A4BAD";
const CYAN = "#00CFFF";
const WHITE = "#FFFFFF";
const LGREY = "#F6F8FE";
const MGREY = "#E0E8FF";
const GREY = "#5F6F95";
const INK = "#13213C";

const navLinks = [
  ["Features", "/features"],
  ["Benchmarks", "/benchmarks"],
  ["Pricing", "/pricing"],
  ["About", "/about"],
  ["Roadmap", "/roadmap"],
];

const features = [
  {
    title: "Conversational Molecule Generation",
    text: "Type in plain English - Genorova generates, scores, and ranks drug-like candidates instantly.",
  },
  {
    title: "ADMET Safety Scoring",
    text: "Absorption, Distribution, Metabolism, Excretion, Toxicity - computed for every molecule automatically. Grade A/B/C/D system with Lipinski, Veber, PAINS filters.",
  },
  {
    title: "DPP-4 Diabetes Specialist",
    text: "Fine-tuned on 3,652 confirmed DPP-4 inhibitors from ChEMBL. Achieved 0.836 Tanimoto vs Sitagliptin.",
  },
  {
    title: "Gyrase B Antibacterial Specialist",
    text: "204 potent Gyrase B inhibitors trained. Target for next-generation antibiotics.",
  },
  {
    title: "MOSES Benchmarks",
    text: "Evaluated on official MOSES suite. SNN/Test 0.611 beats REINVENT (0.58), MolGPT (0.56), JT-VAE (0.54).",
  },
  {
    title: "REST API",
    text: "5 endpoints: /generate, /score, /batch-score, /health, /metrics. FastAPI with Swagger docs at /api-docs.",
  },
  {
    title: "Researcher CLI",
    text: "Plain English queries: 'give me 10 potent DPP-4 inhibitors under 500 daltons' -> ranked results in 60s.",
  },
  {
    title: "Export & Reports",
    text: "Download ranked candidates as CSV with full ADMET profiles for further computational or wet-lab work.",
  },
];

const benchmarkRows = [
  { model: "Genorova AI", valid: "70.9%", unique: "91.1%", snn: "0.611★", fcd: "6.23", filters: "97.3%★", highlight: true },
  { model: "REINVENT", valid: "96.8%", unique: "98.5%", snn: "0.58", fcd: "1.84", filters: "~95%" },
  { model: "MolGPT", valid: "98.5%", unique: "96.6%", snn: "0.56", fcd: "3.46", filters: "~94%" },
  { model: "JT-VAE", valid: "100%", unique: "100%", snn: "0.54", fcd: "4.71", filters: "~97%" },
];

const dpp4Evidence = [
  ["Tanimoto similarity to Sitagliptin", "0.836"],
  ["Generated without being shown Sitagliptin structure", "confirmed"],
  ["Top hit IC50", "0.012 nM (ChEMBL validated)"],
  ["Training actives", "3,652 DPP-4 confirmed inhibitors"],
];

const founderStats = [
  "6 active users at AIIMS Rishikesh",
  "ISoP 2026 abstract submitted (Costa Rica, September)",
  "Applied to YC S2026, Accel Atoms, Surge, Endiya Partners",
  "Built in 6 weeks on consumer CPU, no GPU, no funding",
  "Beats REINVENT (AstraZeneca) on SNN/Test metric",
];

const pageCopy = {
  pricing: {
    title: "Pricing",
    subtitle: "Research access first, commercial workflows next.",
    body: [
      "Genorova is currently operating with free research access while the validation pipeline matures.",
      "Paid tiers will focus on larger batch generation, private datasets, audit trails, and team workspaces.",
    ],
  },
  roadmap: {
    title: "Roadmap",
    subtitle: "From specialist generation to validated discovery workflows.",
    body: [
      "Near-term work includes broader target specialists, stronger novelty checks, richer ADMET explainability, and workspace exports for research teams.",
      "The long-term goal is a reliable early-stage molecule exploration layer for labs that do not have dedicated computational chemistry infrastructure.",
    ],
  },
  contact: {
    title: "Contact",
    subtitle: "For collaborations, validation, and research access.",
    body: [
      "Use the Genorova workspace to test generation and scoring workflows.",
      "For institutional collaboration, prepare the target class, assay context, and desired molecular constraints before reaching out.",
    ],
  },
};

const shellStyle = {
  background: WHITE,
  color: INK,
  fontFamily: '"Inter", system-ui, sans-serif',
  minHeight: "100vh",
};

function PublicNav({ onSignup, onLogin }) {
  return (
    <nav
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: "rgba(255,255,255,0.96)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid #E4EAF8",
        padding: "10px 28px",
        minHeight: 64,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        flexWrap: "wrap",
      }}
    >
      <Link to="/" style={{ textDecoration: "none" }}>
        <GenorovaLogo size={34} showText />
      </Link>
      <div style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
        {navLinks.map(([label, href]) => (
          <Link
            key={href}
            to={href}
            style={{
              color: GREY,
              fontSize: 14,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            {label}
          </Link>
        ))}
        <button onClick={onLogin} style={secondaryButtonStyle}>
          Login
        </button>
        <button onClick={onSignup} style={primaryButtonStyle}>
          Sign Up
        </button>
      </div>
    </nav>
  );
}

function Footer() {
  return (
    <footer style={{ borderTop: "1px solid #E4EAF8", padding: "28px 24px", background: WHITE }}>
      <div
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 18,
          flexWrap: "wrap",
        }}
      >
        <GenorovaLogo size={28} showText />
        <div style={{ color: GREY, fontSize: 12, lineHeight: 1.6 }}>
          © 2026 Genorova AI. Computational research outputs require experimental validation.
        </div>
      </div>
    </footer>
  );
}

const primaryButtonStyle = {
  background: BLUE2,
  color: WHITE,
  border: "none",
  padding: "9px 18px",
  borderRadius: 8,
  cursor: "pointer",
  fontSize: 14,
  fontWeight: 800,
};

const secondaryButtonStyle = {
  color: BLUE2,
  background: WHITE,
  border: `1.5px solid ${BLUE2}`,
  padding: "8px 17px",
  borderRadius: 8,
  cursor: "pointer",
  fontSize: 14,
  fontWeight: 700,
};

function StatGrid() {
  return (
    <section style={{ background: BLUE, padding: "34px 24px" }}>
      <div
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))",
          gap: 22,
          textAlign: "center",
        }}
      >
        {[
          ["0.611", "SNN/Test", "Beats REINVENT 0.58"],
          ["97.3%", "Filters", "MOSES filter pass"],
          ["0.836", "DPP-4 Tanimoto", "vs Sitagliptin"],
          ["3,652", "DPP-4 actives", "ChEMBL confirmed"],
          ["6 weeks", "Built lean", "CPU, no GPU, no funding"],
        ].map(([value, label, note]) => (
          <div key={label}>
            <div style={{ color: CYAN, fontSize: 27, fontWeight: 900 }}>{value}</div>
            <div style={{ color: WHITE, fontSize: 13, fontWeight: 700, marginTop: 4 }}>{label}</div>
            <div style={{ color: "rgba(255,255,255,0.66)", fontSize: 11, marginTop: 3 }}>{note}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function FeatureGrid() {
  return (
    <section style={{ padding: "72px 24px", background: LGREY }}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <SectionHeading title="Real Genorova Features" subtitle="Built around usable molecule generation, scoring, and export workflows." />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))", gap: 16 }}>
          {features.map((feature, index) => (
            <article
              key={feature.title}
              style={{
                background: WHITE,
                border: "1px solid #DCE5F7",
                borderRadius: 8,
                padding: 22,
                minHeight: 170,
              }}
            >
              <div style={{ color: BLUE2, fontSize: 12, fontWeight: 900, marginBottom: 12 }}>
                {String(index + 1).padStart(2, "0")}
              </div>
              <h3 style={{ color: BLUE, fontSize: 18, margin: "0 0 10px", lineHeight: 1.3 }}>{feature.title}</h3>
              <p style={{ color: GREY, fontSize: 14, lineHeight: 1.6, margin: 0 }}>{feature.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function BenchmarkTable() {
  return (
    <section style={{ padding: "72px 24px", background: WHITE }}>
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <SectionHeading title="MOSES Benchmarks" subtitle="Official benchmark metrics for molecular generation quality." />
        <div style={{ overflowX: "auto", border: "1px solid #DCE5F7", borderRadius: 8 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
            <thead>
              <tr style={{ background: BLUE }}>
                {["Model", "Valid", "Unique", "SNN↑", "FCD↓", "Filters↑"].map((header) => (
                  <th key={header} style={{ color: WHITE, padding: "13px 15px", textAlign: "left", fontSize: 13 }}>
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {benchmarkRows.map((row) => (
                <tr key={row.model} style={{ background: row.highlight ? "#F0FBFF" : WHITE, borderTop: "1px solid #E7EDF8" }}>
                  <td style={tableCell(row.highlight)}>{row.model}</td>
                  <td style={tableCell()}>{row.valid}</td>
                  <td style={tableCell()}>{row.unique}</td>
                  <td style={tableCell(row.highlight)}>{row.snn}</td>
                  <td style={tableCell()}>{row.fcd}</td>
                  <td style={tableCell(row.highlight)}>{row.filters}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function EvidenceSection() {
  return (
    <section style={{ padding: "72px 24px", background: LGREY }}>
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <SectionHeading title="DPP-4 Evidence" subtitle="Specialist diabetes chemistry results from the Genorova CVAE program." />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14 }}>
          {dpp4Evidence.map(([label, value]) => (
            <div key={label} style={{ background: WHITE, border: "1px solid #DCE5F7", borderRadius: 8, padding: 20 }}>
              <div style={{ color: GREY, fontSize: 13, lineHeight: 1.4 }}>{label}</div>
              <div style={{ color: BLUE, fontSize: 20, fontWeight: 900, marginTop: 8 }}>{value}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function AboutContent() {
  return (
    <>
      <section style={{ padding: "76px 24px", background: LGREY }}>
        <div
          style={{
            maxWidth: 1000,
            margin: "0 auto",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,320px),1fr))",
            gap: 28,
          }}
        >
          <div>
            <SectionLabel>Founder</SectionLabel>
            <h1 style={{ color: BLUE, fontSize: 44, lineHeight: 1.1, margin: "8px 0 16px" }}>Pushp Dwivedi</h1>
            <p style={{ color: GREY, fontSize: 16, lineHeight: 1.75, margin: "0 0 18px" }}>
              Final-year B.Pharm student at United Institute of Pharmacy, Prayagraj. Completed a pharmacovigilance
              internship at AIIMS Rishikesh under IPC, and is building Genorova AI alongside PharmaSeNTinel for ADR reporting.
            </p>
            <p style={{ color: INK, fontSize: 17, lineHeight: 1.75, margin: 0, fontWeight: 600 }}>
              "Drug discovery is broken. 12 years, $2.6 billion per approved drug. Genorova AI compresses the early-stage
              molecule exploration from years to minutes — putting computational drug discovery in the hands of every
              researcher, not just well-funded labs."
            </p>
          </div>
          <div style={{ background: WHITE, border: "1px solid #DCE5F7", borderRadius: 8, padding: 24 }}>
            <h2 style={{ color: BLUE, margin: "0 0 16px", fontSize: 20 }}>Current traction</h2>
            {founderStats.map((stat) => (
              <div key={stat} style={{ borderTop: "1px solid #E7EDF8", padding: "13px 0", color: GREY, fontSize: 14, lineHeight: 1.5 }}>
                {stat}
              </div>
            ))}
          </div>
        </div>
      </section>
      <section style={{ padding: "64px 24px", background: WHITE }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <SectionHeading title="Projects" subtitle="Two product tracks, one practical research mission." />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 16 }}>
            <InfoBlock title="Genorova AI" text="Conversational molecule generation and ADMET scoring for early drug discovery workflows." />
            <InfoBlock title="PharmaSeNTinel" text="ADR reporting product shaped by pharmacovigilance work at AIIMS Rishikesh under IPC." />
          </div>
        </div>
      </section>
    </>
  );
}

function LandingHero({ onSignup, onLogin }) {
  return (
    <section style={{ padding: "86px 24px 72px", background: `linear-gradient(180deg, ${WHITE} 0%, ${LGREY} 100%)` }}>
      <div
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,320px),1fr))",
          gap: 34,
          alignItems: "center",
        }}
      >
        <div>
          <SectionLabel>Genorova AI</SectionLabel>
          <h1 style={{ color: BLUE, fontSize: 54, lineHeight: 1.06, margin: "14px 0 18px", letterSpacing: 0 }}>
            Conversational molecule generation for early drug discovery.
          </h1>
          <p style={{ color: GREY, fontSize: 18, lineHeight: 1.7, maxWidth: 620, margin: "0 0 28px" }}>
            Generate DPP-4 inhibitors, score ADMET properties, rank candidates, and export clean research outputs from plain English prompts.
          </p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <button onClick={onSignup} style={{ ...primaryButtonStyle, padding: "13px 24px", fontSize: 16 }}>
              Start Free
            </button>
            <button onClick={onLogin} style={{ ...secondaryButtonStyle, padding: "12px 23px", fontSize: 16 }}>
              Login
            </button>
          </div>
        </div>
        <div style={{ background: WHITE, border: "1px solid #DCE5F7", borderRadius: 8, padding: 24 }}>
          <div style={{ color: BLUE2, fontWeight: 900, marginBottom: 14 }}>Genorova CVAE v1.0</div>
          <div style={{ background: LGREY, borderRadius: 8, padding: 16, color: BLUE, fontSize: 14, lineHeight: 1.6 }}>
            give me 10 potent DPP-4 inhibitors under 500 daltons
          </div>
          <div style={{ marginTop: 16, border: "1px solid #DCE5F7", borderRadius: 8, padding: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginBottom: 16 }}>
              <Metric value="A/B/C/D" label="Grades" />
              <Metric value="0.836" label="Tanimoto" />
              <Metric value="97.3%" label="Filters" />
            </div>
            <p style={{ color: GREY, fontSize: 13, lineHeight: 1.65, margin: 0 }}>
              Generated candidates include QED, molecular weight, Lipinski, Veber, PAINS filters, and export-ready ADMET profiles.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Metric({ value, label }) {
  return (
    <div>
      <div style={{ color: BLUE, fontSize: 20, fontWeight: 900 }}>{value}</div>
      <div style={{ color: GREY, fontSize: 11, fontWeight: 700, marginTop: 3 }}>{label}</div>
    </div>
  );
}

function SectionHeading({ title, subtitle }) {
  return (
    <div style={{ textAlign: "center", marginBottom: 34 }}>
      <h2 style={{ color: BLUE, fontSize: 34, lineHeight: 1.15, margin: "0 0 10px" }}>{title}</h2>
      <p style={{ color: GREY, fontSize: 16, margin: 0 }}>{subtitle}</p>
    </div>
  );
}

function SectionLabel({ children }) {
  return <div style={{ color: BLUE2, fontSize: 12, fontWeight: 900, letterSpacing: "0.08em" }}>{children}</div>;
}

function tableCell(strong = false) {
  return {
    padding: "13px 15px",
    color: strong ? BLUE2 : GREY,
    fontWeight: strong ? 900 : 600,
    fontSize: 14,
  };
}

function InfoBlock({ title, text }) {
  return (
    <div style={{ border: "1px solid #DCE5F7", borderRadius: 8, padding: 22, background: WHITE }}>
      <h3 style={{ color: BLUE, margin: "0 0 10px", fontSize: 19 }}>{title}</h3>
      <p style={{ color: GREY, margin: 0, lineHeight: 1.65 }}>{text}</p>
    </div>
  );
}

function SimplePage({ page }) {
  const copy = pageCopy[page] || pageCopy.contact;
  return (
    <section style={{ padding: "86px 24px", background: LGREY }}>
      <div style={{ maxWidth: 850, margin: "0 auto" }}>
        <SectionLabel>{copy.title}</SectionLabel>
        <h1 style={{ color: BLUE, fontSize: 46, margin: "10px 0 14px", lineHeight: 1.12 }}>{copy.subtitle}</h1>
        {copy.body.map((paragraph) => (
          <p key={paragraph} style={{ color: GREY, fontSize: 17, lineHeight: 1.75 }}>
            {paragraph}
          </p>
        ))}
      </div>
    </section>
  );
}

export function LandingPage({ onSignup, onLogin }) {
  return (
    <div style={shellStyle}>
      <PublicNav onSignup={onSignup} onLogin={onLogin} />
      <LandingHero onSignup={onSignup} onLogin={onLogin} />
      <StatGrid />
      <FeatureGrid />
      <BenchmarkTable />
      <EvidenceSection />
      <Footer />
    </div>
  );
}

export function PublicPage({ page, onSignup, onLogin }) {
  return (
    <div style={shellStyle}>
      <PublicNav onSignup={onSignup} onLogin={onLogin} />
      {page === "features" && <FeatureGrid />}
      {page === "benchmarks" && (
        <>
          <BenchmarkTable />
          <EvidenceSection />
        </>
      )}
      {page === "about" && <AboutContent />}
      {["pricing", "roadmap", "contact"].includes(page) && <SimplePage page={page} />}
      <Footer />
    </div>
  );
}

export function AuthModal({ mode, onClose, onSuccess }) {
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState(mode);
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async () => {
    setLoading(true);
    setError("");
    const endpoint = view === "login" ? "/auth/login" : "/auth/signup";
    const body =
      view === "login"
        ? { email: form.email, password: form.password }
        : { name: form.name, email: form.email, password: form.password };
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (response.ok) {
        onSuccess();
      } else {
        const data = await response.json();
        setError(data.detail || (view === "login" ? "Login failed" : "Signup failed"));
      }
    } catch {
      setError("Connection error. Try again.");
    }
    setLoading(false);
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(15,45,110,0.58)",
        backdropFilter: "blur(8px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div style={{ background: WHITE, borderRadius: 8, padding: 34, width: "100%", maxWidth: 410 }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div style={{ display: "inline-flex" }}>
            <GenorovaLogo size={32} showText />
          </div>
          <div style={{ color: GREY, marginTop: 10, fontSize: 14 }}>
            {view === "login" ? "Sign in to your workspace" : "Create your free account"}
          </div>
        </div>

        {error && (
          <div style={{ background: "#FFF0F0", border: "1px solid #FFB3B3", color: "#B42318", padding: 11, borderRadius: 8, fontSize: 13, marginBottom: 18 }}>
            {error}
          </div>
        )}

        {view === "signup" && (
          <Field label="Full Name" value={form.name} onChange={(value) => set("name", value)} placeholder="Pushp Dwivedi" />
        )}
        <Field label="Email" type="email" value={form.email} onChange={(value) => set("email", value)} placeholder="researcher@lab.org" onEnter={submit} />
        <Field label="Password" type="password" value={form.password} onChange={(value) => set("password", value)} placeholder="••••••••" onEnter={submit} />

        <button
          onClick={submit}
          disabled={loading}
          style={{ ...primaryButtonStyle, width: "100%", padding: 12, opacity: loading ? 0.7 : 1 }}
        >
          {loading ? (view === "login" ? "Signing in..." : "Creating account...") : view === "login" ? "Sign In" : "Create Account"}
        </button>

        <div style={{ textAlign: "center", marginTop: 16, color: GREY, fontSize: 13 }}>
          {view === "login" ? "No account? " : "Already have an account? "}
          <button
            type="button"
            style={{ color: BLUE2, background: "transparent", border: "none", cursor: "pointer", fontWeight: 800, padding: 0 }}
            onClick={() => {
              setView(view === "login" ? "signup" : "login");
              setError("");
            }}
          >
            {view === "login" ? "Sign up" : "Sign in"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text", onEnter }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ color: GREY, fontSize: 13, display: "block", marginBottom: 6, fontWeight: 700 }}>{label}</label>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        type={type}
        placeholder={placeholder}
        onKeyDown={(event) => {
          if (event.key === "Enter" && onEnter) onEnter();
        }}
        style={{
          width: "100%",
          border: "1.5px solid #C7D8FF",
          borderRadius: 8,
          padding: "10px 13px",
          fontSize: 14,
          color: BLUE,
          boxSizing: "border-box",
          outline: "none",
        }}
      />
    </div>
  );
}
