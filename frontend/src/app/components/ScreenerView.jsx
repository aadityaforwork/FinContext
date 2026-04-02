"use client";

import { useState, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function ScreenerView({ onNavigate }) {
  const [stocks, setStocks] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState("");
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState("ticker");
  const [sortDir, setSortDir] = useState("asc");
  const [actionMsg, setActionMsg] = useState("");

  // Fetch sectors
  useEffect(() => {
    fetch(`${API_BASE}/api/stocks/sectors`)
      .then((r) => r.json())
      .then(setSectors)
      .catch(() => {});
  }, []);

  // Fetch stocks
  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (searchQuery) params.set("q", searchQuery);
    if (selectedSector) params.set("sector", selectedSector);
    params.set("limit", "100");

    fetch(`${API_BASE}/api/stocks/search?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setStocks(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [searchQuery, selectedSector]);

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
  };

  const sortedStocks = [...stocks].sort((a, b) => {
    let aVal = a[sortBy];
    let bVal = b[sortBy];
    if (typeof aVal === "string") aVal = aVal.toLowerCase();
    if (typeof bVal === "string") bVal = bVal.toLowerCase();
    if (aVal < bVal) return sortDir === "asc" ? -1 : 1;
    if (aVal > bVal) return sortDir === "asc" ? 1 : -1;
    return 0;
  });

  const addToWatchlist = async (ticker) => {
    try {
      await fetch(`${API_BASE}/api/watchlist/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      setActionMsg(`✓ ${ticker} added to watchlist`);
      setTimeout(() => setActionMsg(""), 2000);
    } catch (e) {
      setActionMsg(`Failed to add ${ticker}`);
    }
  };

  const addToPortfolio = async (ticker, price) => {
    const qty = prompt(`Enter quantity for ${ticker}:`, "10");
    if (!qty) return;
    const buyPrice = prompt(`Buy price (₹):`, price.toString());
    if (!buyPrice) return;
    try {
      await fetch(`${API_BASE}/api/portfolio/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          quantity: parseFloat(qty),
          buy_price: parseFloat(buyPrice),
        }),
      });
      setActionMsg(`✓ ${ticker} added to portfolio`);
      setTimeout(() => setActionMsg(""), 2000);
    } catch (e) {
      setActionMsg(`Failed to add ${ticker}`);
    }
  };

  const SortIcon = ({ field }) => (
    <span style={{ marginLeft: "4px", opacity: sortBy === field ? 1 : 0.3, fontSize: "10px" }}>
      {sortBy === field && sortDir === "desc" ? "▼" : "▲"}
    </span>
  );

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px" }}>
        <div>
          <h2 style={{ fontSize: "24px", fontWeight: 700, color: "var(--color-text-primary)" }}>
            Stock Screener
          </h2>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
            Browse {stocks.length} NSE-listed stocks
          </p>
        </div>
        {actionMsg && (
          <div style={{
            padding: "8px 16px", borderRadius: "8px", fontSize: "13px", fontWeight: 500,
            background: "rgba(16,185,129,0.15)", color: "var(--color-accent-green)",
          }}>{actionMsg}</div>
        )}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "20px", flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: 1, minWidth: "200px" }}>
          <input
            type="text"
            placeholder="Search by ticker or company name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: "100%", padding: "10px 16px 10px 40px", borderRadius: "12px",
              fontSize: "13px", border: "1px solid var(--border-subtle)", outline: "none",
              background: "var(--color-bg-card)", color: "var(--color-text-primary)",
            }}
          />
          <svg style={{ position: "absolute", left: "14px", top: "50%", transform: "translateY(-50%)", width: "16px", height: "16px", color: "var(--color-text-muted)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <select
          value={selectedSector}
          onChange={(e) => setSelectedSector(e.target.value)}
          style={{
            padding: "10px 16px", borderRadius: "12px", fontSize: "13px",
            border: "1px solid var(--border-subtle)", outline: "none",
            background: "var(--color-bg-card)", color: "var(--color-text-primary)",
            minWidth: "180px", cursor: "pointer",
          }}
        >
          <option value="">All Sectors</option>
          {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="glass-card" style={{ overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                {[
                  { key: "ticker", label: "Ticker" },
                  { key: "name", label: "Company" },
                  { key: "sector", label: "Sector" },
                  { key: "current_price", label: "Price" },
                  { key: "change_percent", label: "Change" },
                ].map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    style={{
                      padding: "14px 16px", textAlign: "left", fontWeight: 600,
                      color: "var(--color-text-muted)", cursor: "pointer",
                      textTransform: "uppercase", fontSize: "10px", letterSpacing: "0.05em",
                      userSelect: "none",
                    }}
                  >
                    {col.label}<SortIcon field={col.key} />
                  </th>
                ))}
                <th style={{ padding: "14px 16px", textAlign: "right", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", fontSize: "10px", letterSpacing: "0.05em" }}>
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <td key={j} style={{ padding: "14px 16px" }}>
                        <div className="shimmer" style={{ height: "16px", borderRadius: "4px", width: j === 1 ? "160px" : "80px" }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : sortedStocks.map((stock) => {
                const isPos = stock.change_percent >= 0;
                return (
                  <tr key={stock.ticker}
                    style={{ borderBottom: "1px solid var(--border-subtle)", transition: "background 0.2s", cursor: "pointer" }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "rgba(99,102,241,0.05)"}
                    onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                    onClick={() => onNavigate?.("company", stock.ticker)}
                  >
                    <td style={{ padding: "14px 16px", fontWeight: 600, color: "var(--color-text-primary)" }}>
                      {stock.ticker}
                    </td>
                    <td style={{ padding: "14px 16px", color: "var(--color-text-secondary)" }}>
                      {stock.name}
                    </td>
                    <td style={{ padding: "14px 16px" }}>
                      <span style={{
                        padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontWeight: 500,
                        background: "rgba(99,102,241,0.1)", color: "var(--color-accent-secondary)",
                      }}>{stock.sector}</span>
                    </td>
                    <td style={{ padding: "14px 16px", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>
                      {stock.current_price > 0 ? `₹${stock.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                    </td>
                    <td style={{ padding: "14px 16px", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: isPos ? "var(--color-accent-green)" : "var(--color-accent-red)" }}>
                      {stock.current_price > 0 ? `${isPos ? "+" : ""}${stock.change_percent.toFixed(2)}%` : "—"}
                    </td>
                    <td style={{ padding: "14px 16px", textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end" }}>
                        <button onClick={() => addToWatchlist(stock.ticker)}
                          style={{ padding: "4px 10px", borderRadius: "6px", fontSize: "11px", fontWeight: 500, border: "1px solid var(--border-subtle)", background: "transparent", color: "var(--color-accent-amber)", cursor: "pointer" }}
                        >⭐ Watch</button>
                        <button onClick={() => addToPortfolio(stock.ticker, stock.current_price)}
                          style={{ padding: "4px 10px", borderRadius: "6px", fontSize: "11px", fontWeight: 500, border: "none", background: "rgba(99,102,241,0.2)", color: "var(--color-accent-secondary)", cursor: "pointer" }}
                        >+ Portfolio</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!loading && sortedStocks.length === 0 && (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--color-text-muted)" }}>
            No stocks found matching your query.
          </div>
        )}
      </div>
    </div>
  );
}
