"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "./components/Sidebar";
import DashboardHeader from "./components/DashboardHeader";
import ScreenerView from "./components/ScreenerView";
import WatchlistView from "./components/WatchlistView";
import PortfolioView from "./components/PortfolioView";
import AnalysisView from "./components/AnalysisView";
import CompanyView from "./components/CompanyView";
import PortfolioTodayStrip from "./components/PortfolioTodayStrip";
import MarketBriefStrip from "./components/MarketBriefStrip";
import NewsImpactFeed from "./components/NewsImpactFeed";
import UniverseRail from "./components/UniverseRail";
import WatchlistDrawer from "./components/WatchlistDrawer";
import ScreenerDrawer from "./components/ScreenerDrawer";
import SettingsView from "./components/SettingsView";
import { useAuth } from "./context/AuthContext";
import { supabase } from "./lib/supabase";
import { useToast } from "./components/Toast";
import BrandedSplash from "./components/BrandedSplash";
import ComplianceFooter from "./components/ComplianceFooter";

export default function App() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [activeNav, setActiveNav] = useState("dashboard");
  const [analysisTicker, setAnalysisTicker] = useState(null);
  const [companyTicker, setCompanyTicker] = useState(null);
  // Drawer state for the hub-and-drawer model. Only one drawer open at a time.
  const [drawer, setDrawer] = useState(null); // "watchlist" | "screener" | null

  // Redirect unauthenticated users to /login
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const nav = params.get("nav");
    if (nav) setActiveNav(nav);

    const error = params.get("error");
    if (error) setTimeout(() => toast.error(decodeURIComponent(error.replace(/_/g, " "))), 500);

    // Handle Zerodha import: positions arrive as base64 JSON in query param.
    // Kite is source of truth — replace the current user's snapshot entirely so sells in Kite are reflected.
    const zerodhaImport = params.get("zerodha_import");
    if (zerodhaImport && user?.id) {
      (async () => {
        try {
          const positions = JSON.parse(atob(zerodhaImport));
          // Scope delete to current user — never run a global delete.
          await supabase.from("portfolio").delete().eq("user_id", user.id);
          for (const pos of positions) {
            await supabase.from("portfolio").upsert(
              { ticker: pos.ticker, quantity: pos.quantity, buy_price: pos.buy_price, user_id: user.id },
              { onConflict: "ticker,user_id", ignoreDuplicates: false }
            );
          }
          setTimeout(
            () => toast.success(`Synced ${positions.length} positions from Zerodha`),
            300
          );
        } catch (e) {
          console.warn("Zerodha import failed:", e?.message || e);
          toast.error("Could not sync positions from Zerodha.");
        }
        // Clean up URL
        window.history.replaceState({}, "", "/");
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  // Navigation handler used by child components
  const handleNavigate = (page, ticker) => {
    setActiveNav(page);
    if (page === "analysis" && ticker) setAnalysisTicker(ticker);
    if (page === "company" && ticker) setCompanyTicker(ticker);
  };

  if (loading || !user) {
    return <BrandedSplash />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        activeNav={activeNav}
        onNavChange={(nav) => {
          setActiveNav(nav);
          setAnalysisTicker(null);
          setCompanyTicker(null);
        }}
      />

      <main className="main-content">
        <DashboardHeader
          onSearch={() => setActiveNav("screener")}
          user={user}
          onLogout={logout}
        />

        <div className="content-area">
          {activeNav === "dashboard" && (
            <DashboardView
              onNavigate={handleNavigate}
              onOpenWatchlist={() => setDrawer("watchlist")}
              onOpenScreener={() => setDrawer("screener")}
            />
          )}
          {activeNav === "settings"  && <SettingsView />}
          {/* Full-page views reached via dashboard CTAs or ticker clicks */}
          {activeNav === "screener"  && <ScreenerView onNavigate={handleNavigate} />}
          {activeNav === "watchlist" && <WatchlistView onNavigate={handleNavigate} />}
          {activeNav === "portfolio" && <PortfolioView onNavigate={handleNavigate} />}
          {activeNav === "analysis"  && <AnalysisView initialTicker={analysisTicker} />}
          {activeNav === "company"   && <CompanyView ticker={companyTicker} onNavigate={handleNavigate} />}
        </div>

        {/* Dashboard handles its own disclaimer per-pane; other views show the footer. */}
        {activeNav !== "dashboard" && <ComplianceFooter />}
      </main>

      {/* Drawers — rendered at app root so they overlay everything */}
      <WatchlistDrawer
        open={drawer === "watchlist"}
        onClose={() => setDrawer(null)}
        onNavigate={handleNavigate}
        onOpenScreener={() => setDrawer("screener")}
      />
      <ScreenerDrawer
        open={drawer === "screener"}
        onClose={() => setDrawer(null)}
        onNavigate={handleNavigate}
      />
    </div>
  );
}

// -----------------------------------------------------------------------
// Dashboard View — News → Portfolio Impact (the USP)
// -----------------------------------------------------------------------
// Two zones:
//   1. PortfolioTodayStrip   — your P&L at-a-glance, the proof of personalization
//   2. NewsImpactFeed (left) + UniverseRail (right) — the news stream where every
//      headline is annotated with which of YOUR stocks it touches and why
//
// Everything else (Globe, Screener, Deep Dive Agent, valuation simulator) is
// accessible via sidebar nav — they don't crowd the dashboard anymore.
// -----------------------------------------------------------------------
function DashboardView({ onNavigate, onOpenWatchlist, onOpenScreener }) {
  return (
    <div className="dashboard-shell">
      <PortfolioTodayStrip onNavigate={onNavigate} />
      <MarketBriefStrip onNavigate={onNavigate} />
      <div className="dashboard-main">
        <div className="dashboard-pane">
          <NewsImpactFeed onNavigate={onNavigate} />
        </div>
        <div className="dashboard-pane">
          <UniverseRail
            onNavigate={onNavigate}
            onOpenWatchlist={onOpenWatchlist}
            onOpenScreener={onOpenScreener}
            onOpenPortfolio={() => onNavigate("portfolio")}
          />
        </div>
      </div>
      <p
        style={{
          fontSize: "10px",
          color: "var(--color-text-muted)",
          textAlign: "center",
          fontStyle: "italic",
          margin: "2px 0 0",
        }}
      >
        Educational only — not investment advice. Not a SEBI-registered RA.
      </p>
    </div>
  );
}
