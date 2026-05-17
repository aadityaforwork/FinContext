"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { useToast } from "./Toast";
import { API_BASE } from "../lib/api";
import { resetOnboarding } from "./OnboardingModal";

// Bot username so we can deep-link to https://t.me/<bot_username>. Set
// NEXT_PUBLIC_TELEGRAM_BOT_USERNAME in your Vercel/local .env to your bot's
// handle (without the @). Falls back to a placeholder so the UI doesn't break
// in dev when the env var isn't set yet.
const TELEGRAM_BOT_USERNAME =
  process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || "FinContextBot";

/**
 * SettingsView — minimal account + app preferences screen.
 * Replaces the second sidebar nav item. Kept lightweight on purpose;
 * we expand as the product grows (notifications, billing, integrations).
 */
export default function SettingsView() {
  const { user, session, logout, updatePassword } = useAuth();
  const toast = useToast();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // ---- Telegram linking ----
  const [tgStatus, setTgStatus] = useState(null);   // { linked, telegram_username, ... }
  const [tgLoading, setTgLoading] = useState(true);
  const [tgCode, setTgCode] = useState(null);       // { code, expires_at }
  const [tgGenerating, setTgGenerating] = useState(false);

  const tgAuthHeader = useCallback(
    () => (session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
    [session?.access_token]
  );

  const refreshTgStatus = useCallback(async () => {
    if (!session?.access_token) { setTgLoading(false); return; }
    setTgLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/telegram/link-status`, {
        headers: { ...tgAuthHeader() },
      });
      if (r.ok) setTgStatus(await r.json());
    } catch {
      // Silent — Settings shouldn't error-toast on a status fetch.
    } finally {
      setTgLoading(false);
    }
  }, [session?.access_token, tgAuthHeader]);

  useEffect(() => { refreshTgStatus(); }, [refreshTgStatus]);

  const handleGenerateCode = async () => {
    if (!session?.access_token) return;
    setTgGenerating(true);
    try {
      const r = await fetch(`${API_BASE}/api/telegram/link-code`, {
        method: "POST",
        headers: { ...tgAuthHeader(), "Content-Type": "application/json" },
      });
      if (!r.ok) throw new Error(`Code generation failed (${r.status})`);
      setTgCode(await r.json());
    } catch (e) {
      toast.error(e?.message || "Could not generate code.");
    } finally {
      setTgGenerating(false);
    }
  };

  const handleUnlink = async () => {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${API_BASE}/api/telegram/link`, {
        method: "DELETE",
        headers: { ...tgAuthHeader() },
      });
      if (!r.ok) throw new Error(`Unlink failed (${r.status})`);
      toast.success("Telegram disconnected.");
      setTgStatus({ linked: false });
      setTgCode(null);
    } catch (e) {
      toast.error(e?.message || "Could not disconnect.");
    }
  };

  const handleCopyCode = async () => {
    if (!tgCode?.code) return;
    try {
      await navigator.clipboard.writeText(tgCode.code);
      toast.success("Code copied.");
    } catch { /* ignore */ }
  };

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

      {/* TELEGRAM */}
      <Section title="Daily brief on Telegram">
        {tgLoading ? (
          <p style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>Checking link status…</p>
        ) : tgStatus?.linked ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{
              padding: "12px 14px",
              borderRadius: "8px",
              background: "rgba(16,185,129,0.06)",
              border: "1px solid rgba(16,185,129,0.25)",
              display: "flex", alignItems: "center", justifyContent: "space-between",
              gap: "12px", flexWrap: "wrap",
            }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                <span style={{
                  fontSize: "9px", fontWeight: 800, color: "var(--color-accent-green)",
                  textTransform: "uppercase", letterSpacing: "0.10em",
                }}>
                  Connected
                </span>
                <span style={{ fontSize: "13px", color: "var(--color-text-primary)", fontWeight: 600 }}>
                  {tgStatus.telegram_username ? `@${tgStatus.telegram_username}` : "Telegram chat linked"}
                </span>
                <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
                  Daily brief {tgStatus.daily_brief_enabled ? "enabled" : "paused — send /on in chat to resume"}
                </span>
              </div>
              <button
                type="button"
                onClick={handleUnlink}
                style={{
                  padding: "7px 14px", borderRadius: "8px",
                  border: "1px solid rgba(239,68,68,0.30)",
                  background: "rgba(239,68,68,0.06)",
                  color: "var(--color-accent-red)",
                  fontSize: "11.5px", fontWeight: 700, cursor: "pointer",
                }}
              >
                Disconnect
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <p style={{ fontSize: "12.5px", color: "var(--color-text-secondary)", lineHeight: 1.55, margin: 0 }}>
              Get your portfolio brief in Telegram every weekday at 8:30 AM IST —
              P&amp;L, top movers, and policy news hitting your sectors.
              Generate a code, paste it into the bot.
            </p>

            {!tgCode ? (
              <button
                type="button"
                onClick={handleGenerateCode}
                disabled={tgGenerating}
                style={{
                  alignSelf: "flex-start",
                  padding: "8px 16px",
                  borderRadius: "var(--radius-control, 8px)",
                  border: "1px solid var(--color-accent-primary)",
                  background: "var(--color-accent-primary)",
                  color: "#fff",
                  fontSize: "12px", fontWeight: 700, cursor: tgGenerating ? "wait" : "pointer",
                  opacity: tgGenerating ? 0.6 : 1,
                  transition: "filter 0.15s",
                }}
              >
                {tgGenerating ? "Generating…" : "Generate link code"}
              </button>
            ) : (
              <div style={{
                padding: "14px",
                borderRadius: "10px",
                background: "rgba(99,102,241,0.06)",
                border: "1px solid rgba(99,102,241,0.25)",
                display: "flex", flexDirection: "column", gap: "10px",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                  <span style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "22px", fontWeight: 800, color: "var(--color-text-primary)",
                    letterSpacing: "0.12em",
                  }}>
                    {tgCode.code}
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyCode}
                    style={{
                      padding: "5px 10px", borderRadius: "6px",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--color-bg-card)",
                      color: "var(--color-text-secondary)",
                      fontSize: "10.5px", fontWeight: 700, cursor: "pointer",
                    }}
                  >
                    Copy
                  </button>
                  <span style={{ fontSize: "10.5px", color: "var(--color-text-muted)", marginLeft: "auto" }}>
                    Valid for 10 minutes
                  </span>
                </div>
                <ol style={{
                  margin: 0, paddingLeft: "18px", fontSize: "12px",
                  color: "var(--color-text-secondary)", lineHeight: 1.6,
                }}>
                  <li>
                    Open the bot:{" "}
                    <a
                      href={`https://t.me/${TELEGRAM_BOT_USERNAME}`}
                      target="_blank" rel="noopener noreferrer"
                      style={{ color: "var(--color-accent-secondary)", fontWeight: 700 }}
                    >
                      @{TELEGRAM_BOT_USERNAME}
                    </a>
                  </li>
                  <li>
                    Send: <code style={{
                      padding: "1px 6px", borderRadius: "4px",
                      background: "rgba(0,0,0,0.3)", color: "var(--color-accent-cyan)",
                    }}>
                      /link {tgCode.code}
                    </code>
                  </li>
                  <li>
                    Come back here — this section will update once the chat is bound.
                  </li>
                </ol>
                <button
                  type="button"
                  onClick={refreshTgStatus}
                  style={{
                    alignSelf: "flex-start",
                    padding: "6px 12px", borderRadius: "6px",
                    border: "1px solid var(--border-subtle)",
                    background: "var(--color-bg-card)",
                    color: "var(--color-text-secondary)",
                    fontSize: "11px", fontWeight: 600, cursor: "pointer",
                  }}
                >
                  I've sent it — refresh
                </button>
              </div>
            )}
          </div>
        )}
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

      {/* TOUR — replay the dashboard guided tour. Useful if the user
          dismissed it on first run, or just wants to see it again. */}
      <Section title="Guided tour">
        <p style={{ fontSize: "12.5px", color: "var(--color-text-muted)", marginBottom: "12px", lineHeight: 1.55 }}>
          Replay the first-run dashboard tour — highlights Context Engine, News Feed,
          and AI Analysis with their actual data.
        </p>
        <button
          type="button"
          onClick={() => {
            resetOnboarding(user?.id);
            toast.success("Tour will replay on the dashboard.");
            // Send to dashboard with ?tour=1 — page.js consumes the param,
            // bumps trigger, then strips it from the URL.
            setTimeout(() => {
              window.location.href = "/?nav=dashboard&tour=1";
            }, 500);
          }}
          style={{
            padding: "8px 16px",
            borderRadius: "var(--radius-control, 8px)",
            border: "1px solid var(--border-subtle)",
            background: "transparent",
            color: "var(--color-text-secondary)",
            fontSize: "12px",
            fontWeight: 600,
            letterSpacing: "0.02em",
            cursor: "pointer",
            transition: "border-color 0.15s, color 0.15s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--border-strong)";
            e.currentTarget.style.color = "var(--color-text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--border-subtle)";
            e.currentTarget.style.color = "var(--color-text-secondary)";
          }}
        >
          Replay tour →
        </button>
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
            ? "var(--font-mono)"
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
