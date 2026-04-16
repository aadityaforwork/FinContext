"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { API_BASE, apiJson, installFetchCredentials } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState({ password: true, google: false });

  // Install the global fetch patch exactly once
  useEffect(() => {
    installFetchCredentials();
  }, []);

  // Fetch current user on mount; try a silent refresh if unauthorized
  const fetchMe = useCallback(async () => {
    try {
      const me = await apiJson("/api/auth/me");
      setUser(me);
      return me;
    } catch (err) {
      if (err.status === 401) {
        // Try refresh silently
        try {
          await apiJson("/api/auth/refresh", { method: "POST" });
          const me = await apiJson("/api/auth/me");
          setUser(me);
          return me;
        } catch {
          setUser(null);
          return null;
        }
      }
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await fetchMe();
      // Also load which providers are available
      try {
        const p = await apiJson("/api/auth/providers");
        setProviders(p);
      } catch {
        /* ignore */
      }
      setLoading(false);
    })();
  }, [fetchMe]);

  const login = useCallback(async (email, password) => {
    const me = await apiJson("/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setUser(me);
    return me;
  }, []);

  const signup = useCallback(async (email, password, name) => {
    const me = await apiJson("/api/auth/signup", {
      method: "POST",
      body: { email, password, name },
    });
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiJson("/api/auth/logout", { method: "POST" });
    } catch {
      /* ignore — still clear locally */
    }
    setUser(null);
  }, []);

  const googleLogin = useCallback(() => {
    // Top-level navigation so Google's OAuth flow can set/read cookies on the
    // backend origin. The backend will redirect back to FRONTEND_URL after.
    window.location.href = `${API_BASE}/api/auth/google/start`;
  }, []);

  const value = {
    user,
    loading,
    providers,
    login,
    signup,
    logout,
    googleLogin,
    refresh: fetchMe,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
