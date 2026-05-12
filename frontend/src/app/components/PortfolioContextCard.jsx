"use client";

import { useState, useRef, useEffect } from "react";
import { API_BASE as _SHARED_API_BASE } from "../lib/api";
import { claimText, claimSource } from "../lib/claim";
import Modal from "./Modal";
import { Hint, TECH_TOOLTIPS } from "./Tooltips";

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
  flow:           "FII/DII flow",
  technical:      "Technical",
  unexplained:    "Unexplained",
};

const DRIVER_COLORS = {
  stock_specific: "#6366f1",
  sector:         "#06b6d4",
  macro:          "#f59e0b",
  flow:           "#ec4899",
  technical:      "#a855f7",
  unexplained:    "#64748b",
};

const CATALYST_LABELS = {
  earnings:    "Earnings",
  news:        "News catalyst",
  technical:   "Chart setup",
  sector_flow: "Sector flow",
  mixed:       "Mixed",
};

const CATALYST_COLORS = {
  earnings:    "#10b981",
  news:        "#6366f1",
  technical:   "#a855f7",
  sector_flow: "#06b6d4",
  mixed:       "#f59e0b",
};

const RSI_COLORS = {
  oversold:   "#10b981",
  weak:       "#84cc16",
  neutral:    "#64748b",
  strong:     "#f59e0b",
  overbought: "#ef4444",
};

const VOL_COLORS = {
  low:    "#64748b",
  normal: "#64748b",
  high:   "#f59e0b",
  surge:  "#ef4444",
};


export default function PortfolioContextCard({ positions }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState([]);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("today");
  const [detailTicker, setDetailTicker] = useState(null);     // Today MoverRow modal
  const [watchDetail, setWatchDetail] = useState(null);       // Tomorrow watch item modal
  const [themeDetail, setThemeDetail] = useState(null);       // Tomorrow theme modal
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

          {data.market_flows && (data.market_flows.fii_net_cr != null || data.market_flows.dii_net_cr != null) && (
            <FlowsStrip flows={data.market_flows} />
          )}

          {/* Tabs */}
          <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid var(--border-subtle)", marginBottom: "16px" }}>
            <TabButton active={tab === "today"} onClick={() => setTab("today")}>
              Today — Why did we move?
            </TabButton>
            <TabButton active={tab === "tomorrow"} onClick={() => setTab("tomorrow")}>
              Tomorrow — What to watch
            </TabButton>
          </div>

          {tab === "today" && (
            <TodaySection today={data.today} onMoverClick={(t) => setDetailTicker(t)} />
          )}
          {tab === "tomorrow" && (
            <TomorrowSection
              tomorrow={data.tomorrow}
              onWatchClick={(w) => setWatchDetail(w)}
              onThemeClick={(t) => setThemeDetail(t)}
            />
          )}
        </div>
      )}

      {detailTicker && (
        <MoverDetailModal
          ticker={detailTicker}
          mover={(data?.today?.movers || []).find((m) => m.ticker === detailTicker)}
          detail={data?.holdings_detail?.[detailTicker]}
          onClose={() => setDetailTicker(null)}
        />
      )}

      {watchDetail && (
        <WatchItemDetailModal
          watch={watchDetail}
          detail={data?.holdings_detail?.[watchDetail.ticker]}
          onClose={() => setWatchDetail(null)}
        />
      )}

      {themeDetail && (
        <ThemeDetailModal
          theme={themeDetail}
          holdingsDetail={data?.holdings_detail || {}}
          sectorReturns={data?.sector_returns || []}
          onClose={() => setThemeDetail(null)}
        />
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

function TodaySection({ today, onMoverClick }) {
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
          {movers.map((m, i) => <MoverRow key={i} mover={m} onClick={() => onMoverClick?.(m.ticker)} />)}
        </div>
      )}

      <FooterMeta confidence={confidence} data_gaps={data_gaps} />
    </div>
  );
}

function MoverRow({ mover, onClick }) {
  const pos = (mover.move_percent ?? 0) >= 0;
  const tech = mover.technical_state;
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => { if (onClick && (e.key === "Enter" || e.key === " ")) onClick(); }}
      onMouseEnter={(e) => { if (onClick) e.currentTarget.style.background = "rgba(99,102,241,0.04)"; }}
      onMouseLeave={(e) => { if (onClick) e.currentTarget.style.background = "rgba(255,255,255,0.02)"; }}
      style={{
        padding: "14px 16px", background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border-subtle)", borderRadius: "10px",
        cursor: onClick ? "pointer" : "default",
        transition: "background 0.15s, border-color 0.15s",
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
      {tech && (tech.rsi_zone || tech.vol_zone || tech.momentum_state || tech.sma_state) && (
        <TechBadges tech={tech} />
      )}
    </div>
  );
}

function TechBadges({ tech }) {
  return (
    <div style={{
      marginTop: "10px", paddingTop: "10px",
      borderTop: "1px dashed var(--border-subtle)",
      display: "flex", flexDirection: "column", gap: "8px",
    }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
        {tech.rsi_zone && (
          <Pill color={RSI_COLORS[tech.rsi_zone] || "#64748b"} label={`RSI ${tech.rsi_zone}`} tooltip={TECH_TOOLTIPS.rsi} />
        )}
        {tech.vol_zone && (
          <Pill color={VOL_COLORS[tech.vol_zone] || "#64748b"} label={`Vol ${tech.vol_zone}`} tooltip={TECH_TOOLTIPS.vol_vs_avg} />
        )}
        {tech.momentum_state && (
          <Pill color="#a855f7" label={tech.momentum_state.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.momentum_state} />
        )}
        {tech.sma_state && (
          <Pill color="#06b6d4" label={tech.sma_state.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.sma_state} />
        )}
      </div>
      {tech.confirms_or_contradicts && (
        <p style={{ fontSize: "12px", color: "var(--color-text-muted)", fontStyle: "italic", lineHeight: 1.4, margin: 0 }}>
          {tech.confirms_or_contradicts}
        </p>
      )}
    </div>
  );
}

function Pill({ color, label, tooltip }) {
  const pill = (
    <span style={{
      padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
      background: `${color}20`, color, textTransform: "uppercase", letterSpacing: "0.5px",
      cursor: tooltip ? "help" : "default",
    }}>
      {label}
    </span>
  );
  return tooltip ? <Hint text={tooltip}>{pill}</Hint> : pill;
}

function FlowsStrip({ flows }) {
  const fii = flows.fii_net_cr;
  const dii = flows.dii_net_cr;
  const Cell = ({ label, value }) => {
    if (value == null) return null;
    const positive = value >= 0;
    const color = positive ? "var(--color-accent-green)" : "var(--color-accent-red)";
    return (
      <div style={{
        flex: "1 1 140px", padding: "10px 14px", borderRadius: "10px",
        background: "rgba(0,0,0,0.2)", borderLeft: `3px solid ${color}`,
      }}>
        <div style={{ fontSize: "10px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>{label}</div>
        <div style={{ fontSize: "15px", fontWeight: 700, color, fontVariantNumeric: "tabular-nums", marginTop: "2px" }}>
          {positive ? "+" : ""}{Math.round(value).toLocaleString("en-IN")} cr
        </div>
        <div style={{ fontSize: "10px", color: "var(--color-text-muted)", marginTop: "2px" }}>
          {positive ? "buying" : "selling"}
        </div>
      </div>
    );
  };
  return (
    <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "16px" }}>
      <Cell label="FII net (cash)" value={fii} />
      <Cell label="DII net (cash)" value={dii} />
    </div>
  );
}

function TomorrowSection({ tomorrow, onWatchClick, onThemeClick }) {
  if (!tomorrow) return null;
  const {
    per_holding = [],
    macro_themes = [],
    themes = [],
    overall_bias,
    confidence,
    data_gaps = [],
  } = tomorrow;
  // Prefer the new shape; fall back to legacy `themes` for back-compat.
  const macros = macro_themes.length > 0 ? macro_themes : themes;
  const biasColor = DIRECTION_COLORS[overall_bias] || "#64748b";
  const nothing = per_holding.length === 0 && macros.length === 0;

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

      {per_holding.length > 0 && (
        <div style={{ marginBottom: macros.length > 0 ? "18px" : 0 }}>
          <SectionLabel>For your holdings ({per_holding.length})</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {per_holding.map((w, i) => (
              <WatchItemRow key={`w-${i}`} watch={w} onClick={() => onWatchClick?.(w)} />
            ))}
          </div>
        </div>
      )}

      {macros.length > 0 && (
        <div>
          <SectionLabel>Cross-market themes</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {macros.map((t, i) => (
              <ThemeRow key={`t-${i}`} theme={t} onClick={() => onThemeClick?.(t)} />
            ))}
          </div>
        </div>
      )}

      {nothing && (
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", padding: "16px", textAlign: "center", background: "rgba(0,0,0,0.15)", borderRadius: "10px" }}>
          No strong overnight signals tied to your holdings.
        </p>
      )}

      <FooterMeta confidence={confidence} data_gaps={data_gaps} />
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
      textTransform: "uppercase", letterSpacing: "1.2px", marginBottom: "8px",
    }}>
      {children}
    </div>
  );
}

function WatchItemRow({ watch, onClick }) {
  const direction = watch.direction || "neutral";
  const color = DIRECTION_COLORS[direction] || "#64748b";
  const catalystColor = CATALYST_COLORS[watch.catalyst_type] || "#64748b";
  const imp = watch.importance || "medium";
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => { if (onClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onClick(); } }}
      onMouseEnter={(e) => { if (onClick) e.currentTarget.style.background = "rgba(99,102,241,0.04)"; }}
      onMouseLeave={(e) => { if (onClick) e.currentTarget.style.background = "rgba(255,255,255,0.02)"; }}
      style={{
        padding: "14px 16px", background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border-subtle)", borderRadius: "10px",
        borderLeft: `3px solid ${color}`,
        cursor: onClick ? "pointer" : "default",
        transition: "background 0.15s",
      }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>{watch.ticker}</span>
        {watch.sector && (
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>{watch.sector}</span>
        )}
        <span style={{
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${catalystColor}20`, color: catalystColor,
          textTransform: "uppercase", letterSpacing: "0.5px",
        }}>
          {CATALYST_LABELS[watch.catalyst_type] || watch.catalyst_type}
        </span>
        <span style={{
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${color}20`, color, textTransform: "uppercase", letterSpacing: "0.5px",
        }}>
          {direction}
        </span>
        {imp === "high" && (
          <span style={{
            padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
            background: "rgba(245,158,11,0.15)", color: "#f59e0b",
            textTransform: "uppercase", letterSpacing: "0.5px",
          }}>
            ★ High
          </span>
        )}
      </div>
      {watch.what_to_watch && (
        <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5, margin: 0 }}>
          {watch.what_to_watch}
        </p>
      )}
    </div>
  );
}

function ThemeRow({ theme, onClick }) {
  const color = DIRECTION_COLORS[theme.direction] || "#64748b";
  const importance = theme.importance || "medium";
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => { if (onClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onClick(); } }}
      onMouseEnter={(e) => { if (onClick) e.currentTarget.style.background = "rgba(99,102,241,0.04)"; }}
      onMouseLeave={(e) => { if (onClick) e.currentTarget.style.background = "rgba(255,255,255,0.02)"; }}
      style={{
        padding: "14px 16px", background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border-subtle)", borderRadius: "10px", borderLeft: `3px solid ${color}`,
        cursor: onClick ? "pointer" : "default",
        transition: "background 0.15s",
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

// ---------------------------------------------------------------------------
// MoverDetailModal — full reasoning chain for one mover (click-through from
// MoverRow). Renders the raw evidence the AI used: every attribution item with
// its weight + cited source headline resolved, full technicals in raw numbers,
// every semantic_news match with similarity score, every keyword news headline.
// ---------------------------------------------------------------------------
function MoverDetailModal({ ticker, mover, detail, onClose }) {
  const newsById = {};
  for (const n of (detail?.news || [])) newsById[n.id] = n;
  for (const s of (detail?.semantic_news || [])) newsById[s.id] = s;
  const resolveSource = (src) => {
    if (!src) return null;
    return newsById[src] || null;
  };

  const move = mover?.move_percent ?? detail?.change_percent_today;
  const pos = (move ?? 0) >= 0;
  const moveColor = pos ? "var(--color-accent-green)" : "var(--color-accent-red)";
  const tech = detail?.technicals;
  const earnings = detail?.upcoming_earnings;

  const header = (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "12px", flexWrap: "wrap" }}>
        <h3 style={{ fontSize: "20px", fontWeight: 800, color: "var(--color-text-primary)", margin: 0 }}>
          {ticker}
        </h3>
        {detail?.name && (
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>{detail.name}</span>
        )}
        {move != null && (
          <span style={{ fontSize: "20px", fontWeight: 800, color: moveColor, fontVariantNumeric: "tabular-nums" }}>
            {pos ? "▲ +" : "▼ "}{move}%
          </span>
        )}
        {detail?.sector_index_return_today != null && detail?.excess_return_today != null && (
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
            vs sector {detail.sector_index_return_today >= 0 ? "+" : ""}{detail.sector_index_return_today}%
            &nbsp;·&nbsp; excess {detail.excess_return_today >= 0 ? "+" : ""}{detail.excess_return_today}%
          </span>
        )}
      </div>
      {mover?.primary_driver && (
        <div style={{
          display: "inline-block", marginTop: "8px",
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${DRIVER_COLORS[mover.primary_driver] || "#64748b"}20`,
          color: DRIVER_COLORS[mover.primary_driver] || "#64748b",
          textTransform: "uppercase", letterSpacing: "0.5px",
        }}>
          Primary driver: {DRIVER_LABELS[mover.primary_driver] || mover.primary_driver}
        </div>
      )}
    </div>
  );

  return (
    <Modal onClose={onClose} header={header}>
        {/* Attribution chain — each cited claim + the resolved headline */}
        {mover?.attribution?.length > 0 && (
          <ModalSection title="Attribution chain">
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {mover.attribution.map((a, i) => {
                const src = resolveSource(a.source);
                return (
                  <div key={i} style={{
                    padding: "10px 12px",
                    background: "rgba(0,0,0,0.2)", borderRadius: "8px",
                    borderLeft: "2px solid var(--color-accent-secondary)",
                  }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "4px" }}>
                      {a.weight_pct != null && (
                        <span style={{
                          fontSize: "10px", fontWeight: 700, padding: "2px 6px", borderRadius: "4px",
                          background: "rgba(99,102,241,0.18)", color: "var(--color-accent-secondary)",
                          minWidth: "38px", textAlign: "center", flexShrink: 0,
                        }}>{a.weight_pct}%</span>
                      )}
                      <span style={{ fontSize: "13px", color: "var(--color-text-primary)", lineHeight: 1.45 }}>
                        {claimText(a)}
                      </span>
                    </div>
                    {a.source && (
                      <div style={{ fontSize: "10px", color: "var(--color-text-muted)", marginLeft: a.weight_pct != null ? "48px" : 0 }}>
                        cite: <code style={{ color: "var(--color-accent-cyan)" }}>{a.source}</code>
                        {src && (
                          <>
                            &nbsp;·&nbsp; <span style={{ fontStyle: "italic" }}>{src.headline}</span>
                            {src.source && <> &nbsp;·&nbsp; {src.source}</>}
                            {src.similarity != null && (
                              <> &nbsp;·&nbsp; sim {src.similarity}</>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ModalSection>
        )}

        {/* Technical state — full raw numbers */}
        {tech && (
          <ModalSection title="Technical state">
            <div style={{
              display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              gap: "8px",
            }}>
              <Metric label="RSI (14)" value={tech.rsi14 != null ? tech.rsi14 : "—"} accent={RSI_COLORS[tech.rsi_zone]} hint={tech.rsi_zone} tooltip={TECH_TOOLTIPS.rsi} />
              <Metric label="Volume vs 20d avg" value={tech.vol_vs_avg20 != null ? `${tech.vol_vs_avg20}x` : "—"} accent={VOL_COLORS[tech.vol_zone]} hint={tech.vol_zone} tooltip={TECH_TOOLTIPS.vol_vs_avg} />
              <Metric label="Momentum 5d" value={tech.momentum_5d_pct != null ? `${tech.momentum_5d_pct > 0 ? "+" : ""}${tech.momentum_5d_pct}%` : "—"} tooltip={TECH_TOOLTIPS.momentum_5d} />
              <Metric label="Momentum 20d" value={tech.momentum_20d_pct != null ? `${tech.momentum_20d_pct > 0 ? "+" : ""}${tech.momentum_20d_pct}%` : "—"} hint={tech.momentum_state?.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.momentum_20d} />
              <Metric label="vs SMA20" value={tech.pct_from_sma20 != null ? `${tech.pct_from_sma20 > 0 ? "+" : ""}${tech.pct_from_sma20}%` : "—"} tooltip={TECH_TOOLTIPS.vs_sma20} />
              <Metric label="vs SMA50" value={tech.pct_from_sma50 != null ? `${tech.pct_from_sma50 > 0 ? "+" : ""}${tech.pct_from_sma50}%` : "—"} hint={tech.sma_state?.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.vs_sma50} />
              <Metric label="From 20d high" value={tech.pct_from_20d_high != null ? `${tech.pct_from_20d_high}%` : "—"} tooltip={TECH_TOOLTIPS.from_20d_high} />
              <Metric label="From 20d low" value={tech.pct_from_20d_low != null ? `+${tech.pct_from_20d_low}%` : "—"} tooltip={TECH_TOOLTIPS.from_20d_low} />
            </div>
            {mover?.technical_state?.confirms_or_contradicts && (
              <p style={{ marginTop: "10px", fontSize: "12px", color: "var(--color-text-muted)", fontStyle: "italic" }}>
                {mover.technical_state.confirms_or_contradicts}
              </p>
            )}
          </ModalSection>
        )}

        {/* Earnings */}
        {earnings && (
          <ModalSection title="Upcoming earnings">
            <div style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
              <span style={{ color: "var(--color-text-primary)", fontWeight: 700 }}>{earnings.date}</span>
              {" "}({earnings.days_ahead === 0 ? "today" : `${earnings.days_ahead} days away`})
            </div>
          </ModalSection>
        )}

        {/* Semantic news — pgvector matches */}
        {detail?.semantic_news?.length > 0 && (
          <ModalSection title={`Semantic matches (${detail.semantic_news.length})`} hint="Themes that affect this ticker — headlines don't have to name it">
            <NewsList items={detail.semantic_news} showSimilarity />
          </ModalSection>
        )}

        {/* Keyword news — RSS hits naming the ticker */}
        {detail?.news?.length > 0 && (
          <ModalSection title={`Headlines mentioning ${ticker} (${detail.news.length})`}>
            <NewsList items={detail.news} />
          </ModalSection>
        )}

        {!detail && (
          <p style={{ fontSize: "12px", color: "var(--color-text-muted)", padding: "12px 0" }}>
            No detail payload available for this ticker.
          </p>
        )}
    </Modal>
  );
}

function ModalSection({ title, hint, children }) {
  return (
    <div style={{ marginTop: "18px" }}>
      <div style={{
        display: "flex", alignItems: "baseline", gap: "10px",
        marginBottom: "10px",
      }}>
        <span style={{
          fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
          textTransform: "uppercase", letterSpacing: "1.2px",
        }}>{title}</span>
        {hint && (
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)", fontStyle: "italic" }}>{hint}</span>
        )}
      </div>
      {children}
    </div>
  );
}

function Metric({ label, value, accent, hint, tooltip }) {
  const labelEl = (
    <span style={{ fontSize: "9px", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
      {label}
    </span>
  );
  return (
    <div style={{
      padding: "8px 10px", background: "rgba(0,0,0,0.2)", borderRadius: "8px",
      borderLeft: accent ? `2px solid ${accent}` : "2px solid transparent",
    }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        {tooltip ? <Hint text={tooltip} showIcon>{labelEl}</Hint> : labelEl}
      </div>
      <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums", marginTop: "2px" }}>{value}</div>
      {hint && (
        <div style={{ fontSize: "10px", color: accent || "var(--color-text-muted)", marginTop: "2px", textTransform: "uppercase", letterSpacing: "0.5px" }}>{hint}</div>
      )}
    </div>
  );
}

function NewsList({ items, showSimilarity }) {
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "8px" }}>
      {items.map((n, i) => (
        <li key={n.id || i} style={{
          padding: "8px 10px",
          background: "rgba(255,255,255,0.02)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "8px",
          fontSize: "12px", color: "var(--color-text-secondary)",
          lineHeight: 1.5,
        }}>
          <div style={{ color: "var(--color-text-primary)" }}>{n.headline}</div>
          <div style={{ marginTop: "4px", display: "flex", gap: "10px", flexWrap: "wrap", fontSize: "10px", color: "var(--color-text-muted)" }}>
            {n.id && <code style={{ color: "var(--color-accent-cyan)" }}>{n.id}</code>}
            {n.source && <span>· {n.source}</span>}
            {showSimilarity && n.similarity != null && (
              <span>· sim <span style={{ color: "#a855f7", fontWeight: 700 }}>{n.similarity}</span></span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

// Backwards-compat alias — earlier modals were authored against `ModalShell`.
// `Modal` (portal + ESC + scroll lock) is now the canonical shell; keep this
// thin alias rather than rewriting every call site.
function ModalShell(props) {
  return <Modal {...props} />;
}

// ---------------------------------------------------------------------------
// WatchItemDetailModal — opens when a "For your holdings" row is clicked.
// Renders the catalyst sentence, full per-ticker technical state from
// holdings_detail, upcoming earnings, every supporting semantic + keyword
// news headline, and the sources the LLM cited.
// ---------------------------------------------------------------------------
function WatchItemDetailModal({ watch, detail, onClose }) {
  const ticker = watch?.ticker;
  const tech = detail?.technicals;
  const earnings = detail?.upcoming_earnings;
  const direction = watch?.direction || "neutral";
  const dirColor = DIRECTION_COLORS[direction] || "#64748b";
  const catalystColor = CATALYST_COLORS[watch?.catalyst_type] || "#64748b";

  const header = (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "12px", flexWrap: "wrap" }}>
        <h3 style={{ fontSize: "20px", fontWeight: 800, color: "var(--color-text-primary)", margin: 0 }}>{ticker}</h3>
        {detail?.name && (
          <span style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>{detail.name}</span>
        )}
        {detail?.sector && (
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>· {detail.sector}</span>
        )}
      </div>
      <div style={{ display: "flex", gap: "6px", marginTop: "8px", flexWrap: "wrap" }}>
        <span style={{
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${catalystColor}20`, color: catalystColor,
          textTransform: "uppercase", letterSpacing: "0.5px",
        }}>
          {CATALYST_LABELS[watch?.catalyst_type] || watch?.catalyst_type}
        </span>
        <span style={{
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${dirColor}20`, color: dirColor,
          textTransform: "uppercase", letterSpacing: "0.5px",
        }}>{direction}</span>
        {watch?.importance === "high" && (
          <span style={{
            padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
            background: "rgba(245,158,11,0.15)", color: "#f59e0b",
            textTransform: "uppercase", letterSpacing: "0.5px",
          }}>★ High</span>
        )}
      </div>
    </div>
  );

  return (
    <ModalShell onClose={onClose} header={header}>
      {watch?.what_to_watch && (
        <ModalSection title="What to watch">
          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.55, margin: 0 }}>
            {watch.what_to_watch}
          </p>
        </ModalSection>
      )}

      {earnings && (
        <ModalSection title="Upcoming earnings">
          <div style={{
            padding: "10px 12px", borderRadius: "8px",
            background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.25)",
            fontSize: "13px", color: "var(--color-text-secondary)",
          }}>
            <span style={{ color: "var(--color-text-primary)", fontWeight: 700 }}>{earnings.date}</span>
            {" "}({earnings.days_ahead === 0 ? "today" : `${earnings.days_ahead} days away`})
          </div>
        </ModalSection>
      )}

      {tech && (
        <ModalSection title="Technical setup">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "8px" }}>
            <Metric label="RSI (14)" value={tech.rsi14 != null ? tech.rsi14 : "—"} accent={RSI_COLORS[tech.rsi_zone]} hint={tech.rsi_zone} tooltip={TECH_TOOLTIPS.rsi} />
            <Metric label="Volume vs 20d avg" value={tech.vol_vs_avg20 != null ? `${tech.vol_vs_avg20}x` : "—"} accent={VOL_COLORS[tech.vol_zone]} hint={tech.vol_zone} tooltip={TECH_TOOLTIPS.vol_vs_avg} />
            <Metric label="Momentum 5d" value={tech.momentum_5d_pct != null ? `${tech.momentum_5d_pct > 0 ? "+" : ""}${tech.momentum_5d_pct}%` : "—"} tooltip={TECH_TOOLTIPS.momentum_5d} />
            <Metric label="Momentum 20d" value={tech.momentum_20d_pct != null ? `${tech.momentum_20d_pct > 0 ? "+" : ""}${tech.momentum_20d_pct}%` : "—"} hint={tech.momentum_state?.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.momentum_20d} />
            <Metric label="vs SMA50" value={tech.pct_from_sma50 != null ? `${tech.pct_from_sma50 > 0 ? "+" : ""}${tech.pct_from_sma50}%` : "—"} hint={tech.sma_state?.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.vs_sma50} />
            <Metric label="From 20d high" value={tech.pct_from_20d_high != null ? `${tech.pct_from_20d_high}%` : "—"} tooltip={TECH_TOOLTIPS.from_20d_high} />
          </div>
        </ModalSection>
      )}

      {watch?.sources?.length > 0 && (
        <ModalSection title="Cited sources">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {watch.sources.map((s, i) => (
              <code key={i} style={{
                fontSize: "10px", padding: "3px 7px", borderRadius: "5px",
                background: "rgba(6,182,212,0.10)", color: "var(--color-accent-cyan)",
              }}>{s}</code>
            ))}
          </div>
        </ModalSection>
      )}

      {detail?.semantic_news?.length > 0 && (
        <ModalSection
          title={`Semantic catalysts (${detail.semantic_news.length})`}
          hint="Themes that affect this ticker — headlines don't have to name it"
        >
          <NewsList items={detail.semantic_news} showSimilarity />
        </ModalSection>
      )}

      {detail?.news?.length > 0 && (
        <ModalSection title={`Headlines mentioning ${ticker} (${detail.news.length})`}>
          <NewsList items={detail.news} />
        </ModalSection>
      )}

      {!detail && (
        <p style={{ fontSize: "12px", color: "var(--color-text-muted)", padding: "12px 0" }}>
          No detail payload available for this ticker.
        </p>
      )}
    </ModalShell>
  );
}

// ---------------------------------------------------------------------------
// ThemeDetailModal — opens when a "Cross-market themes" row is clicked.
// Shows the LLM's mechanism + source citation, then renders each affected
// holding's current state as a row so the user sees the transmission chain.
// ---------------------------------------------------------------------------
function ThemeDetailModal({ theme, holdingsDetail, sectorReturns, onClose }) {
  const direction = theme?.direction || "neutral";
  const color = DIRECTION_COLORS[direction] || "#64748b";
  const sectorMap = {};
  for (const s of (sectorReturns || [])) sectorMap[s.sector] = s.change_percent;

  const header = (
    <div>
      <h3 style={{ fontSize: "18px", fontWeight: 800, color: "var(--color-text-primary)", margin: 0, lineHeight: 1.35 }}>
        {theme?.theme}
      </h3>
      <div style={{ display: "flex", gap: "6px", marginTop: "8px", flexWrap: "wrap" }}>
        <span style={{
          padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
          background: `${color}20`, color, textTransform: "uppercase", letterSpacing: "0.5px",
        }}>{direction}</span>
        {theme?.importance === "high" && (
          <span style={{
            padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700,
            background: "rgba(245,158,11,0.15)", color: "#f59e0b",
            textTransform: "uppercase", letterSpacing: "0.5px",
          }}>★ High importance</span>
        )}
      </div>
    </div>
  );

  return (
    <ModalShell onClose={onClose} header={header}>
      {theme?.mechanism && (
        <ModalSection title="Transmission mechanism">
          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.55, margin: 0 }}>
            {claimText(theme.mechanism)}
          </p>
          {claimSource(theme.mechanism) && (
            <div style={{ fontSize: "10px", color: "var(--color-text-muted)", marginTop: "6px" }}>
              cite: <code style={{ color: "var(--color-accent-cyan)" }}>{claimSource(theme.mechanism)}</code>
            </div>
          )}
        </ModalSection>
      )}

      {theme?.affected_holdings?.length > 0 && (
        <ModalSection title={`Affected holdings (${theme.affected_holdings.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {theme.affected_holdings.map((t) => {
              const d = holdingsDetail?.[t];
              const tech = d?.technicals;
              const chg = d?.change_percent_today;
              return (
                <div key={t} style={{
                  padding: "10px 12px", borderRadius: "8px",
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid var(--border-subtle)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                    <span style={{
                      fontSize: "13px", fontWeight: 800, color: "var(--color-text-primary)",
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                    }}>{t}</span>
                    {d?.sector && (
                      <span style={{ fontSize: "10px", color: "var(--color-text-muted)" }}>{d.sector}</span>
                    )}
                    {chg != null && (
                      <span style={{
                        fontSize: "12px", fontWeight: 700, fontVariantNumeric: "tabular-nums",
                        color: chg >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)",
                      }}>
                        {chg >= 0 ? "▲ +" : "▼ "}{chg}%
                      </span>
                    )}
                    {tech?.rsi_zone && <Pill color={RSI_COLORS[tech.rsi_zone]} label={`RSI ${tech.rsi_zone}`} tooltip={TECH_TOOLTIPS.rsi} />}
                    {tech?.vol_zone && <Pill color={VOL_COLORS[tech.vol_zone]} label={`Vol ${tech.vol_zone}`} tooltip={TECH_TOOLTIPS.vol_vs_avg} />}
                    {tech?.momentum_state && <Pill color="#a855f7" label={tech.momentum_state.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.momentum_state} />}
                    {tech?.sma_state && <Pill color="#06b6d4" label={tech.sma_state.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.sma_state} />}
                  </div>
                </div>
              );
            })}
          </div>
        </ModalSection>
      )}

      {theme?.affected_sectors?.length > 0 && (
        <ModalSection title={`Affected sectors (${theme.affected_sectors.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {theme.affected_sectors.map((s) => {
              const chg = sectorMap[s];
              return (
                <div key={s} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "8px 12px", borderRadius: "8px",
                  background: "rgba(6,182,212,0.06)",
                  border: "1px solid rgba(6,182,212,0.18)",
                }}>
                  <span style={{ fontSize: "12px", color: "var(--color-accent-cyan)", fontWeight: 700 }}>{s}</span>
                  {chg != null && (
                    <span style={{
                      fontSize: "12px", fontWeight: 700, fontVariantNumeric: "tabular-nums",
                      color: chg >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)",
                    }}>
                      {chg >= 0 ? "+" : ""}{chg}% today
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </ModalSection>
      )}
    </ModalShell>
  );
}
