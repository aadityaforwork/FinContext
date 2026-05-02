"use client";

import { useState, useRef, useEffect } from "react";
import { API_BASE as _SHARED_API_BASE } from "../lib/api";
import { claimText, claimSource } from "../lib/claim";

const API_BASE = _SHARED_API_BASE;

const DIRECTION_COLORS = {
  positive: "#10b981",
  negative: "#ef4444",
  mixed:    "#f59e0b",
  neutral:  "#64748b",
};

const DRIVER_LABELS = {
  stock_specific: "Company news",
  sector:         "Sector move",
  macro:          "Macro / news",
  unexplained:    "Unexplained",
};

const DRIVER_COLORS = {
  stock_specific: "#6366f1",
  sector:         "#06b6d4",
  macro:          "#f59e0b",
  unexplained:    "#64748b",
};

export default function PortfolioContextCard({ positions }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState([]);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("today");
  const terminalRef = useRef(null);

  useEffect(() => {
    if (terminalRef.current) terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [steps]);

  const run = async () => {
    if (!positions?.length) return;
    setLoading(true);
    setData(null);
    setSteps([]);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/intelligence/movers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ positions }),
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      while (!done) {
        const { value, done: rd } = await reader.read();
        if (value) {
          const chunk = decoder.decode(value);
          for (const line of chunk.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const s = line.slice(6).trim();
            if (s === "[DONE]") { setLoading(false); break; }
            if (!s) continue;
            try {
              const msg = JSON.parse(s);
              if (msg.type === "step") setSteps(prev => [...prev, msg.message]);
              else if (msg.type === "error") { setError(msg.message); setLoading(false); }
              else if (msg.type === "result") { setData(msg); setLoading(false); }
            } catch {}
          }
        }
        done = rd;
      }
    } catch (e) {
      setError(String(e));
      setLoading(false);
    }
  };

  const portReturn = data?.portfolio_return_today_pct;
  const portReturnColor = portReturn == null ? "var(--color-text-muted)"
    : portReturn >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)";

  return (
    <div className="glass-card animate-fade-in" style={{ padding: "24px", marginBottom: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", flexWrap: "wrap" }}>
        <div>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "20px" }}>🧭</span> Context Engine
          </h3>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px", maxWidth: "580px" }}>
            Why did your portfolio move today — and what global news might move it tomorrow. Every claim cites a real source.
          </p>
        </div>
        {!data && !loading && (
          <button
            onClick={run}
            disabled={!positions?.length}
            style={{
              padding: "10px 18px", borderRadius: "10px", fontSize: "13px", fontWeight: 600,
              background: positions?.length ? "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))" : "var(--color-bg-tertiary)",
              color: positions?.length ? "white" : "var(--color-text-muted)",
              border: "none", cursor: positions?.length ? "pointer" : "not-allowed",
            }}
          >
            Run Context Engine
          </button>
        )}
        {data && (
          <button
            onClick={run}
            style={{
              padding: "6px 12px", borderRadius: "8px", fontSize: "12px",
              border: "1px solid var(--border-subtle)", background: "transparent",
              color: "var(--color-text-muted)", cursor: "pointer",
            }}
          >
            ↻ Refresh
          </button>
        )}
      </div>

      {error && (
        <div style={{ marginTop: "14px", color: "var(--color-accent-red)", fontSize: "13px", padding: "10px", background: "rgba(239,68,68,0.08)", borderRadius: "8px" }}>
          {error}
        </div>
      )}

      {loading && (
        <div style={{
          marginTop: "16px", background: "#0c0a13", border: "1px solid #2a2542", borderRadius: "12px",
          padding: "14px", fontFamily: "'JetBrains Mono', monospace", fontSize: "12px", color: "#a599e9",
        }}>
          <div ref={terminalRef} style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "160px", overflowY: "auto" }}>
            {steps.map((s, i) => (
              <div key={i}><span style={{ color: "#34d399", marginRight: "8px" }}>&gt;</span>{s}</div>
            ))}
            <div style={{ color: "var(--color-text-muted)" }}>
              <span style={{ color: "#34d399", marginRight: "8px" }}>&gt;</span> _
            </div>
          </div>
        </div>
      )}

      {data && (
        <div style={{ marginTop: "18px" }}>
          {/* Top strip: portfolio return + NIFTY */}
          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginBottom: "18px" }}>
            <div style={{ flex: "1 1 160px", padding: "14px 16px", background: "rgba(0,0,0,0.2)", borderRadius: "10px" }}>
              <div style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>Your portfolio today</div>
              <div style={{ fontSize: "26px", fontWeight: 800, color: portReturnColor, marginTop: "4px", fontVariantNumeric: "tabular-nums" }}>
                {portReturn == null ? "—" : `${portReturn > 0 ? "+" : ""}${portReturn}%`}
              </div>
            </div>
            {data.market_indices && Object.entries(data.market_indices).filter(([, v]) => v).map(([k, v]) => (
              <div key={k} style={{ flex: "1 1 140px", padding: "14px 16px", background: "rgba(0,0,0,0.2)", borderRadius: "10px" }}>
                <div style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
                  {k.replace(/_/g, " ")}
                </div>
                <div style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                  {v.value?.toLocaleString("en-IN")}
                </div>
                <div style={{ fontSize: "12px", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: v.change_percent >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)" }}>
                  {v.change_percent >= 0 ? "+" : ""}{v.change_percent}%
                </div>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid var(--border-subtle)", marginBottom: "16px" }}>
            <TabButton active={tab === "today"} onClick={() => setTab("today")}>
              Today — Why did we move?
            </TabButton>
            <TabButton active={tab === "tomorrow"} onClick={() => setTab("tomorrow")}>
              Tomorrow — What to watch
            </TabButton>
          </div>

          {tab === "today" && <TodaySection today={data.today} />}
          {tab === "tomorrow" && <TomorrowSection tomorrow={data.tomorrow} />}
        </div>
      )}
    </div>
  );
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "10px 14px", background: "transparent", border: "none", cursor: "pointer",
        fontSize: "13px", fontWeight: 600,
        color: active ? "var(--color-text-primary)" : "var(--color-text-muted)",
        borderBottom: active ? "2px solid var(--color-accent-primary)" : "2px solid transparent",
        marginBottom: "-1px",
      }}
    >
      {children}
    </button>
  );
}

function TodaySection({ today }) {
  if (!today) return null;
  const { movers = [], top_positive_driver, top_negative_driver, confidence, data_gaps = [] } = today;

  return (
    <div>
      {(top_positive_driver || top_negative_driver) && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px", marginBottom: "16px" }}>
          {top_positive_driver && (
            <DriverHeadline label="Top positive driver" color="var(--color-accent-green)" claim={top_positive_driver} />
          )}
          {top_negative_driver && (
            <DriverHeadline label="Top negative driver" color="var(--color-accent-red)" claim={top_negative_driver} />
          )}
        </div>
      )}

      {movers.length === 0 ? (
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", padding: "16px", textAlign: "center", background: "rgba(0,0,0,0.15)", borderRadius: "10px" }}>
          No notable movers today (all holdings within ±1.5%).
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {movers.map((m, i) => <MoverRow key={i} mover={m} />)}
        </div>
      )}

      <FooterMeta confidence={confidence} data_gaps={data_gaps} />
    </div>
  );
}

function MoverRow({ mover }) {
  const pos = (mover.move_percent ?? 0) >= 0;
  return (
    <div style={{
      padding: "14px 16px", background: "rgba(255,255,255,0.02)",
      border: "1px solid var(--border-subtle)", borderRadius: "10px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "10px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>{mover.ticker}</span>
        <span style={{
          fontSize: "15px", fontWeight: 800, fontVariantNumeric: "tabular-nums",
          color: pos ? "var(--color-accent-green)" : "var(--color-accent-red)",
        }}>
          {pos ? "▲ +" : "▼ "}{mover.move_percent}%
        </span>
        <span style={{
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${DRIVER_COLORS[mover.primary_driver] || "#64748b"}20`,
          color: DRIVER_COLORS[mover.primary_driver] || "#64748b",
          textTransform: "uppercase", letterSpacing: "0.5px",
        }}>
          {DRIVER_LABELS[mover.primary_driver] || mover.primary_driver}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {(mover.attribution || []).map((a, i) => (
          <div key={i} title={claimSource(a) || ""} style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5, display: "flex", gap: "10px", alignItems: "baseline" }}>
            {a.weight_pct != null && (
              <span style={{
                fontSize: "10px", fontWeight: 700, padding: "2px 6px", borderRadius: "4px",
                background: "rgba(99,102,241,0.12)", color: "var(--color-accent-secondary)",
                flexShrink: 0, minWidth: "38px", textAlign: "center",
              }}>
                {a.weight_pct}%
              </span>
            )}
            <span>{claimText(a)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TomorrowSection({ tomorrow }) {
  if (!tomorrow) return null;
  const { themes = [], overall_bias, confidence, data_gaps = [] } = tomorrow;
  const biasColor = DIRECTION_COLORS[overall_bias] || "#64748b";

  return (
    <div>
      {overall_bias && (
        <div style={{
          padding: "10px 14px", marginBottom: "14px", borderRadius: "10px",
          background: `${biasColor}14`, borderLeft: `3px solid ${biasColor}`,
          display: "flex", alignItems: "center", gap: "10px",
        }}>
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>Overnight bias for tomorrow</span>
          <span style={{ fontSize: "13px", fontWeight: 700, color: biasColor, textTransform: "uppercase" }}>{overall_bias}</span>
        </div>
      )}

      {themes.length === 0 ? (
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", padding: "16px", textAlign: "center", background: "rgba(0,0,0,0.15)", borderRadius: "10px" }}>
          No strong overnight signals tied to your holdings.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {themes.map((t, i) => <ThemeRow key={i} theme={t} />)}
        </div>
      )}

      <FooterMeta confidence={confidence} data_gaps={data_gaps} />
    </div>
  );
}

function ThemeRow({ theme }) {
  const color = DIRECTION_COLORS[theme.direction] || "#64748b";
  const importance = theme.importance || "medium";
  return (
    <div style={{
      padding: "14px 16px", background: "rgba(255,255,255,0.02)",
      border: "1px solid var(--border-subtle)", borderRadius: "10px", borderLeft: `3px solid ${color}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>{theme.theme}</span>
        <span style={{
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${color}20`, color, textTransform: "uppercase", letterSpacing: "0.5px",
        }}>
          {theme.direction}
        </span>
        {importance === "high" && (
          <span style={{
            padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
            background: "rgba(245,158,11,0.15)", color: "#f59e0b", textTransform: "uppercase", letterSpacing: "0.5px",
          }}>
            ★ High importance
          </span>
        )}
      </div>
      {theme.mechanism && (
        <p title={claimSource(theme.mechanism) || ""} style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5, marginBottom: "8px" }}>
          {claimText(theme.mechanism)}
        </p>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
        {(theme.affected_holdings || []).map((t, i) => (
          <span key={`h-${i}`} style={{
            padding: "3px 8px", borderRadius: "6px", fontSize: "11px", fontWeight: 600,
            background: "rgba(99,102,241,0.12)", color: "var(--color-accent-secondary)",
          }}>
            {t}
          </span>
        ))}
        {(theme.affected_sectors || []).map((s, i) => (
          <span key={`s-${i}`} style={{
            padding: "3px 8px", borderRadius: "6px", fontSize: "11px", fontWeight: 600,
            background: "rgba(6,182,212,0.12)", color: "var(--color-accent-cyan)",
          }}>
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

function DriverHeadline({ label, color, claim }) {
  return (
    <div title={claimSource(claim) || ""} style={{ padding: "10px 14px", borderRadius: "10px", background: `${color}0d`, borderLeft: `3px solid ${color}` }}>
      <div style={{ fontSize: "10px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "4px" }}>{label}</div>
      <div style={{ fontSize: "13px", color: "var(--color-text-primary)", lineHeight: 1.5 }}>{claimText(claim)}</div>
    </div>
  );
}

function FooterMeta({ confidence, data_gaps }) {
  if (!confidence && (!data_gaps || data_gaps.length === 0)) return null;
  return (
    <div style={{ marginTop: "14px", padding: "10px 12px", background: "rgba(0,0,0,0.15)", borderRadius: "8px", display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "center" }}>
      {confidence && (
        <span style={{ fontSize: "11px", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
          Confidence: <span style={{ color: confidence === "high" ? "var(--color-accent-green)" : confidence === "medium" ? "#f59e0b" : "var(--color-accent-red)" }}>{confidence}</span>
        </span>
      )}
      {data_gaps?.length > 0 && (
        <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
          Gaps: {data_gaps.slice(0, 2).join(" · ")}
        </span>
      )}
    </div>
  );
}
