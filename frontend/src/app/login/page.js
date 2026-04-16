"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../context/AuthContext";
import AuthCard, {
  authInputStyle,
  authButtonStyle,
  authGoogleButtonStyle,
  GoogleIcon,
} from "../components/AuthCard";

export default function LoginPage() {
  const { user, loading, login, googleLogin, providers } = useAuth();
  const router = useRouter();
  const search = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Redirect if already logged in
  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  // Surface OAuth errors passed via query string
  useEffect(() => {
    const err = search.get("error");
    if (err) setError(formatOAuthError(err));
  }, [search]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="Welcome back" subtitle="Sign in to continue">
      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>
            EMAIL
          </span>
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={authInputStyle}
            placeholder="you@example.com"
          />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>
            PASSWORD
          </span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={authInputStyle}
            placeholder="••••••••"
          />
        </label>

        {error && (
          <div
            style={{
              fontSize: "13px",
              color: "var(--color-accent-red)",
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: "8px",
              padding: "8px 12px",
            }}
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          style={{ ...authButtonStyle, opacity: submitting ? 0.6 : 1, marginTop: "4px" }}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {providers.google && (
        <>
          <Divider label="or" />
          <button
            type="button"
            onClick={googleLogin}
            style={authGoogleButtonStyle}
            aria-label="Continue with Google"
          >
            <GoogleIcon />
            <span>Continue with Google</span>
          </button>
        </>
      )}

      <p style={{ textAlign: "center", marginTop: "20px", fontSize: "13px", color: "var(--color-text-secondary)" }}>
        Don&apos;t have an account?{" "}
        <Link href="/signup" style={{ color: "var(--color-accent-secondary)", fontWeight: 600 }}>
          Sign up
        </Link>
      </p>
    </AuthCard>
  );
}

function Divider({ label }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "12px", margin: "18px 0" }}>
      <div style={{ flex: 1, height: "1px", background: "var(--border-subtle)" }} />
      <span style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase" }}>
        {label}
      </span>
      <div style={{ flex: 1, height: "1px", background: "var(--border-subtle)" }} />
    </div>
  );
}

function formatOAuthError(code) {
  const map = {
    invalid_state: "Sign-in was interrupted. Please try again.",
    missing_code: "Google did not return a valid response.",
    token_exchange_failed: "Could not complete Google sign-in.",
    userinfo_failed: "Could not fetch your Google profile.",
    email_not_verified: "Please verify your Google email before signing in.",
    oauth_not_configured: "Google sign-in is not configured on this server.",
    google_unreachable: "Could not reach Google. Please try again.",
  };
  return map[code] || `Sign-in failed (${code})`;
}
