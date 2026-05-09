import { useEffect, useState } from "react";
import GenorovaChatAppV11 from "./GenorovaChatAppV11";
import { AuthProvider } from "./auth";
import GenorovaLogo from "./components/GenorovaLogo";

const BLUE = "#0F2D6E";
const BLUE2 = "#1A4BAD";
const CYAN = "#00CFFF";
const WHITE = "#FFFFFF";
const LGREY = "#F0F4FF";
const MGREY = "#E0E8FF";
const GREY = "#6B7FAB";

async function checkAuth() {
  try {
    const r = await fetch("/auth/me", { credentials: "include" });
    return r.ok;
  } catch {
    return false;
  }
}

function LandingNav({ onSignup, onLogin }) {
  return (
    <nav
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        background: "rgba(255,255,255,0.95)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid #E0E8FF",
        padding: "0 32px",
        height: 64,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        boxShadow: "0 1px 12px rgba(15,45,110,0.08)",
      }}
    >
      <GenorovaLogo size={36} showText />
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        {["Features", "Benchmarks", "About"].map((label) => (
          <span
            key={label}
            style={{ color: GREY, fontSize: 14, cursor: "pointer", fontWeight: 500 }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = BLUE2;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = GREY;
            }}
          >
            {label}
          </span>
        ))}
        <button
          onClick={onLogin}
          style={{
            color: BLUE2,
            background: "transparent",
            border: `1.5px solid ${BLUE2}`,
            padding: "7px 18px",
            borderRadius: 8,
            cursor: "pointer",
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          Log In
        </button>
        <button
          onClick={onSignup}
          style={{
            background: BLUE2,
            color: WHITE,
            border: "none",
            padding: "8px 20px",
            borderRadius: 8,
            cursor: "pointer",
            fontSize: 14,
            fontWeight: 700,
            boxShadow: "0 4px 12px rgba(26,75,173,0.3)",
          }}
        >
          Sign Up Free
        </button>
      </div>
    </nav>
  );
}

function LandingPage({ onSignup, onLogin }) {
  return (
    <div style={{ background: WHITE, fontFamily: '"Inter",system-ui,sans-serif', minHeight: "100vh", color: BLUE }}>
      <LandingNav onSignup={onSignup} onLogin={onLogin} />

      <section
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "120px 24px 80px",
          background: `linear-gradient(160deg, ${WHITE} 0%, ${LGREY} 60%, ${MGREY} 100%)`,
        }}
      >
        <div style={{ maxWidth: 820 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: "rgba(0,207,255,0.1)",
              border: "1px solid rgba(0,207,255,0.4)",
              borderRadius: 24,
              padding: "6px 18px",
              marginBottom: 28,
            }}
          >
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: CYAN, boxShadow: `0 0 8px ${CYAN}` }} />
            <span style={{ color: BLUE2, fontSize: 12, fontWeight: 600, letterSpacing: "0.08em" }}>
              AI-POWERED DRUG DISCOVERY
            </span>
          </div>

          <h1
            style={{
              fontSize: 52,
              fontWeight: 800,
              lineHeight: 1.15,
              color: BLUE,
              marginBottom: 20,
              letterSpacing: 0,
            }}
          >
            Generate Drug Candidates
            <br />
            <span
              style={{
                background: `linear-gradient(90deg, ${BLUE2}, ${CYAN})`,
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              With Conversational AI
            </span>
          </h1>

          <p
            style={{
              fontSize: 18,
              color: GREY,
              lineHeight: 1.7,
              maxWidth: 580,
              margin: "0 auto 40px",
              fontWeight: 400,
            }}
          >
            Tell Genorova what you need in plain language. Get ranked, drug-safe molecular candidates with full ADMET
            profiles in seconds.
          </p>

          <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap", marginBottom: 56 }}>
            <button
              onClick={onSignup}
              style={{
                background: `linear-gradient(135deg, ${BLUE2}, #2563EB)`,
                color: WHITE,
                border: "none",
                padding: "14px 36px",
                borderRadius: 8,
                fontSize: 16,
                fontWeight: 700,
                cursor: "pointer",
                boxShadow: "0 8px 24px rgba(26,75,173,0.35)",
                transition: "transform 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-2px)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "none";
              }}
            >
              Start for Free →
            </button>
            <button
              onClick={onLogin}
              style={{
                background: WHITE,
                color: BLUE2,
                border: `1.5px solid ${BLUE2}`,
                padding: "14px 36px",
                borderRadius: 8,
                fontSize: 16,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Launch Dashboard
            </button>
          </div>

          <div
            style={{
              background: WHITE,
              borderRadius: 8,
              border: "1px solid #C7D8FF",
              boxShadow: "0 20px 60px rgba(15,45,110,0.12)",
              padding: 24,
              maxWidth: 600,
              margin: "0 auto",
              textAlign: "left",
            }}
          >
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              {["#FF5F57", "#FFBD2E", "#28CA41"].map((c) => (
                <div key={c} style={{ width: 12, height: 12, borderRadius: "50%", background: c }} />
              ))}
              <span style={{ color: GREY, fontSize: 11, marginLeft: 8 }}>Genorova AI Workspace</span>
            </div>
            <div style={{ marginBottom: 12 }}>
              <div
                style={{
                  background: LGREY,
                  borderRadius: 8,
                  padding: "10px 14px",
                  display: "inline-block",
                  maxWidth: "85%",
                }}
              >
                <span style={{ color: BLUE, fontSize: 13 }}>
                  "Generate 10 DPP-4 inhibitors under 450 daltons with high drug-likeness"
                </span>
              </div>
            </div>
            <div
              style={{
                background: `linear-gradient(135deg, ${LGREY}, ${MGREY})`,
                borderRadius: 8,
                border: "1px solid #C7D8FF",
                padding: "12px 14px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <GenorovaLogo size={18} showText={false} />
                <span style={{ color: BLUE2, fontSize: 12, fontWeight: 600 }}>Genorova CVAE v1.0</span>
                <span
                  style={{
                    background: "rgba(0,207,255,0.15)",
                    color: BLUE2,
                    fontSize: 10,
                    padding: "2px 8px",
                    borderRadius: 8,
                    fontWeight: 600,
                  }}
                >
                  SNN 0.611 ★
                </span>
              </div>
              <p style={{ color: BLUE, fontSize: 12, lineHeight: 1.6, margin: 0 }}>
                Generated 10 computational candidates. Top results include RDKit ADMET predictions, QED, molecular
                weight, Lipinski status, and clear limitations for wet-lab follow-up.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section style={{ background: BLUE, padding: "40px 24px" }}>
        <div
          style={{
            maxWidth: 900,
            margin: "0 auto",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))",
            gap: 24,
            textAlign: "center",
          }}
        >
          {[
            { n: "0.611", l: "SNN/Test Score", note: "Beats REINVENT 0.58" },
            { n: "97.3%", l: "ADMET Filter Pass", note: "Medicinal chemistry" },
            { n: "0.836", l: "DPP-4 Tanimoto", note: "Structural similarity benchmark" },
            { n: "6.78M", l: "Model Parameters", note: "Trained CVAE" },
            { n: "< 60s", l: "Generation Time", note: "Per query" },
          ].map((s) => (
            <div key={s.l}>
              <div style={{ color: CYAN, fontSize: 28, fontWeight: 800, marginBottom: 4 }}>{s.n}</div>
              <div style={{ color: WHITE, fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{s.l}</div>
              <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 11 }}>{s.note}</div>
            </div>
          ))}
        </div>
      </section>

      <section style={{ padding: "80px 24px", background: LGREY }}>
        <div style={{ maxWidth: 960, margin: "0 auto" }}>
          <h2 style={{ textAlign: "center", fontSize: 36, fontWeight: 800, color: BLUE, marginBottom: 12 }}>
            How It Works
          </h2>
          <p style={{ textAlign: "center", color: GREY, fontSize: 16, marginBottom: 48 }}>
            Natural language to computational candidates in seconds
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 20 }}>
            {[
              { n: "01", t: "Describe", d: "Type the target, constraints, and disease area in plain English." },
              { n: "02", t: "Generate", d: "The CVAE model creates novel drug-like SMILES candidates." },
              { n: "03", t: "Score", d: "Automatic ADMET screening estimates safety and drug-likeness." },
              { n: "04", t: "Review", d: "Ranked candidates include trust scores, caveats, and limitations." },
              { n: "05", t: "Export", d: "Use the results for further computational or wet-lab planning." },
            ].map((s) => (
              <div
                key={s.n}
                style={{
                  background: WHITE,
                  borderRadius: 8,
                  padding: 24,
                  border: "1px solid #C7D8FF",
                  boxShadow: "0 4px 16px rgba(15,45,110,0.06)",
                }}
              >
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 8,
                    background: `linear-gradient(135deg,${BLUE2},${CYAN})`,
                    color: WHITE,
                    fontWeight: 800,
                    fontSize: 13,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginBottom: 14,
                  }}
                >
                  {s.n}
                </div>
                <div style={{ color: BLUE, fontWeight: 700, fontSize: 15, marginBottom: 8 }}>{s.t}</div>
                <div style={{ color: GREY, fontSize: 13, lineHeight: 1.6 }}>{s.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={{ padding: "80px 24px", background: WHITE }}>
        <div style={{ maxWidth: 800, margin: "0 auto", textAlign: "center" }}>
          <h2 style={{ fontSize: 34, fontWeight: 800, color: BLUE, marginBottom: 12 }}>Benchmark Results</h2>
          <p style={{ color: GREY, marginBottom: 40 }}>Evaluated on the official MOSES benchmark suite</p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ background: BLUE }}>
                  {["Model", "SNN/Test ↑", "Validity", "Filters ↑"].map((h) => (
                    <th key={h} style={{ color: WHITE, padding: "12px 16px", textAlign: "left", fontWeight: 600 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { m: "Genorova AI", snn: "0.611 ★", v: "70.9%", f: "97.3% ★", us: true },
                  { m: "REINVENT", snn: "0.58", v: "96.8%", f: "~95%", us: false },
                  { m: "MolGPT", snn: "0.56", v: "98.5%", f: "~94%", us: false },
                  { m: "JT-VAE", snn: "0.54", v: "100%", f: "~97%", us: false },
                ].map((r) => (
                  <tr
                    key={r.m}
                    style={{
                      background: r.us ? "rgba(0,207,255,0.06)" : r.m === "REINVENT" ? LGREY : WHITE,
                      borderBottom: "1px solid #E0E8FF",
                    }}
                  >
                    <td style={{ padding: "12px 16px", color: r.us ? BLUE2 : BLUE, fontWeight: r.us ? 700 : 500 }}>
                      {r.m}
                    </td>
                    <td style={{ padding: "12px 16px", color: r.us ? "#0066CC" : GREY, fontWeight: r.us ? 700 : 400 }}>
                      {r.snn}
                    </td>
                    <td style={{ padding: "12px 16px", color: GREY }}>{r.v}</td>
                    <td style={{ padding: "12px 16px", color: r.us ? "#0066CC" : GREY, fontWeight: r.us ? 700 : 400 }}>
                      {r.f}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section
        style={{
          padding: "80px 24px",
          textAlign: "center",
          background: `linear-gradient(135deg, ${BLUE} 0%, ${BLUE2} 100%)`,
        }}
      >
        <h2 style={{ color: WHITE, fontSize: 36, fontWeight: 800, marginBottom: 12 }}>
          Start Exploring Drug Candidates
        </h2>
        <p style={{ color: "rgba(255,255,255,0.7)", fontSize: 16, marginBottom: 32 }}>
          Free research access. No credit card required.
        </p>
        <button
          onClick={onSignup}
          style={{
            background: CYAN,
            color: BLUE,
            padding: "14px 40px",
            borderRadius: 8,
            fontSize: 16,
            fontWeight: 800,
            cursor: "pointer",
            border: "none",
            boxShadow: "0 8px 24px rgba(0,207,255,0.4)",
          }}
        >
          Get Started Free →
        </button>
        <div style={{ marginTop: 20, color: "rgba(255,255,255,0.5)", fontSize: 12 }}>
          Computational research platform. Generated molecules require wet-lab validation.
        </div>
      </section>

      <footer style={{ background: BLUE, borderTop: "1px solid rgba(255,255,255,0.1)", padding: "32px 24px" }}>
        <div
          style={{
            maxWidth: 960,
            margin: "0 auto",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 16,
          }}
        >
          <GenorovaLogo size={28} showText />
          <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, textAlign: "right" }}>
            © 2026 Genorova AI · Built by Pushp Dwivedi
            <br />
            Not a clinical decision tool. Outputs require experimental validation.
          </div>
        </div>
      </footer>
    </div>
  );
}

function AuthModal({ mode, onClose, onSuccess }) {
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
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (r.ok) {
        onSuccess();
      } else {
        const data = await r.json();
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
        background: "rgba(15,45,110,0.6)",
        backdropFilter: "blur(8px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: WHITE,
          borderRadius: 8,
          padding: 36,
          width: "100%",
          maxWidth: 400,
          boxShadow: "0 24px 64px rgba(15,45,110,0.25)",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{ display: "inline-flex" }}>
            <GenorovaLogo size={32} showText />
          </div>
          <div style={{ color: GREY, marginTop: 10, fontSize: 14 }}>
            {view === "login" ? "Sign in to your workspace" : "Create your free account"}
          </div>
        </div>

        {error && (
          <div
            style={{
              background: "#FFF0F0",
              border: "1px solid #FFB3B3",
              color: "#CC0000",
              padding: "10px 14px",
              borderRadius: 8,
              fontSize: 13,
              marginBottom: 20,
            }}
          >
            {error}
          </div>
        )}

        {view === "signup" && (
          <div style={{ marginBottom: 14 }}>
            <label style={{ color: GREY, fontSize: 13, display: "block", marginBottom: 5 }}>Full Name</label>
            <input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              type="text"
              placeholder="Dr. Jane Smith"
              style={{
                width: "100%",
                border: "1.5px solid #C7D8FF",
                borderRadius: 8,
                padding: "10px 14px",
                fontSize: 14,
                color: BLUE,
                boxSizing: "border-box",
                outline: "none",
              }}
            />
          </div>
        )}
        <div style={{ marginBottom: 14 }}>
          <label style={{ color: GREY, fontSize: 13, display: "block", marginBottom: 5 }}>Email</label>
          <input
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
            type="email"
            placeholder="researcher@university.edu"
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            style={{
              width: "100%",
              border: "1.5px solid #C7D8FF",
              borderRadius: 8,
              padding: "10px 14px",
              fontSize: 14,
              color: BLUE,
              boxSizing: "border-box",
              outline: "none",
            }}
          />
        </div>
        <div style={{ marginBottom: 20 }}>
          <label style={{ color: GREY, fontSize: 13, display: "block", marginBottom: 5 }}>Password</label>
          <input
            value={form.password}
            onChange={(e) => set("password", e.target.value)}
            type="password"
            placeholder="••••••••"
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            style={{
              width: "100%",
              border: "1.5px solid #C7D8FF",
              borderRadius: 8,
              padding: "10px 14px",
              fontSize: 14,
              color: BLUE,
              boxSizing: "border-box",
              outline: "none",
            }}
          />
        </div>

        <button
          onClick={submit}
          disabled={loading}
          style={{
            width: "100%",
            background: `linear-gradient(135deg,${BLUE2},#2563EB)`,
            color: WHITE,
            border: "none",
            padding: 12,
            borderRadius: 8,
            fontWeight: 700,
            fontSize: 15,
            cursor: "pointer",
            opacity: loading ? 0.7 : 1,
            boxShadow: "0 4px 16px rgba(26,75,173,0.3)",
          }}
        >
          {loading ? (view === "login" ? "Signing in..." : "Creating account...") : view === "login" ? "Sign In" : "Create Account"}
        </button>

        <div style={{ textAlign: "center", marginTop: 16, color: GREY, fontSize: 13 }}>
          {view === "login" ? (
            <>
              No account?{" "}
              <span
                style={{ color: BLUE2, cursor: "pointer", fontWeight: 600 }}
                onClick={() => {
                  setView("signup");
                  setError("");
                }}
              >
                Sign up free
              </span>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <span
                style={{ color: BLUE2, cursor: "pointer", fontWeight: 600 }}
                onClick={() => {
                  setView("login");
                  setError("");
                }}
              >
                Sign in
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState("loading");
  const [modal, setModal] = useState(null);

  useEffect(() => {
    checkAuth().then((ok) => setView(ok ? "workspace" : "landing"));
  }, []);

  const handleAuthSuccess = () => {
    setModal(null);
    setView("workspace");
  };

  if (view === "loading") {
    return (
      <div style={{ background: WHITE, height: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <GenorovaLogo size={48} showText />
      </div>
    );
  }

  if (view === "workspace") {
    return (
      <AuthProvider>
        <GenorovaChatAppV11 />
      </AuthProvider>
    );
  }

  return (
    <>
      <LandingPage onSignup={() => setModal("signup")} onLogin={() => setModal("login")} />
      {modal && <AuthModal mode={modal} onClose={() => setModal(null)} onSuccess={handleAuthSuccess} />}
    </>
  );
}
