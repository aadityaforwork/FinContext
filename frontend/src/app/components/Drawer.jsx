"use client";

import { useEffect } from "react";

/**
 * Reusable side drawer. Slides in from the right, dims the page underneath.
 * Closes on Escape, click outside, or the × button.
 *
 * Props:
 *   open      — boolean, drawer visibility
 *   onClose   — callback
 *   title     — string (drawer header)
 *   subtitle  — optional one-liner under the title
 *   actions   — optional element rendered to the right of the header
 *   width     — CSS width (default: min(640px, 92vw))
 *   children  — drawer body
 */
export default function Drawer({
  open,
  onClose,
  title,
  subtitle,
  actions,
  width = "min(640px, 92vw)",
  children,
}) {
  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Lock body scroll while drawer is open (prevents page scrolling behind)
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(10,14,23,0.65)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
        zIndex: 1000,
        display: "flex",
        justifyContent: "flex-end",
        animation: "fc-drawer-fade 0.18s ease-out",
      }}
    >
      <style>{`
        @keyframes fc-drawer-fade { from { opacity: 0 } to { opacity: 1 } }
        @keyframes fc-drawer-slide { from { transform: translateX(40px); opacity: 0 } to { transform: translateX(0); opacity: 1 } }
      `}</style>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width,
          maxWidth: "100vw",
          height: "100vh",
          background: "var(--color-bg-primary)",
          borderLeft: "1px solid var(--border-subtle)",
          display: "flex",
          flexDirection: "column",
          boxShadow: "-12px 0 40px rgba(0,0,0,0.4)",
          animation: "fc-drawer-slide 0.22s ease-out",
        }}
      >
        {/* HEADER */}
        <header
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "12px",
            padding: "16px 20px",
            borderBottom: "1px solid var(--border-subtle)",
            flexShrink: 0,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <h2
              style={{
                fontSize: "15px",
                fontWeight: 800,
                color: "var(--color-text-primary)",
                letterSpacing: "-0.01em",
                marginBottom: subtitle ? "3px" : 0,
              }}
            >
              {title}
            </h2>
            {subtitle && (
              <p style={{ fontSize: "12px", color: "var(--color-text-muted)", lineHeight: 1.4 }}>
                {subtitle}
              </p>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", flexShrink: 0 }}>
            {actions}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              style={{
                width: "28px",
                height: "28px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
                background: "var(--color-bg-card)",
                color: "var(--color-text-secondary)",
                cursor: "pointer",
                fontSize: "16px",
                lineHeight: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              ×
            </button>
          </div>
        </header>

        {/* BODY — caller handles scroll inside */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px 20px" }}>
          {children}
        </div>
      </div>
    </div>
  );
}
