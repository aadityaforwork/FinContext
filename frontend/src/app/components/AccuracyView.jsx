"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../lib/api";
import { AnimatedNumber, Reveal } from "./AnimatedNumber";

/**
 * AccuracyView — the public Track Record surface.
 *
 * Renders aggregate hit-rate stats from the outcome ledger plus a Recent Calls
 * table so visitors can audit individual predictions. No auth, no scope —
 * intentionally social-proof material for landing-page traffic AND a first-
 * class internal tab inside the dashboard.
 *
 * `embedded={true}` skips the page-level title block (used when rendered
 * inside the dashboard frame); `embedded={false}` keeps it (standalone page).
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

export default function AccuracyView({ embedded = false }) {
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

  const hasData      = (accuracy?.scored ?? 0) > 0;
  const pendingCount = accuracy?.pending_at_horizon ?? 0;
  const loggedCount  = accuracy?.predictions_logged ?? 0;
  const ready        = !loading && !error;

  const Wrapper = embedded ? "div" : "main";
  const wrapperStyle = embedded
    ? { width: "100%" }
    : { maxWidth: "1080px", margin: "0 auto", padding: "32px 24px 80px" };

  return (
    <Wrapper style={wrapperStyle}>
      {/* Title block — skip when embedded, the sidebar already labels the view */}
      {!embedded && (
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
      )}

      {embedded && (
        <div style={{ marginBottom: "16px" }}>
          <h2 style={{
            fontSize: "20px", fontWeight: 700, color: "var(--color-text-primary)",
            margin: 0, letterSpacing: "-0.01em",
          }}>
            Track record
          </h2>
          <p style={{
            marginTop: "4px", fontSize: "12.5px", color: "var(--color-text-muted)",
            lineHeight: 1.55, maxWidth: "640px",
          }}>
            Every forward-looking call we make gets logged and graded against the
            actual price move. Numbers below update daily after market close.
          </p>
        </div>
      )}

      {/* Controls */}
      <div style={{
        display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "20px",
        padding: "12px 14px", background: "rgba(255,255,255,0.02)",
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
        <PendingState
          loggedCount={loggedCount}
          pendingCount={pendingCount}
          distinctTickers={accuracy?.distinct_tickers ?? 0}
          earliest={accuracy?.earliest_pending_date}
          latest={accuracy?.latest_pending_date}
          horizon={horizon}
        />
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
    </Wrapper>
  );
}

// ---------------------------------------------------------------------------
// Empty state — shown when no scored calls exist at the chosen horizon.
// Differentiates "ledger empty" from "ledger has predictions, just not scored
// yet" so the page never looks dead while the daily cron hasn't yet caught up.
// ---------------------------------------------------------------------------
function PendingState({ loggedCount, pendingCount, distinctTickers, earliest, latest, horizon }) {
  if (loggedCount === 0) {
    return (
      <Banner color="#64748b">
        <strong style={{ color: "var(--color-text-primary)" }}>No predictions logged yet.</strong>
        {" "}Run the Context Engine on the dashboard to start the ledger — every
        Tomorrow watch item and every News Impact verdict will be recorded here
        and graded against the actual price move.
      </Banner>
    );
  }
  const horizonLabel = horizon === "1d" ? "1 trading day" : horizon === "5d" ? "5 trading days" : "20 trading days";
  return (
    <div style={{
      padding: "20px 22px", borderRadius: "12px",
      background: "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(0,0,0,0.4))",
      border: "1px solid rgba(99,102,241,0.30)",
      marginBottom: "20px",
    }}>
      <div style={{
        display: "flex", alignItems: "baseline", gap: "16px", flexWrap: "wrap",
      }}>
        <AnimatedNumber
          value={pendingCount}
          duration={900}
          format={(v) => Math.round(v).toLocaleString("en-IN")}
          style={{ fontSize: "44px", fontWeight: 800, color: "var(--color-accent-secondary)", lineHeight: 1 }}
        />
        <div>
          <div style={{ fontSize: "13px", color: "var(--color-text-primary)", fontWeight: 700 }}>
            predictions logged, awaiting score
          </div>
          <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px" }}>
            across {distinctTickers} ticker{distinctTickers === 1 ? "" : "s"}
            {earliest && (
              <>
                {" "}· oldest {earliest}{latest && earliest !== latest ? ` → ${latest}` : ""}
              </>
            )}
          </div>
        </div>
      </div>
      <p style={{
        marginTop: "14px", fontSize: "12.5px", color: "var(--color-text-secondary)",
        lineHeight: 1.55, margin: "14px 0 0 0",
      }}>
        First scores at the <strong>{horizonLabel}</strong> horizon arrive after enough
        trading days have elapsed since the prediction. The grading job runs daily
        ~4:30 PM IST after NSE close — predictions made today will start appearing
        here from tomorrow.
      </p>
      {loggedCount > pendingCount && (
        <p style={{
          marginTop: "8px", fontSize: "11px", color: "var(--color-text-muted)",
          fontStyle: "italic",
        }}>
          {loggedCount - pendingCount} of {loggedCount} total predictions in this
          window are scored at other horizons — try the segmented control above.
        </p>
      )}
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
      marginBottom: "20px",
    }}>
      {children}
    </div>
  );
}

function Headline({ accuracy }) {
  const { hit_rate_pct, scored, hits, avg_return_pct, horizon, days } = accuracy;
  const goodCutoff = 60;
  const okCutoff = 50;
  const color = hit_rate_pct >= goodCutoff ? "#10b981"
              : hit_rate_pct >= okCutoff   ? "#f59e0b"
              : "#ef4444";

  return (
    <div style={{
      marginBottom: "20px", padding: "22px 22px", borderRadius: "12px",
      background: `linear-gradient(135deg, ${color}10, rgba(0,0,0,0.4))`,
      border: `1px solid ${color}40`,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "16px", flexWrap: "wrap" }}>
        <AnimatedNumber
          value={hit_rate_pct}
          duration={1100}
          format={(v) => (v == null || Number.isNaN(v)) ? "—" : `${Math.round(v)}%`}
          style={{ fontSize: "52px", fontWeight: 800, color, lineHeight: 1 }}
        />
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
            <AnimatedNumber
              value={avg_return_pct}
              format={(v) => (v == null || Number.isNaN(v)) ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`}
              style={{
                display: "block",
                fontSize: "18px", fontWeight: 800,
                color: avg_return_pct >= 0 ? "#10b981" : "#ef4444",
                marginTop: "2px",
              }}
            />
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
          <Reveal key={`${it.ticker}-${it.prediction_date}-${i}`} index={i} step={28}>
            <RecentRow it={it} />
          </Reveal>
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
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>
        {it.prediction_date}
      </span>
      <span style={{
        color: "var(--color-text-primary)", fontWeight: 700,
        fontFamily: "var(--font-mono)", fontSize: "11px",
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
