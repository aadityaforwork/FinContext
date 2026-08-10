"use client";

/* Hallmark · genre: editorial (dark palette preserved from the live app,
 * not a catalog light-paper pick — see globals.css's own "editorial
 * terminal" header comment) · macrostructure: Narrative Workflow
 * · theme: preserved (near-black surfaces #0a0a0c, indigo accent #6366f1,
 * Inter body / Georgia-stack display / mono numerals — all pre-existing
 * tokens, none redeclared) · enrichment: E5 hand-built pipeline diagram
 * (Tier A/B SVG+CSS, PipelineDiagram.jsx — no fabricated screenshot; one
 * animated stroke-dashoffset flow via @property, everything else static)
 * · nav: N12 banner + retracting bar (knobs: fill=tint+ink, dismiss=yes,
 * bar-scroll=sticky, content=promo) · footer: Ft1 mast-headed (knobs:
 * wordmark=xl, tagline=roman body, links=two clusters)
 * · new sections: ContextLayer (S2 hanging head) · MCPSection (F3 tabular
 * spec sheet, knobs: columns=3, rules=every row, numbers=tabular)
 * pre-emit critique: P5 H5 E5 S5 R4 V4
 *
 * Rev 2 (MCP + premium pass): nav rotated N9 → N12 and footer Ft2 → Ft1 per
 * the diversification rule — N9's "empty space is the design" premise stops
 * holding once the page has four in-page destinations. N6 masthead was the
 * editorial default and was rejected: its own spec bans it on product /
 * developer-tool pages, where it reads as costume. Macrostructure kept —
 * the four-stage narrative is earned by the actual pipeline, so rotating it
 * would have been change for its own sake.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./context/AuthContext";
import MarketsTicker from "./components/landing/MarketsTicker";
import LandingNav from "./components/landing/LandingNav";
import Hero from "./components/landing/Hero";
import Problem from "./components/landing/Problem";
import HowItWorks from "./components/landing/HowItWorks";
import ContextLayer from "./components/landing/ContextLayer";
import MCPSection from "./components/landing/MCPSection";
import TrackRecord from "./components/landing/TrackRecord";
import ComplianceSection from "./components/landing/ComplianceSection";
import CTASection from "./components/landing/CTASection";
import LandingFooter from "./components/landing/LandingFooter";

/**
 * `/` — the public marketing landing page. Was the dashboard shell until
 * this build; the dashboard now lives at /dashboard (see AGENTS.md /
 * STRATEGY.md's "landing page rewritten" item). Signed-in visitors are
 * bounced straight to /dashboard, mirroring the same guard already used
 * on /login and /signup.
 */
export default function LandingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  return (
    <div className="landing-page">
      {/* Header is fixed (N12) — the ticker sits below it, in normal flow.
          It's live data, not chrome, so it belongs with the content. */}
      <LandingNav />
      <MarketsTicker />
      <main>
        <Hero />
        <Problem />
        <HowItWorks />
        <ContextLayer />
        <MCPSection />
        <TrackRecord />
        <CTASection />
        <ComplianceSection />
      </main>
      <LandingFooter />
    </div>
  );
}
