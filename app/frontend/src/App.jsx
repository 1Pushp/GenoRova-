import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import GenorovaWorkspace from "./GenorovaWorkspace";
import { AuthProvider } from "./auth";
import GenorovaLogo from "./components/GenorovaLogo";
import { AuthModal, LandingPage, PublicPage } from "./PublicSite";

const WHITE = "#FFFFFF";

async function checkAuth() {
  try {
    const response = await fetch("/auth/me", { credentials: "include" });
    return response.ok;
  } catch {
    return false;
  }
}

function LoadingScreen() {
  return (
    <div
      style={{
        background: WHITE,
        height: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <GenorovaLogo size={48} showText />
    </div>
  );
}

function LandingWrapper() {
  const [modal, setModal] = useState(null);
  const navigate = useNavigate();

  const handleAuthSuccess = () => {
    setModal(null);
    navigate("/workspace");
  };

  return (
    <>
      <LandingPage onSignup={() => setModal("signup")} onLogin={() => setModal("login")} />
      {modal && <AuthModal mode={modal} onClose={() => setModal(null)} onSuccess={handleAuthSuccess} />}
    </>
  );
}

function PublicPageWrapper({ page }) {
  const [modal, setModal] = useState(null);
  const navigate = useNavigate();

  const handleAuthSuccess = () => {
    setModal(null);
    navigate("/workspace");
  };

  return (
    <>
      <PublicPage page={page} onSignup={() => setModal("signup")} onLogin={() => setModal("login")} />
      {modal && <AuthModal mode={modal} onClose={() => setModal(null)} onSuccess={handleAuthSuccess} />}
    </>
  );
}

function ProtectedWorkspace() {
  const [authState, setAuthState] = useState("loading");

  useEffect(() => {
    checkAuth().then((ok) => setAuthState(ok ? "authenticated" : "anonymous"));
  }, []);

  if (authState === "loading") {
    return <LoadingScreen />;
  }

  if (authState !== "authenticated") {
    return <Navigate to="/" replace />;
  }

  return (
    <AuthProvider>
      <GenorovaWorkspace />
    </AuthProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingWrapper />} />
        <Route path="/features" element={<PublicPageWrapper page="features" />} />
        <Route path="/benchmarks" element={<PublicPageWrapper page="benchmarks" />} />
        <Route path="/about" element={<PublicPageWrapper page="about" />} />
        <Route path="/pricing" element={<PublicPageWrapper page="pricing" />} />
        <Route path="/roadmap" element={<PublicPageWrapper page="roadmap" />} />
        <Route path="/contact" element={<PublicPageWrapper page="contact" />} />
        <Route path="/workspace/*" element={<ProtectedWorkspace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
