"use client";

import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useToast } from "./Toast";

/**
 * SettingsView — minimal account + app preferences screen.
 * Replaces the second sidebar nav item. Kept lightweight on purpose;
 * we expand as the product grows (notifications, billing, integrations).
 */
export default function SettingsView() {
  const { user, logout, updatePassword } = useAuth();
  const toast = useToast();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSignOut = async () => {
    try {
      await logout();
      toast.success("Signed out.");
    } catch (e) {
      toast.error("Could not sign out.");
    }
  };

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    if (pw.length < 8) { toast.error("Password must be at least 8 characters."); return; }
    if (pw !== pw2)    { toast.error("Passwords don't match."); return; }
    setSubmitting(true);
    try {
      await updatePassword(pw);
      toast.success("Password updated.");
      setPw(""); setPw2("");
    } catch (err) {
      toast.error(err?.message || "Could not update password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: "640px", margin: "0 auto" }}>
      <header style={{ marginBottom: "28px" }}>
        <h1
          style={{
            fontSize: "22px",
            fontWeight: 800,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.01em",
          }}
        >
          Settings
        </h1>
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
          Account preferences and access controls.
        </p>
      </header>

      {/* ACCOUNT */}
      <Section title="Account">
        <Row label="Email" value={user?.email || "—"} />
        <Row label="Name"  value={user?.user_metadata?.name || user?.user_metadata?.full_name || "—"} />
        <Row label="User ID" value={user?.id || "—"} mono />
      </Section>

      {/* PASSWORD */}
      <Section title="Change password">
        <form onSubmit={handlePasswordChange} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <input
            type="password"
            placeholder="New password (min 8 characters)"
            autoComplete="new-password"
            minLength={8}
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            style={inputStyle}
          />
          <input
            type="password"
            placeholder="Confirm new password"
            autoComplete="new-password"
            minLength={8}
            value={pw2}
            onChange={(e) => setPw2(e.target.value)}
            style={inputStyle}
          />
          <button
            type="submit"
            disabled={submitting || !pw || !pw2}
            style={{
              alignSelf: "flex-start",
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-secondary))",
              color: "white",
              fontSize: "12px",
              fontWeight: 700,
              cursor: submitting ? "wait" : "pointer",
              opacity: submitting || !pw || !pw2 ? 0.6 : 1,
            }}
          >
            {submitting ? "Updating…" : "Update password"}
          </button>
        </form>
      </Section>

      {/* COMPLIANCE */}
      <Section title="Disclaimers">
        <p
          style={{
            fontSize: "12px",
            color: "var(--color-text-secondary)",
            lineHeight: 1.6,
            padding: "12px 14px",
            background: "rgba(245,158,11,0.06)",
            border: "1px solid rgba(245,158,11,0.20)",
            borderRadius: "8px",
          }}
        >
          FinContext is for informational and educational purposes only.
          We are not a SEBI-registered Research Analyst or Investment Adviser.
          Nothing here is investment advice or a recommendation to buy or sell any
          security. Markets carry risk — please consult a qualified, registered
          adviser before making investment decisions.
        </p>
      </Section>

      {/* DANGER ZONE */}
      <Section title="Session">
        <button
          type="button"
          onClick={handleSignOut}
          style={{
            padding: "8px 16px",
            borderRadius: "8px",
            border: "1px solid rgba(239,68,68,0.30)",
            background: "rgba(239,68,68,0.06)",
            color: "var(--color-accent-red)",
            fontSize: "12px",
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Sign out
        </button>
      </Section>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section
      style={{
        marginBottom: "24px",
        padding: "18px 20px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "12px",
      }}
    >
      <h2
        style={{
          fontSize: "11px",
          fontWeight: 800,
          textTransform: "uppercase",
          letterSpacing: "0.10em",
          color: "var(--color-text-muted)",
          marginBottom: "14px",
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value, mono }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 0",
        borderBottom: "1px solid var(--border-subtle)",
        gap: "12px",
      }}
    >
      <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>
        {label}
      </span>
      <span
        style={{
          fontSize: "12.5px",
          color: "var(--color-text-primary)",
          fontFamily: mono
            ? "ui-monospace, SFMono-Regular, Menlo, monospace"
            : "inherit",
          textAlign: "right",
          wordBreak: "break-all",
        }}
      >
        {value}
      </span>
    </div>
  );
}

const inputStyle = {
  width: "100%",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid var(--border-subtle)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text-primary)",
  fontSize: "13px",
  outline: "none",
};
