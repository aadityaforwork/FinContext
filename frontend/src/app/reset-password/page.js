"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../context/AuthContext";
import { supabase } from "../lib/supabase";
import AuthCard, { authInputStyle, authButtonStyle } from "../components/AuthCard";

export default function ResetPasswordPage() {
  const { updatePassword } = useAuth();
  const router = useRouter();

  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  // Supabase fires PASSWORD_RECOVERY after the user lands here from the email link.
  // We wait for that event (or an existing session) before allowing password update.
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) setReady(true);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY" || session) setReady(true);
    });
    return () => subscription.unsubscribe();
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    setSubmitting(true);
    try {
      await updatePassword(password);
      setInfo("Password updated. Redirecting…");
      setTimeout(() => router.replace("/"), 1200);
    } catch (err) {
      setError(err.message || "Could not update password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="Choose a new password" subtitle="At least 8 characters">
      {!ready ? (
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)" }}>
          Validating your reset link… If nothing happens, request a new link from{" "}
          <Link href="/forgot-password" style={{ color: "var(--color-accent-secondary)", fontWeight: 600 }}>forgot password</Link>.
        </p>
      ) : (
        <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>NEW PASSWORD</span>
            <input type="password" autoComplete="new-password" required minLength={8} value={password}
              onChange={(e) => setPassword(e.target.value)} style={authInputStyle} placeholder="At least 8 characters" />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>CONFIRM PASSWORD</span>
            <input type="password" autoComplete="new-password" required minLength={8} value={confirm}
              onChange={(e) => setConfirm(e.target.value)} style={authInputStyle} placeholder="Repeat password" />
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
            {submitting ? "Updating…" : "Update password"}
          </button>
        </form>
      )}
    </AuthCard>
  );
}
