"use client";

import { useState, useEffect } from "react";
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
const API_BASE = _SHARED_API_BASE;

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0].payload;
  return (
    <div
      className="glass-card"
      style={{
        padding: "12px 16px",
        fontSize: "12px",
      }}
    >
      <p style={{ fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "6px" }}>{label}</p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "auto auto",
          gap: "2px 16px",
          color: "var(--color-text-secondary)",
        }}
      >
        <span>Open</span><span style={{ textAlign: "right", fontFamily: "monospace" }}>₹{d.open?.toFixed(2)}</span>
        <span>High</span><span style={{ textAlign: "right", fontFamily: "monospace", color: "var(--color-accent-green)" }}>₹{d.high?.toFixed(2)}</span>
        <span>Low</span><span style={{ textAlign: "right", fontFamily: "monospace", color: "var(--color-accent-red)" }}>₹{d.low?.toFixed(2)}</span>
        <span>Close</span><span style={{ textAlign: "right", fontFamily: "monospace", fontWeight: 600, color: "var(--color-accent-secondary)" }}>₹{d.close?.toFixed(2)}</span>
        <span>Volume</span><span style={{ textAlign: "right", fontFamily: "monospace" }}>{(d.volume / 1_000_000).toFixed(1)}M</span>
      </div>
    </div>
  );
}

export default function StockChart({ ticker, stockName }) {
  const [priceData, setPriceData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [timeframe, setTimeframe] = useState("1M");

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

  if (!ticker) {
    return (
      <div
        className="glass-card"
        style={{
          padding: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "400px",
        }}
      >
        <p style={{ fontSize: "14px", color: "var(--color-text-muted)" }}>
          Select a stock to view price chart
        </p>
      </div>
    );
  }

  const priceChange = priceData.length >= 2
    ? priceData[priceData.length - 1].close - priceData[0].close
    : 0;
  const priceChangePercent = priceData.length >= 2
    ? ((priceChange / priceData[0].close) * 100).toFixed(2)
    : "0.00";
  const isPositive = priceChange >= 0;

  return (
    <div className="glass-card" style={{ padding: "24px" }}>
      {/* Chart Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <h3 style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>
              {stockName || ticker}
            </h3>
            <span
              style={{
                padding: "2px 8px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 500,
                background: isPositive ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)",
                color: isPositive ? "var(--color-accent-green)" : "var(--color-accent-red)",
              }}
            >
              {isPositive ? "▲" : "▼"} {isPositive ? "+" : ""}{priceChangePercent}%
            </span>
          </div>
          {priceData.length > 0 && (
            <p style={{ fontSize: "28px", fontWeight: 700, marginTop: "4px", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>
              ₹{priceData[priceData.length - 1].close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </p>
          )}
        </div>

        {/* Timeframe buttons */}
        <div
          style={{
            display: "flex",
            gap: "4px",
            padding: "4px",
            borderRadius: "12px",
            background: "var(--color-bg-secondary)",
          }}
        >
          {["1W", "1M", "3M", "1Y"].map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              style={{
                padding: "6px 12px",
                borderRadius: "8px",
                fontSize: "12px",
                fontWeight: 500,
                border: "none",
                cursor: "pointer",
                transition: "all 0.2s",
                background: timeframe === tf ? "var(--color-accent-primary)" : "transparent",
                color: timeframe === tf ? "white" : "var(--color-text-muted)",
              }}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      {loading ? (
        <div className="shimmer" style={{ height: "300px", borderRadius: "12px" }} />
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={priceData} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0.3} />
                <stop offset="100%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(148,163,184,0.08)"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#64748b", fontSize: 11 }}
              tickFormatter={(val) => {
                const d = new Date(val);
                return `${d.getDate()}/${d.getMonth() + 1}`;
              }}
              interval="preserveStartEnd"
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#64748b", fontSize: 11 }}
              domain={["auto", "auto"]}
              tickFormatter={(val) => `₹${val}`}
              width={65}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="close"
              stroke={isPositive ? "#10b981" : "#ef4444"}
              strokeWidth={2}
              fill="url(#chartGradient)"
              animationDuration={800}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
