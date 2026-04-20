"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "../context/AuthContext";
import AuthCard, { authInputStyle, authButtonStyle } from "../components/AuthCard";

export default function ForgotPasswordPage() {
  const { resetPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    setSubmitting(true);
    try {
      await resetPassword(email);
      setInfo("If an account exists for that email, a reset link is on the way.");
    } catch (err) {
      setError(err.message || "Could not send reset email");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="Reset your password" subtitle="We'll email you a link to choose a new one">
      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>EMAIL</span>
          <input type="email" autoComplete="email" required value={email}
            onChange={(e) => setEmail(e.target.value)} style={authInputStyle} placeholder="you@example.com" />
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
          {submitting ? "Sending…" : "Send reset link"}
        </button>
      </form>

      <p style={{ textAlign: "center", marginTop: "20px", fontSize: "13px", color: "var(--color-text-secondary)" }}>
        Remembered it?{" "}
        <Link href="/login" style={{ color: "var(--color-accent-secondary)", fontWeight: 600 }}>Sign in</Link>
      </p>
    </AuthCard>
  );
}
