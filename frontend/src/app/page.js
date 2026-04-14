"use client";

import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import DashboardHeader from "./components/DashboardHeader";
import WatchlistCard from "./components/WatchlistCard";
import StockChart from "./components/StockChart";
import ContextPanel from "./components/ContextPanel";
import ScreenerView from "./components/ScreenerView";
import WatchlistView from "./components/WatchlistView";
import PortfolioView from "./components/PortfolioView";
import AnalysisView from "./components/AnalysisView";
import CompanyView from "./components/CompanyView";
import GlobeNewsSection from "./components/GlobeNewsSection";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function App() {
  const [activeNav, setActiveNav] = useState("dashboard");
  const [analysisTicker, setAnalysisTicker] = useState(null);
  const [companyTicker, setCompanyTicker] = useState(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const nav = params.get("nav");
      if (nav) setActiveNav(nav);
      
      const success = params.get("success");
      const error = params.get("error");
      if (success) setTimeout(() => alert("Successfully synced!"), 500);
      if (error) setTimeout(() => alert("Sync failed: " + error), 500);
    }
  }, []);

  // Navigation handler used by child components
  const handleNavigate = (page, ticker) => {
    setActiveNav(page);
    if (page === "analysis" && ticker) setAnalysisTicker(ticker);
    if (page === "company" && ticker) setCompanyTicker(ticker);
  };

  return (
    <div className="app-shell">
      <Sidebar activeNav={activeNav} onNavChange={(nav) => { setActiveNav(nav); setAnalysisTicker(null); setCompanyTicker(null); }} />

      <main className="main-content">
        <DashboardHeader onSearch={(q) => { setActiveNav("screener"); }} />

        <div className="content-area">
          {activeNav === "dashboard" && <DashboardView onNavigate={handleNavigate} />}
          {activeNav === "screener" && <ScreenerView onNavigate={handleNavigate} />}
          {activeNav === "watchlist" && <WatchlistView onNavigate={handleNavigate} />}
          {activeNav === "portfolio" && <PortfolioView onNavigate={handleNavigate} />}
          {activeNav === "analysis" && <AnalysisView initialTicker={analysisTicker} />}
          {activeNav === "company" && <CompanyView ticker={companyTicker} onNavigate={handleNavigate} />}
        </div>
      </main>
    </div>
  );
}

// -----------------------------------------------------------------------
// Dashboard View (the original home page content)
// -----------------------------------------------------------------------
function DashboardView({ onNavigate }) {
  const [stocks, setStocks] = useState([]);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [loading, setLoading] = useState(true);
  const [indices, setIndices] = useState([
    { label: "NIFTY 50", value: "—", change: "—", positive: true },
    { label: "SENSEX", value: "—", change: "—", positive: true },
    { label: "NIFTY MIDCAP", value: "—", change: "—", positive: false },
    { label: "INR/USD", value: "—", change: "—", positive: false },
  ]);

  useEffect(() => {
    fetch(`${API_BASE}/api/watchlist/`)
      .then((r) => r.json())
      .then((data) => { setStocks(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/market/indices`)
      .then((r) => r.json())
      .then((data) => { if (data && data.length) setIndices(data); })
      .catch(() => {});
  }, []);

  const selectedStock = stocks.find((s) => s.ticker === selectedTicker);

  return (
    <>
      {/* Market Overview Cards */}
      <div className="responsive-grid-4" style={{ marginBottom: "24px" }}>
        {indices.map((idx) => (
          <div key={idx.label} className="glass-card" style={{ padding: "16px" }}>
            <p style={{ fontSize: "10px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)" }}>{idx.label}</p>
            <p style={{ fontSize: "20px", fontWeight: 700, marginTop: "4px", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>{idx.value}</p>
            <p style={{ fontSize: "12px", fontWeight: 600, marginTop: "2px", fontVariantNumeric: "tabular-nums", color: idx.positive ? "var(--color-accent-green)" : "var(--color-accent-red)" }}>{idx.change}</p>
          </div>
        ))}
      </div>

      {/* Global Intelligence Globe */}
      <GlobeNewsSection />

      {/* Main Grid */}
      <div className="responsive-grid-sidebar">
        {/* Watchlist */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
            <h3 style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)" }}>Your Watchlist</h3>
            <span style={{ fontSize: "12px", padding: "2px 8px", borderRadius: "9999px", background: "rgba(99,102,241,0.1)", color: "var(--color-accent-secondary)" }}>{stocks.length} stocks</span>
          </div>

          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {[1, 2, 3, 4, 5].map((i) => <div key={i} className="shimmer" style={{ height: "80px", borderRadius: "16px" }} />)}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {stocks.map((stock) => (
                <WatchlistCard key={stock.ticker} stock={stock}
                  isSelected={selectedTicker === stock.ticker}
                  onClick={() => setSelectedTicker(stock.ticker)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right: Chart + Context */}
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <StockChart ticker={selectedTicker} stockName={selectedStock?.name} />
          <ContextPanel ticker={selectedTicker} stockName={selectedStock?.name} />
        </div>
      </div>
    </>
  );
}
