"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../context/AuthContext";
import AuthCard, {
  authInputStyle,
  authButtonStyle,
  authGoogleButtonStyle,
  GoogleIcon,
} from "../components/AuthCard";

export default function SignupPage() {
  const { user, loading, signup, googleLogin } = useAuth();
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    setSubmitting(true);
    try {
      await signup(email, password, name || null);
      // Supabase may require email confirmation depending on project settings.
      // If so, user won't be logged in immediately — show a message.
      if (!user) {
        setInfo("Check your email to confirm your account, then sign in.");
      } else {
        router.replace("/");
      }
    } catch (err) {
      setError(err.message || "Signup failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="Create your account" subtitle="Free to start. No card required.">
      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>NAME (optional)</span>
          <input type="text" autoComplete="name" value={name}
            onChange={(e) => setName(e.target.value)} style={authInputStyle} placeholder="Jane Doe" />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>EMAIL</span>
          <input type="email" autoComplete="email" required value={email}
            onChange={(e) => setEmail(e.target.value)} style={authInputStyle} placeholder="you@example.com" />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>PASSWORD</span>
          <input type="password" autoComplete="new-password" required minLength={8} value={password}
            onChange={(e) => setPassword(e.target.value)} style={authInputStyle} placeholder="At least 8 characters" />
        </label>

        {error && (
          <div style={{ fontSize: "13px", color: "var(--color-accent-red)", background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.25)", borderRadius: "8px", padding: "8px 12px" }}>{error}</div>
        )}
        {info && (
          <div style={{ fontSize: "13px", color: "var(--color-accent-green)", background: "rgba(16,185,129,0.08)",
            border: "1px solid rgba(16,185,129,0.25)", borderRadius: "8px", padding: "8px 12px" }}>{info}</div>
        )}

        <button type="submit" disabled={submitting}
          style={{ ...authButtonStyle, opacity: submitting ? 0.6 : 1, marginTop: "4px" }}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <div style={{ display: "flex", alignItems: "center", gap: "12px", margin: "18px 0" }}>
        <div style={{ flex: 1, height: "1px", background: "var(--border-subtle)" }} />
        <span style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase" }}>or</span>
        <div style={{ flex: 1, height: "1px", background: "var(--border-subtle)" }} />
      </div>
      <button type="button" onClick={googleLogin} style={authGoogleButtonStyle} aria-label="Continue with Google">
        <GoogleIcon />
        <span>Continue with Google</span>
      </button>

      <p style={{ textAlign: "center", marginTop: "20px", fontSize: "13px", color: "var(--color-text-secondary)" }}>
        Already have an account?{" "}
        <Link href="/login" style={{ color: "var(--color-accent-secondary)", fontWeight: 600 }}>Sign in</Link>
      </p>
    </AuthCard>
  );
}
