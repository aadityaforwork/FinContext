"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { API_BASE } from "../lib/api";

/**
 * /accuracy — public Track Record page.
 *
 * Renders aggregate hit-rate stats from the outcome ledger plus a Recent Calls
 * table so visitors can audit individual predictions. No auth, no scope —
 * this is intentionally social proof for landing-page traffic.
 */

const HORIZONS = [
  { id: "1d",  label: "Next day"  },
  { id: "5d",  label: "5 days"    },
  { id: "20d", label: "20 days"   },
];

const SOURCE_LABEL = {
  tomorrow_per_holding: "Tomorrow's watch list",
  news_feed:            "News Impact Feed",
};

const IMPACT_COLOR = {
  high:   "#ef4444",
  medium: "#f59e0b",
  low:    "#94a3b8",
};

const DIRECTION_COLOR = {
  positive: "#10b981",
  negative: "#ef4444",
  neutral:  "#64748b",
};

export default function AccuracyPage() {
  const [horizon, setHorizon] = useState("5d");
  const [days, setDays] = useState(30);
  const [accuracy, setAccuracy] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true); setError(null);
      try {
        const [accRes, recRes] = await Promise.all([
          fetch(`${API_BASE}/api/outcomes/accuracy?horizon=${horizon}&days=${days}`),
          fetch(`${API_BASE}/api/outcomes/recent?horizon=${horizon}&limit=30`),
        ]);
        if (!accRes.ok) throw new Error(`accuracy ${accRes.status}`);
        if (!recRes.ok) throw new Error(`recent ${recRes.status}`);
        if (cancelled) return;
        const accData = await accRes.json();
        const recData = await recRes.json();
        setAccuracy(accData);
        setRecent(recData?.items || []);
      } catch (e) {
        if (!cancelled) setError(e?.message || "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [horizon, days]);

  const hasData = (accuracy?.scored ?? 0) > 0;
  const ready   = !loading && !error;

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--color-bg-primary, #0a0b14)",
      color: "var(--color-text-primary)",
    }}>
      {/* Top nav strip */}
      <header style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "18px 28px", borderBottom: "1px solid var(--border-subtle)",
      }}>
        <Link href="/" style={{
          fontSize: "13px", fontWeight: 800, color: "var(--color-text-primary)",
          textDecoration: "none", letterSpacing: "-0.01em",
        }}>
          ← FinContext
        </Link>
        <div style={{
          fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
          textTransform: "uppercase", letterSpacing: "0.08em",
        }}>
          Track record · Public
        </div>
      </header>

      <main style={{ maxWidth: "1080px", margin: "0 auto", padding: "32px 24px 80px" }}>
        {/* Title block */}
        <div style={{ marginBottom: "28px" }}>
          <h1 style={{
            fontSize: "28px", fontWeight: 800, color: "var(--color-text-primary)",
            margin: 0, letterSpacing: "-0.02em",
          }}>
            Does it actually work?
          </h1>
          <p style={{
            marginTop: "8px", fontSize: "14px", color: "var(--color-text-muted)",
            lineHeight: 1.6, maxWidth: "640px",
          }}>
            Every forward-looking call we make — Tomorrow's watch items, News
            Impact directional verdicts — gets logged and graded against the
            actual price move. Numbers below update daily after market close.
          </p>
        </div>

        {/* Controls */}
        <div style={{
          display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "24px",
          padding: "14px", background: "rgba(255,255,255,0.02)",
          border: "1px solid var(--border-subtle)", borderRadius: "10px",
        }}>
          <ControlGroup label="Horizon">
            <Segmented options={HORIZONS} value={horizon} onChange={setHorizon} />
          </ControlGroup>
          <ControlGroup label="Window">
            <Segmented
              options={[
                { id: 7,   label: "7d"  },
                { id: 30,  label: "30d" },
                { id: 90,  label: "90d" },
              ]}
              value={days}
              onChange={setDays}
            />
          </ControlGroup>
          <p style={{
            marginLeft: "auto", alignSelf: "center",
            fontSize: "11px", color: "var(--color-text-muted)", fontStyle: "italic",
          }}>
            Updated after each NSE close (~4:30 PM IST).
          </p>
        </div>

        {/* Body */}
        {loading && <p style={{ color: "var(--color-text-muted)", fontSize: "13px" }}>Loading…</p>}
        {error && <Banner color="#ef4444">Error loading track record: {error}</Banner>}

        {ready && !hasData && (
          <Banner color="#64748b">
            No graded calls yet for this horizon. Outcome computation runs daily
            after market close; predictions made in the last {horizon === "20d" ? 20 : horizon === "5d" ? 5 : 1}+ trading day(s) will appear here as scores roll in.
          </Banner>
        )}

        {ready && hasData && (
          <>
            <Headline accuracy={accuracy} />
            <BreakdownGrid accuracy={accuracy} />
            <RecentCalls items={recent} />
          </>
        )}

        <p style={{
          marginTop: "32px", fontSize: "11px", color: "var(--color-text-muted)",
          fontStyle: "italic", textAlign: "center",
        }}>
          Educational only — not investment advice. Not a SEBI-registered RA.
        </p>
      </main>
    </div>
  );
}

function ControlGroup({ label, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <span style={{
        fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
        textTransform: "uppercase", letterSpacing: "1px",
      }}>{label}</span>
      {children}
    </div>
  );
}

function Segmented({ options, value, onChange }) {
  return (
    <div style={{
      display: "flex", border: "1px solid var(--border-subtle)",
      borderRadius: "6px", overflow: "hidden",
    }}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          style={{
            padding: "6px 12px", fontSize: "11px", fontWeight: 700,
            border: "none", cursor: "pointer",
            background: value === o.id ? "rgba(99,102,241,0.15)" : "transparent",
            color: value === o.id ? "var(--color-accent-secondary)" : "var(--color-text-muted)",
          }}
        >{o.label}</button>
      ))}
    </div>
  );
}

function Banner({ color, children }) {
  return (
    <div style={{
      padding: "12px 14px", borderRadius: "8px",
      background: `${color}14`, borderLeft: `3px solid ${color}`,
      color: "var(--color-text-secondary)", fontSize: "13px", lineHeight: 1.5,
    }}>
      {children}
    </div>
  );
}

function Headline({ accuracy }) {
  const { hit_rate_pct, scored, hits, avg_return_pct, horizon, days } = accuracy;
  const goodCutoff = 60; // arbitrary marketing threshold — green if ≥60%
  const okCutoff = 50;
  const color = hit_rate_pct >= goodCutoff ? "#10b981"
              : hit_rate_pct >= okCutoff   ? "#f59e0b"
              : "#ef4444";

  return (
    <div style={{
      marginBottom: "24px", padding: "26px 24px", borderRadius: "14px",
      background: `linear-gradient(135deg, ${color}10, rgba(0,0,0,0.4))`,
      border: `1px solid ${color}40`,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "16px", flexWrap: "wrap" }}>
        <div style={{ fontSize: "56px", fontWeight: 800, color, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
          {hit_rate_pct != null ? `${hit_rate_pct}%` : "—"}
        </div>
        <div>
          <div style={{ fontSize: "13px", color: "var(--color-text-primary)", fontWeight: 700 }}>
            hit rate on {horizon} horizon
          </div>
          <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px" }}>
            {hits} of {scored} scored calls · last {days} days
          </div>
        </div>
        {avg_return_pct != null && (
          <div style={{
            marginLeft: "auto", padding: "8px 14px", borderRadius: "8px",
            background: "rgba(0,0,0,0.25)",
          }}>
            <div style={{ fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
              Avg actual move
            </div>
            <div style={{
              fontSize: "18px", fontWeight: 800,
              color: avg_return_pct >= 0 ? "#10b981" : "#ef4444",
              fontVariantNumeric: "tabular-nums", marginTop: "2px",
            }}>
              {avg_return_pct >= 0 ? "+" : ""}{avg_return_pct}%
            </div>
          </div>
        )}
      </div>
      <p style={{
        marginTop: "14px", fontSize: "11px", color: "var(--color-text-muted)",
        fontStyle: "italic", lineHeight: 1.5,
      }}>
        A "hit" means the predicted direction matched AND the actual move was ≥ 0.5%.
        Neutral calls hit if the move stayed under 0.5%. "Mixed" calls aren't scored.
      </p>
    </div>
  );
}

function BreakdownGrid({ accuracy }) {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
      gap: "12px", marginBottom: "24px",
    }}>
      <BreakdownCard
        title="By impact level"
        rows={accuracy.by_impact}
        labels={["high", "medium", "low"]}
        colorOf={(k) => IMPACT_COLOR[k] || "#64748b"}
      />
      <BreakdownCard
        title="By prediction source"
        rows={accuracy.by_source}
        labels={["tomorrow_per_holding", "news_feed"]}
        labelMap={SOURCE_LABEL}
        colorOf={() => "#a855f7"}
      />
      <BreakdownCard
        title="By direction"
        rows={accuracy.by_direction}
        labels={["positive", "negative", "neutral"]}
        colorOf={(k) => DIRECTION_COLOR[k] || "#64748b"}
      />
      <BreakdownCard
        title="By catalyst type"
        rows={accuracy.by_catalyst}
        colorOf={() => "#06b6d4"}
      />
    </div>
  );
}

function BreakdownCard({ title, rows, labels, labelMap, colorOf }) {
  const keys = labels && labels.length
    ? labels.filter((k) => (rows || {})[k])
    : Object.keys(rows || {}).filter((k) => k && k !== "unknown");

  return (
    <div style={{
      padding: "14px 16px", background: "rgba(255,255,255,0.02)",
      border: "1px solid var(--border-subtle)", borderRadius: "10px",
    }}>
      <div style={{
        fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
        textTransform: "uppercase", letterSpacing: "1.2px", marginBottom: "10px",
      }}>{title}</div>
      {keys.length === 0 ? (
        <p style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>No data.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {keys.map((k) => {
            const r = rows[k] || {};
            const pct = r.hit_rate_pct;
            const color = colorOf(k);
            return (
              <div key={k}>
                <div style={{
                  display: "flex", justifyContent: "space-between", alignItems: "baseline",
                  marginBottom: "3px", fontSize: "12px",
                }}>
                  <span style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
                    {(labelMap && labelMap[k]) || k.replace(/_/g, " ")}
                  </span>
                  <span style={{
                    fontVariantNumeric: "tabular-nums",
                    color: pct == null ? "var(--color-text-muted)" : color,
                    fontWeight: 700,
                  }}>
                    {pct != null ? `${pct}%` : "—"}
                    <span style={{ color: "var(--color-text-muted)", fontWeight: 500, marginLeft: "6px", fontSize: "10px" }}>
                      ({r.scored || 0})
                    </span>
                  </span>
                </div>
                <div style={{ height: "4px", background: "rgba(255,255,255,0.05)", borderRadius: "2px", overflow: "hidden" }}>
                  <div style={{
                    width: `${pct ?? 0}%`, height: "100%",
                    background: color, borderRadius: "2px",
                    transition: "width 0.3s",
                  }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function RecentCalls({ items }) {
  if (!items?.length) return null;
  return (
    <div style={{ marginTop: "8px" }}>
      <h2 style={{
        fontSize: "12px", fontWeight: 700, color: "var(--color-text-muted)",
        textTransform: "uppercase", letterSpacing: "1.2px", marginBottom: "10px",
      }}>
        Recent scored calls ({items.length})
      </h2>
      <div style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border-subtle)", borderRadius: "10px",
        overflow: "hidden",
      }}>
        <div style={{
          display: "grid",
          gridTemplateColumns: "100px 80px 1fr 80px 90px 60px",
          gap: "12px", padding: "10px 14px",
          fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
          textTransform: "uppercase", letterSpacing: "0.6px",
          borderBottom: "1px solid var(--border-subtle)",
        }}>
          <span>Date</span>
          <span>Ticker</span>
          <span>Reason</span>
          <span>Direction</span>
          <span style={{ textAlign: "right" }}>Move</span>
          <span style={{ textAlign: "center" }}>Hit?</span>
        </div>
        {items.map((it, i) => (
          <RecentRow key={`${it.ticker}-${it.prediction_date}-${i}`} it={it} />
        ))}
      </div>
    </div>
  );
}

function RecentRow({ it }) {
  const dirColor = DIRECTION_COLOR[it.direction] || "#64748b";
  const moveColor = (it.return_pct ?? 0) >= 0 ? "#10b981" : "#ef4444";
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "100px 80px 1fr 80px 90px 60px",
      gap: "12px", padding: "10px 14px",
      fontSize: "12px", color: "var(--color-text-secondary)",
      borderBottom: "1px solid var(--border-subtle)",
      alignItems: "center",
    }}>
      <span style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "11px" }}>
        {it.prediction_date}
      </span>
      <span style={{
        color: "var(--color-text-primary)", fontWeight: 700,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "11px",
      }}>
        {it.ticker}
      </span>
      <span style={{
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
      }} title={it.reason || ""}>
        {it.reason || <em style={{ color: "var(--color-text-muted)" }}>(no reason logged)</em>}
      </span>
      <span style={{
        color: dirColor, fontWeight: 700, fontSize: "10px",
        textTransform: "uppercase", letterSpacing: "0.5px",
      }}>
        {it.direction}
      </span>
      <span style={{
        textAlign: "right",
        color: moveColor, fontWeight: 700, fontVariantNumeric: "tabular-nums",
      }}>
        {it.return_pct != null ? `${it.return_pct >= 0 ? "+" : ""}${it.return_pct}%` : "—"}
      </span>
      <span style={{ textAlign: "center", fontSize: "14px" }}>
        {it.hit === true  ? <span title="Hit"  style={{ color: "#10b981" }}>✓</span>
       : it.hit === false ? <span title="Miss" style={{ color: "#ef4444" }}>✗</span>
       : <span style={{ color: "var(--color-text-muted)" }}>—</span>}
      </span>
    </div>
  );
}
