import { createContext, useContext, useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const AUTH_PREFIX = API_BASE_URL ? `${API_BASE_URL}/auth` : "/auth";

const AuthContext = createContext(null);

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

async function authRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(`${AUTH_PREFIX}${path}`, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch {
    const error = new Error("Genorova could not reach the backend service.");
    error.status = 0;
    error.code = "backend_unavailable";
    throw error;
  }

  const payload = await readJson(response);
  if (!response.ok) {
    const error = new Error(payload.detail || "Authentication request failed.");
    error.status = response.status;
    throw error;
  }

  return payload;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState(null);

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      try {
        const payload = await authRequest("/me", { method: "GET" });
        if (active) {
          setUser(payload.user || null);
          setBootstrapError(null);
        }
      } catch (error) {
        if (active && error.status === 401) {
          setUser(null);
          setBootstrapError(null);
        } else if (active) {
          setUser(null);
          setBootstrapError(error);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    bootstrap();

    return () => {
      active = false;
    };
  }, []);

  async function signup(credentials) {
    const payload = await authRequest("/signup", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
    setBootstrapError(null);
    setUser(payload.user || null);
    return payload.user || null;
  }

  async function login(credentials) {
    const payload = await authRequest("/login", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
    setBootstrapError(null);
    setUser(payload.user || null);
    return payload.user || null;
  }

  async function logout() {
    await authRequest("/logout", { method: "POST" });
    setUser(null);
  }

  async function refreshUser() {
    try {
      const payload = await authRequest("/me", { method: "GET" });
      setBootstrapError(null);
      setUser(payload.user || null);
      return payload.user || null;
    } catch (error) {
      if (error.status === 401) {
        setBootstrapError(null);
        setUser(null);
        return null;
      }
      setBootstrapError(error);
      throw error;
    }
  }

  function clearBootstrapError() {
    setBootstrapError(null);
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: Boolean(user),
        signup,
        login,
        logout,
        refreshUser,
        bootstrapError,
        clearBootstrapError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return value;
}
