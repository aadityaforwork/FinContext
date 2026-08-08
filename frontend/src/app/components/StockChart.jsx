"use client";

/**
 * StockChart — Editorial Quiet edition.
 *
 * Replaces the generic Recharts demo with the same vocabulary as the rest of
 * the product:
 *   • Mono caps labels, no big-bold price hero
 *   • Outlined timeframe toggles (matching the financial-statement period
 *     toggles in CompanyView)
 *   • Period stats strip — open / high / low / latest / range / % move,
 *     all derived locally from sliced data (no extra backend call needed)
 *   • Thinner chart stroke, lower-alpha gradient, mono tick labels
 *   • Tooltip is editorial-quiet — hairline border, mono numerals,
 *     no glass-card class
 *   • Empty + loading states share the rest of the product's voice
 */

import { useMemo, useState, useEffect } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { API_BASE as _SHARED_API_BASE } from "../lib/api";
import { Skeleton } from "./Loaders";
const API_BASE = _SHARED_API_BASE;

const SERIF = "var(--font-serif)";
const MONO  = "var(--font-mono)";

// Number of trading sessions per timeframe — used to slice the price data
// the backend returns (which is typically 1 year of daily candles).
const TIMEFRAME_BARS = {
  "1W": 7,
  "1M": 22,
  "3M": 66,
  "6M": 132,
  "1Y": 252,
};

// ---------------------------------------------------------------------------
// Tooltip — editorial-quiet, no glass-card.
// ---------------------------------------------------------------------------
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0].payload;
  const dateStr = (() => {
    try {
      return new Date(label).toLocaleDateString("en-IN", {
        day: "2-digit", month: "short", year: "numeric",
        timeZone: "Asia/Kolkata",
      });
    } catch { return label; }
  })();
  return (
    <div
      style={{
        padding: "12px 14px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--radius-control)",
        boxShadow: "0 8px 20px rgba(0,0,0,0.4)",
        fontFamily: MONO,
        fontSize: "11.5px",
        minWidth: "180px",
      }}
    >
      <div
        style={{
          fontSize: "9.5px", fontWeight: 700,
          letterSpacing: "0.18em", textTransform: "uppercase",
          color: "var(--color-text-muted)",
          marginBottom: "10px",
        }}
      >
        {dateStr}
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "auto auto",
          gap: "5px 18px",
          color: "var(--color-text-secondary)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <span style={{ fontSize: "10px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>Open</span>
        <span style={{ textAlign: "right" }}>₹{d.open?.toFixed(2) ?? "—"}</span>
        <span style={{ fontSize: "10px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>High</span>
        <span style={{ textAlign: "right", color: "var(--color-accent-green)" }}>₹{d.high?.toFixed(2) ?? "—"}</span>
        <span style={{ fontSize: "10px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>Low</span>
        <span style={{ textAlign: "right", color: "var(--color-accent-red)" }}>₹{d.low?.toFixed(2) ?? "—"}</span>
        <span style={{ fontSize: "10px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>Close</span>
        <span style={{ textAlign: "right", color: "var(--color-text-primary)", fontWeight: 700 }}>
          ₹{d.close?.toFixed(2) ?? "—"}
        </span>
        {d.volume != null && (
          <>
            <span style={{ fontSize: "10px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>Vol</span>
            <span style={{ textAlign: "right" }}>
              {d.volume >= 1e7 ? `${(d.volume / 1e7).toFixed(1)}Cr` :
               d.volume >= 1e5 ? `${(d.volume / 1e5).toFixed(1)}L`  :
                                 d.volume.toLocaleString("en-IN")}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------
function shortDate(val) {
  try {
    const d = new Date(val);
    const day = String(d.getDate()).padStart(2, "0");
    const mon = d.toLocaleString("en-IN", { month: "short", timeZone: "Asia/Kolkata" });
    return `${day} ${mon}`;
  } catch { return val; }
}

function formatINR(n) {
  if (n == null) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

// ---------------------------------------------------------------------------
// Stat tile — used in the period summary strip.
// ---------------------------------------------------------------------------
function StatTile({ label, value, accent, sub }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "3px", minWidth: 0 }}>
      <span style={{
        fontFamily: MONO, fontSize: "9.5px", fontWeight: 700,
        letterSpacing: "0.16em", textTransform: "uppercase",
        color: "var(--color-text-muted)",
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: MONO, fontSize: "13px", fontWeight: 700,
        color: accent || "var(--color-text-primary)",
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "0.01em",
        whiteSpace: "nowrap",
      }}>
        {value}
      </span>
      {sub && (
        <span style={{
          fontFamily: MONO, fontSize: "9.5px", fontWeight: 600,
          color: "var(--color-text-muted)", letterSpacing: "0.04em",
        }}>
          {sub}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function StockChart({ ticker, stockName }) {
  const [priceData, setPriceData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [timeframe, setTimeframe] = useState("3M");

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    fetch(`${API_BASE}/api/stocks/${ticker}/price`)
      .then((res) => res.json())
      .then((data) => {
        setPriceData(data.data || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [ticker]);

  // Slice the price data by the active timeframe. The backend returns up to
  // a year of daily candles; we just take the tail. Doing this client-side
  // means a timeframe flip is instant — no extra API call.
  const sliced = useMemo(() => {
    const bars = TIMEFRAME_BARS[timeframe] || TIMEFRAME_BARS["3M"];
    if (!priceData.length) return [];
    return priceData.slice(-bars);
  }, [priceData, timeframe]);

  // Period stats — derived from the slice. All deterministic, no LLM.
  const stats = useMemo(() => {
    if (!sliced.length) return null;
    const first = sliced[0];
    const last  = sliced[sliced.length - 1];
    let hi = -Infinity, lo = Infinity, hiBar = null, loBar = null;
    let cumVol = 0, volBars = 0;
    for (const b of sliced) {
      if (b.high > hi) { hi = b.high; hiBar = b; }
      if (b.low  < lo) { lo = b.low;  loBar = b; }
      if (b.volume) { cumVol += b.volume; volBars += 1; }
    }
    const periodChange    = last.close - first.close;
    const periodChangePct = (periodChange / first.close) * 100;
    const range           = hi - lo;
    const rangePct        = (range / first.close) * 100;
    const pctFromHigh     = ((last.close - hi) / hi) * 100;
    const avgVol          = volBars ? cumVol / volBars : null;
    return {
      first, last, hi, lo, hiBar, loBar,
      periodChange, periodChangePct, range, rangePct,
      pctFromHigh, avgVol,
    };
  }, [sliced]);

  if (!ticker) {
    return (
      <div style={{
        padding: "60px 28px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        textAlign: "center",
      }}>
        <div style={{
          fontFamily: MONO, fontSize: "10.5px", fontWeight: 700,
          letterSpacing: "0.22em", textTransform: "uppercase",
          color: "var(--color-text-muted)",
          marginBottom: "14px",
        }}>
          Price chart · awaiting ticker
        </div>
        <p style={{
          fontFamily: SERIF, fontStyle: "italic",
          fontSize: "16px", color: "var(--color-text-secondary)",
          margin: 0, letterSpacing: "-0.003em",
        }}>
          Select a stock to view its price history.
        </p>
      </div>
    );
  }

  const isPos = stats ? stats.periodChangePct >= 0 : true;
  const accentColor = isPos ? "var(--color-accent-green)" : "var(--color-accent-red)";

  return (
    <div style={{
      padding: "22px 24px",
      background: "var(--color-bg-card)",
      border: "1px solid var(--border-subtle)",
      borderRadius: "var(--radius-card)",
    }}>
      {/* HEADER — mono name + tiny period label + outlined timeframe toggles */}
      <div style={{
        display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", gap: "16px",
        marginBottom: "18px", flexWrap: "wrap",
      }}>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2, minWidth: 0 }}>
          <span style={{
            fontFamily: MONO, fontSize: "9.5px", fontWeight: 700,
            letterSpacing: "0.22em", textTransform: "uppercase",
            color: "var(--color-text-muted)", marginBottom: "4px",
          }}>
            Price history &nbsp;·&nbsp; {timeframe}
          </span>
          <h3 style={{
            fontSize: "16px", fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.005em",
            margin: 0,
          }}>
            {stockName || ticker}
          </h3>
        </div>

        {/* Timeframe toggles — outlined editorial buttons */}
        <div style={{
          display: "inline-flex", gap: "2px",
          padding: "2px",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-control)",
          background: "var(--color-bg-secondary, transparent)",
        }}>
          {Object.keys(TIMEFRAME_BARS).map((tf) => {
            const on = timeframe === tf;
            return (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframe(tf)}
                style={{
                  padding: "5px 11px",
                  borderRadius: "4px",
                  border: "none",
                  background: on ? "var(--color-accent-primary)" : "transparent",
                  color: on ? "#fff" : "var(--color-text-muted)",
                  fontSize: "10.5px", fontWeight: 700,
                  letterSpacing: "0.1em",
                  fontFamily: MONO,
                  cursor: "pointer",
                  transition: "background 0.15s, color 0.15s",
                }}
              >
                {tf}
              </button>
            );
          })}
        </div>
      </div>

      {/* PERIOD STATS STRIP — only when we have data */}
      {!loading && stats && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
          gap: "16px",
          padding: "14px 16px",
          marginBottom: "16px",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-control)",
          borderLeft: `2px solid ${accentColor}`,
        }}>
          <StatTile
            label="Last"
            value={formatINR(stats.last.close)}
          />
          <StatTile
            label={`${timeframe} move`}
            value={`${stats.periodChangePct >= 0 ? "+" : ""}${stats.periodChangePct.toFixed(2)}%`}
            accent={accentColor}
            sub={`${stats.periodChange >= 0 ? "+" : "−"}₹${Math.abs(stats.periodChange).toFixed(2)}`}
          />
          <StatTile
            label="Period high"
            value={formatINR(stats.hi)}
            sub={stats.hiBar ? shortDate(stats.hiBar.date) : null}
            accent="var(--color-accent-green)"
          />
          <StatTile
            label="Period low"
            value={formatINR(stats.lo)}
            sub={stats.loBar ? shortDate(stats.loBar.date) : null}
            accent="var(--color-accent-red)"
          />
          <StatTile
            label="From high"
            value={`${stats.pctFromHigh >= 0 ? "+" : ""}${stats.pctFromHigh.toFixed(2)}%`}
            accent={stats.pctFromHigh >= -3 ? "var(--color-accent-green)" : "var(--color-text-secondary)"}
          />
        </div>
      )}

      {/* CHART */}
      {loading ? (
        <Skeleton h={300} r={12} />
      ) : sliced.length === 0 ? (
        <p style={{
          padding: "60px 20px", textAlign: "center",
          fontFamily: SERIF, fontStyle: "italic",
          fontSize: "14px", color: "var(--color-text-muted)",
          border: "1px dashed var(--border-subtle)",
          borderRadius: "var(--radius-card)",
        }}>
          No price data available for this stock.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={sliced} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
            <defs>
              {/* Lower-alpha gradient than the old 0.3 → 0; reads as a quiet
                  hint not a flag. */}
              <linearGradient id="sc-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"
                      stopColor={isPos ? "var(--color-accent-green)" : "var(--color-accent-red)"}
                      stopOpacity={0.18} />
                <stop offset="100%"
                      stopColor={isPos ? "var(--color-accent-green)" : "var(--color-accent-red)"}
                      stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="2 4"
              stroke="rgba(255,255,255,0.05)"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--color-text-muted)", fontSize: 10, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
              tickFormatter={shortDate}
              minTickGap={28}
              interval="preserveStartEnd"
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--color-text-muted)", fontSize: 10, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
              domain={["auto", "auto"]}
              tickFormatter={(val) => `₹${Math.round(val).toLocaleString("en-IN")}`}
              width={68}
              tickCount={5}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: "rgba(255,255,255,0.18)", strokeWidth: 1, strokeDasharray: "2 4" }} />
            <Area
              type="linear"
              dataKey="close"
              stroke={isPos ? "var(--color-accent-green)" : "var(--color-accent-red)"}
              strokeWidth={1.5}
              fill="url(#sc-fill)"
              animationDuration={500}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0, fill: isPos ? "var(--color-accent-green)" : "var(--color-accent-red)" }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
