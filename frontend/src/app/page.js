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
import AccuracyView from "./components/AccuracyView";
import OnboardingModal, {
  shouldShowOnboarding,
  consumePendingFirstInsight,
  consumePendingTour,
} from "./components/OnboardingModal";
import FirstInsightCard from "./components/FirstInsightCard";
import OnboardingTour from "./components/OnboardingTour";
import PreTradeCheckModal from "./components/PreTradeCheckModal";
import { useAuth } from "./context/AuthContext";
import { supabase } from "./lib/supabase";
import { useToast } from "./components/Toast";
import BrandedSplash from "./components/BrandedSplash";
import ComplianceFooter from "./components/ComplianceFooter";
import { prewarmIntelligence } from "./lib/prewarm";

export default function App() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [activeNav, setActiveNav] = useState("dashboard");
  const [analysisTicker, setAnalysisTicker] = useState(null);
  const [companyTicker, setCompanyTicker] = useState(null);
  // Lightweight nav history — only stores the page the user was on before
  // jumping into a stock-detail view (analysis / company). Powers the "← Back"
  // affordance on those pages without a full router.
  const [prevNav, setPrevNav] = useState(null);
  // Pre-Trade Check modal — the muscle-memory "before you click buy" surface.
  // null = closed; ticker string = open with that ticker.
  const [preTradeTicker, setPreTradeTicker] = useState(null);
  // Drawer state for the hub-and-drawer model. Only one drawer open at a time.
  const [drawer, setDrawer] = useState(null); // "watchlist" | "screener" | null
  // First-run onboarding modal (shown to new users with empty universe).
  const [showOnboarding, setShowOnboarding] = useState(false);
  // Act 2 of onboarding — the FirstInsightCard interstitial. Holds the
  // tickers the user just picked so the card can fetch a personalized
  // insight before the user lands on the dashboard.
  const [firstInsightTickers, setFirstInsightTickers] = useState(null);
  // Act 3 — bump the OnboardingTour any time onboarding completes so it
  // re-evaluates its localStorage flag and surfaces the callouts.
  const [tourTrigger, setTourTrigger] = useState(0);

  // Redirect unauthenticated users to /login
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  // First-run detection: brand-new users (empty portfolio + empty watchlist,
  // no localStorage flag) get the onboarding modal. Don't block render — let
  // the dashboard load with demo data, then overlay the modal.
  //
  // Storage is per-user (see OnboardingModal.shouldShowOnboarding) so a
  // second account on the same browser still sees onboarding. This was the
  // "nothing happens on signup" bug.
  useEffect(() => {
    if (!user?.id) return;
    let cancelled = false;

    // Consume the post-wizard sessionStorage flags FIRST. If we just
    // reloaded out of the wizard, open the FirstInsightCard immediately so
    // the dashboard underneath is the freshly-loaded one with new data.
    const pendingTickers = consumePendingFirstInsight();
    if (pendingTickers && pendingTickers.length > 0) {
      setFirstInsightTickers(pendingTickers);
      return;   // skip the empty-portfolio check — they just onboarded
    }

    (async () => {
      try {
        const [{ data: portfolio }, { data: watch }] = await Promise.all([
          supabase.from("portfolio").select("ticker").eq("user_id", user.id).limit(1),
          supabase.from("watchlist").select("ticker").eq("user_id", user.id).limit(1),
        ]);
        if (cancelled) return;
        if (
          shouldShowOnboarding({
            hasPortfolio: (portfolio?.length || 0) > 0,
            hasWatchlist: (watch?.length || 0) > 0,
            userId: user.id,
          })
        ) {
          setShowOnboarding(true);
        }
      } catch {
        // Silent — onboarding is a nice-to-have, not a blocker.
      }
    })();
    return () => { cancelled = true; };
  }, [user?.id]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const nav = params.get("nav");
    if (nav) setActiveNav(nav);

    // ?tour=1 in the URL means Settings → Replay tour just navigated us
    // here. Bump trigger so the (otherwise-dormant) tour fires once.
    if (params.get("tour") === "1") {
      setTourTrigger((n) => n + 1);
      // Clean the URL so a manual refresh doesn't re-trigger.
      const cleaned = new URL(window.location.href);
      cleaned.searchParams.delete("tour");
      window.history.replaceState({}, "", cleaned.toString());
    }

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
          // Fire-and-forget: warm the backend cache for news-feed + movers so
          // the user's first dashboard paint isn't a cold LLM round-trip.
          // Pull current watchlist so prewarm sees the same context the
          // dashboard will request a few seconds later.
          try {
            const { data: watchRows } = await supabase
              .from("watchlist").select("ticker").eq("user_id", user.id);
            prewarmIntelligence({
              positions,
              watchlistTickers: (watchRows || []).map((r) => r.ticker),
            });
          } catch { /* prewarm is best-effort */ }
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

  // Navigation handler used by child components. Records the previous page
  // before jumping into a stock-detail view so the detail view can render an
  // accurate "← Back to <where>" affordance. Doesn't overwrite prevNav when
  // hopping between two detail views (analysis ↔ company) — we want back to
  // return to the list (portfolio/watchlist/screener) where the journey started.
  const handleNavigate = (page, ticker) => {
    const isDetailPage = page === "analysis" || page === "company";
    const wasDetailPage = activeNav === "analysis" || activeNav === "company";
    if (isDetailPage && !wasDetailPage && activeNav !== page) {
      setPrevNav(activeNav);
    }
    setActiveNav(page);
    if (page === "analysis" && ticker) setAnalysisTicker(ticker);
    if (page === "company"  && ticker) setCompanyTicker(ticker);
  };

  // Pop back to where the user came from. Defaults to dashboard if no history.
  const handleBack = () => {
    const target = prevNav || "dashboard";
    setActiveNav(target);
    setPrevNav(null);
  };

  // Human-readable labels for back-button copy.
  const NAV_LABELS = {
    dashboard: "Dashboard",
    portfolio: "Portfolio",
    watchlist: "Watchlist",
    screener:  "Screener",
    accuracy:  "Accuracy",
    settings:  "Settings",
    analysis:  "Deep dive",
    company:   "Company details",
  };
  const backLabel = NAV_LABELS[prevNav || "dashboard"];

  // ---- Keep-alive view rendering --------------------------------------------
  // Switching tabs used to unmount the previous view, throwing away its state
  // and forcing a re-fetch when the user came back. We now lazy-mount each
  // view on first visit and keep it alive (display:none when inactive) so
  // returning to a tab is instant — no spinner, no reload.
  //
  // `visitedViews` is the set of views ever opened in this session. Unvisited
  // ones render `null` so we don't pre-fetch every panel on page load.
  const [visitedViews, setVisitedViews] = useState(() => new Set(["dashboard"]));
  useEffect(() => {
    setVisitedViews((prev) => {
      if (prev.has(activeNav)) return prev;
      const next = new Set(prev);
      next.add(activeNav);
      return next;
    });
  }, [activeNav]);

  if (loading || !user) {
    return <BrandedSplash />;
  }

  const renderTab = (id, build) => {
    if (!visitedViews.has(id)) return null;
    return (
      <div
        key={id}
        style={{ display: activeNav === id ? "block" : "none" }}
      >
        {build()}
      </div>
    );
  };

  return (
    <div className="app-shell">
      <Sidebar
        activeNav={activeNav}
        onNavChange={(nav) => setActiveNav(nav)}
      />

      <main className="main-content">
        <DashboardHeader
          onSearch={() => setActiveNav("screener")}
          onCheckTicker={(t) => setPreTradeTicker(t)}
          user={user}
          onLogout={logout}
        />

        <div className="content-area">
          {renderTab("dashboard", () => (
            <DashboardView
              onNavigate={handleNavigate}
              onOpenWatchlist={() => setDrawer("watchlist")}
              onOpenScreener={() => setDrawer("screener")}
            />
          ))}
          {renderTab("accuracy",  () => <AccuracyView embedded />)}
          {renderTab("settings",  () => <SettingsView />)}
          {/* Full-page views reached via dashboard CTAs or ticker clicks */}
          {renderTab("screener",  () => <ScreenerView onNavigate={handleNavigate} />)}
          {renderTab("watchlist", () => <WatchlistView onNavigate={handleNavigate} />)}
          {renderTab("portfolio", () => <PortfolioView onNavigate={handleNavigate} />)}
          {renderTab("analysis",  () => <AnalysisView initialTicker={analysisTicker} onBack={handleBack} backLabel={backLabel} onNavigate={handleNavigate} />)}
          {renderTab("company",   () => <CompanyView ticker={companyTicker} onNavigate={handleNavigate} onBack={handleBack} backLabel={backLabel} />)}
        </div>

        {/* Dashboard handles its own disclaimer per-pane; other views show the footer. */}
        {activeNav !== "dashboard" && <ComplianceFooter />}
      </main>

      {/* Pre-Trade Check — modal at app root so it overlays any view.
          Triggered by the header pill (or programmatically elsewhere). */}
      {preTradeTicker && (
        <PreTradeCheckModal
          ticker={preTradeTicker}
          onClose={() => setPreTradeTicker(null)}
          onOpenDeepDive={(t) => handleNavigate("analysis", t)}
        />
      )}

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

      {/* Act 1 — first-run onboarding wizard.
          On complete, the wizard writes sessionStorage flags + reloads.
          We DON'T chain via onComplete here — the next mount picks up the
          flags via consumePendingFirstInsight(). This eliminates the chop
          where the FirstInsightCard appeared over a still-empty dashboard. */}
      <OnboardingModal
        open={showOnboarding}
        onClose={() => setShowOnboarding(false)}
        userName={user?.user_metadata?.name || user?.user_metadata?.full_name || ""}
      />

      {/* Act 2 — single-insight interstitial. Fires either right after a
          fresh reload from the wizard (via sessionStorage handoff above)
          or via direct setFirstInsightTickers in dev/test. */}
      <FirstInsightCard
        open={firstInsightTickers != null}
        tickers={firstInsightTickers || []}
        userId={user?.id}
        onDismiss={() => {
          setFirstInsightTickers(null);
          // Tour only fires if the post-wizard sessionStorage flag was set
          // (i.e. they came in via real onboarding) — not if they hit the
          // card via a dev URL.
          if (consumePendingTour()) {
            setTourTrigger((n) => n + 1);
          }
        }}
      />

      {/* Act 3 — dashboard tour callouts. Anchors to [data-tour=...] on
          the live dashboard. No reload needed — by this point the dashboard
          has been fully loaded since before the FirstInsightCard opened. */}
      <OnboardingTour trigger={tourTrigger} userId={user?.id} />
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
