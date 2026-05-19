"use client";

/**
 * PreTradeCheckModal
 * ------------------
 * "The thing you check before you hit buy on Zerodha."
 *
 * One ticker, one screen, deterministic — no LLM wait. Six grounded checks
 * (RSI, distance from 20-DMA, volume, valuation vs sector, 52w position,
 * primary trend), each rendered as a row with PASS / CAUTION / FAIL plus a
 * one-line `why` so the user learns the framework, not just the verdict.
 *
 * Compliance shape — this is NOT a recommendation:
 *   • Top-line is a count of pass/caution/fail. Never "buy" / "don't buy".
 *   • Each row evaluates ONE factor in isolation. We do not aggregate to a
 *     recommendation.
 *   • Every status carries a `why` so the user can disagree based on facts.
 *
 * Trigger: a search box in the dashboard header (any ticker, anytime), or
 * programmatically from any "check this stock" affordance elsewhere.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { API_BASE } from "../lib/api";
import { Spinner } from "./Loaders";

const SERIF = "var(--font-serif)";
const MONO  = "var(--font-mono)";

const STATUS_META = {
  PASS:    { color: "var(--color-accent-green)", glyph: "✓", label: "PASS" },
  CAUTION: { color: "var(--color-accent-amber)", glyph: "!", label: "CAUTION" },
  FAIL:    { color: "var(--color-accent-red)",   glyph: "✕", label: "FAIL" },
};

export default function PreTradeCheckModal({ ticker, onClose, onOpenDeepDive }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const cardRef = useRef(null);

  const run = useCallback(async (t) => {
    setLoading(true); setError(null); setData(null);
    try {
      const res = await fetch(`${API_BASE}/api/analysis/pre-trade-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: t }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      setData(await res.json());
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (ticker) run(ticker); }, [ticker, run]);

  // Close on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!ticker) return null;

  const isPos = (data?.change_percent ?? 0) >= 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(8,11,18,0.72)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        zIndex: 1100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "20px",
        animation: "ptc-fade-in 0.18s ease-out",
      }}
    >
      <style>{`
        @keyframes ptc-fade-in { from { opacity: 0 } to { opacity: 1 } }
        @keyframes ptc-pop-in {
          from { opacity: 0; transform: translateY(10px) scale(0.98); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
      `}</style>

      <div
        ref={cardRef}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 96vw)",
          maxHeight: "92vh",
          overflowY: "auto",
          background: "var(--color-bg-primary)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
          animation: "ptc-pop-in 0.22s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        {/* HEADER */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 22px",
            borderBottom: "1px solid var(--border-subtle)",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
            <span
              style={{
                fontFamily: MONO,
                fontSize: "9.5px",
                fontWeight: 700,
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--color-text-muted)",
                marginBottom: "3px",
              }}
            >
              Pre-trade check
            </span>
            <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: "20px",
                  fontWeight: 800,
                  color: "var(--color-text-primary)",
                  letterSpacing: "0.01em",
                }}
              >
                {ticker}
              </span>
              {data?.current_price != null && (
                <span style={{ fontFamily: MONO, fontSize: "13px", color: "var(--color-text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                  ₹{Number(data.current_price).toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                </span>
              )}
              {data?.change_percent != null && (
                <span
                  style={{
                    fontFamily: MONO,
                    fontSize: "12.5px",
                    fontWeight: 700,
                    color: isPos ? "var(--color-accent-green)" : "var(--color-accent-red)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {isPos ? "▲ +" : "▼ "}{Math.abs(data.change_percent).toFixed(2)}%
                </span>
              )}
            </div>
            {data?.company && (
              <span style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "2px" }}>
                {data.company}{data.sector ? ` · ${data.sector}` : ""}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close pre-trade check"
            style={{
              width: "30px",
              height: "30px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--border-subtle)",
              background: "var(--color-bg-card)",
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: "18px",
              lineHeight: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ×
          </button>
        </div>

        {/* BODY */}
        {loading && <LoadingState />}
        {error && !loading && (
          <ErrorState message={error} onRetry={() => run(ticker)} />
        )}
        {data && !loading && !error && (
          <>
            <SummaryStrip summary={data.summary} />

            <ul style={{ listStyle: "none", padding: "0 22px 4px", margin: 0 }}>
              {data.checks.length === 0 && (
                <li style={{ padding: "24px 0", textAlign: "center", color: "var(--color-text-muted)", fontStyle: "italic", fontSize: "13px" }}>
                  Not enough data to run checks on this ticker right now.
                </li>
              )}
              {data.checks.map((c) => (
                <CheckRow key={c.id} check={c} />
              ))}
            </ul>

            <Disclaimer note={data.disclaimer_short} />

            {/* CTA — open the full LLM brief */}
            <div
              style={{
                padding: "14px 22px 20px",
                borderTop: "1px solid var(--border-subtle)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "12px",
                flexWrap: "wrap",
              }}
            >
              <span
                style={{
                  fontSize: "11.5px",
                  color: "var(--color-text-muted)",
                  fontFamily: SERIF,
                  fontStyle: "italic",
                  letterSpacing: "-0.003em",
                  flex: 1,
                  minWidth: "200px",
                }}
              >
                These are isolated checks — they don&rsquo;t add up to a verdict.
              </span>
              <button
                type="button"
                onClick={() => { onOpenDeepDive?.(ticker); onClose?.(); }}
                style={{
                  padding: "8px 14px",
                  borderRadius: "var(--radius-control)",
                  border: "1px solid var(--color-accent-primary)",
                  background: "var(--color-accent-primary)",
                  color: "#fff",
                  fontSize: "11px",
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  fontFamily: MONO,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                Open full deep dive →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary strip — pass/caution/fail counts. Pure count, never a verdict.
// ---------------------------------------------------------------------------
function SummaryStrip({ summary }) {
  if (!summary || summary.total === 0) return null;
  const { passes, cautions, fails, total } = summary;
  return (
    <div
      style={{
        padding: "16px 22px",
        borderBottom: "1px solid var(--border-subtle)",
        display: "flex",
        alignItems: "center",
        gap: "20px",
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
        <span
          style={{
            fontFamily: MONO,
            fontSize: "9.5px",
            fontWeight: 700,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--color-text-muted)",
            marginBottom: "3px",
          }}
        >
          Result
        </span>
        <span
          style={{
            fontFamily: MONO,
            fontSize: "15px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "0.02em",
          }}
        >
          {passes} pass · {cautions} caution · {fails} fail
        </span>
      </div>

      {/* Tiny segmented bar — proportional. */}
      <div
        aria-hidden
        style={{
          flex: 1,
          minWidth: "120px",
          height: "4px",
          display: "flex",
          borderRadius: "2px",
          overflow: "hidden",
          opacity: 0.7,
        }}
      >
        {passes > 0 && (
          <div style={{ width: `${(passes / total) * 100}%`, background: "var(--color-accent-green)" }} />
        )}
        {cautions > 0 && (
          <div style={{ width: `${(cautions / total) * 100}%`, background: "var(--color-accent-amber)" }} />
        )}
        {fails > 0 && (
          <div style={{ width: `${(fails / total) * 100}%`, background: "var(--color-accent-red)" }} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Check row — label + value + status pill + 1-line why
// ---------------------------------------------------------------------------
function CheckRow({ check }) {
  const meta = STATUS_META[check.status] || STATUS_META.CAUTION;
  return (
    <li
      style={{
        display: "grid",
        gridTemplateColumns: "24px 1fr auto",
        gap: "12px",
        alignItems: "flex-start",
        padding: "14px 0",
        borderBottom: "1px dashed var(--border-subtle)",
      }}
    >
      <span
        aria-hidden
        title={meta.label}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: "20px",
          height: "20px",
          borderRadius: "50%",
          background: `color-mix(in srgb, ${meta.color} 14%, transparent)`,
          color: meta.color,
          fontFamily: MONO,
          fontSize: "11px",
          fontWeight: 800,
          marginTop: "2px",
        }}
      >
        {meta.glyph}
      </span>

      <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px", flexWrap: "wrap" }}>
          <span style={{ fontSize: "13.5px", fontWeight: 700, color: "var(--color-text-primary)", letterSpacing: "-0.005em" }}>
            {check.label}
          </span>
          <span style={{ fontFamily: MONO, fontSize: "11px", fontWeight: 700, color: "var(--color-text-muted)", letterSpacing: "0.04em" }}>
            {check.value}
          </span>
        </div>
        <p style={{ fontSize: "12.5px", lineHeight: 1.55, color: "var(--color-text-secondary)", margin: 0 }}>
          {check.why}
        </p>
      </div>

      <span
        style={{
          fontFamily: MONO,
          fontSize: "9.5px",
          fontWeight: 700,
          letterSpacing: "0.14em",
          color: meta.color,
          border: `1px solid color-mix(in srgb, ${meta.color} 32%, transparent)`,
          background: `color-mix(in srgb, ${meta.color} 10%, transparent)`,
          padding: "3px 8px",
          borderRadius: "4px",
          whiteSpace: "nowrap",
          marginTop: "2px",
        }}
      >
        {meta.label}
      </span>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Loading + Error + Disclaimer atoms
// ---------------------------------------------------------------------------
function LoadingState() {
  return (
    <div
      style={{
        padding: "60px 22px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "14px",
      }}
    >
      <Spinner size="sm" />
      <span
        style={{
          fontFamily: MONO,
          fontSize: "11px",
          fontWeight: 700,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--color-text-muted)",
        }}
      >
        Running checks…
      </span>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div style={{ padding: "32px 22px", textAlign: "center" }}>
      <div
        style={{
          fontFamily: MONO,
          fontSize: "10.5px",
          fontWeight: 700,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--color-accent-red)",
          marginBottom: "8px",
        }}
      >
        Check failed
      </div>
      <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "16px", lineHeight: 1.5 }}>
        {message}
      </p>
      <button
        type="button"
        onClick={onRetry}
        style={{
          padding: "7px 14px",
          borderRadius: "var(--radius-control)",
          border: "1px solid var(--color-accent-red)",
          background: "transparent",
          color: "var(--color-accent-red)",
          fontSize: "11px",
          fontWeight: 700,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontFamily: MONO,
          cursor: "pointer",
        }}
      >
        Retry
      </button>
    </div>
  );
}

function Disclaimer({ note }) {
  if (!note) return null;
  return (
    <p
      style={{
        fontSize: "10.5px",
        color: "var(--color-text-muted)",
        margin: "12px 22px 4px",
        fontStyle: "italic",
        lineHeight: 1.5,
        fontFamily: SERIF,
      }}
    >
      {note}
    </p>
  );
}
