"use client";

/* Hallmark · genre: editorial (dark palette preserved from the live app,
 * not a catalog light-paper pick — see globals.css's own "editorial
 * terminal" header comment) · macrostructure: Narrative Workflow
 * · theme: preserved (near-black surfaces #0a0a0c, indigo accent #6366f1,
 * Inter body / Georgia-stack display / mono numerals — all pre-existing
 * tokens, none redeclared) · enrichment: E5 hand-built pipeline diagram
 * (Tier A/B SVG+CSS, PipelineDiagram.jsx — no fabricated screenshot; one
 * animated stroke-dashoffset flow via @property, everything else static)
 * · nav: N9 edge-aligned minimal · footer: Ft2 inline single line
 * pre-emit critique: P5 H5 E5 S5 R4 V4
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./context/AuthContext";
import MarketsTicker from "./components/landing/MarketsTicker";
import LandingNav from "./components/landing/LandingNav";
import Hero from "./components/landing/Hero";
import Problem from "./components/landing/Problem";
import HowItWorks from "./components/landing/HowItWorks";
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
    <div style={{ background: "var(--color-bg-primary)", minHeight: "100vh" }}>
      <MarketsTicker />
      <LandingNav />
      <main>
        <Hero />
        <Problem />
        <HowItWorks />
        <TrackRecord />
        <CTASection />
        <ComplianceSection />
      </main>
      <LandingFooter />
    </div>
  );
}
