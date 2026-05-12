"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";

/**
 * Modal
 * -----
 * Shared overlay shell used by every click-through detail popup
 * (MoverDetailModal, WatchItemDetailModal, ThemeDetailModal, NewsDetailModal).
 *
 * Two important properties:
 *
 * 1. Renders via createPortal to document.body so the modal escapes any
 *    ancestor stacking context. Several parent containers in this app use
 *    transform/filter for animations (`animate-fade-in`, `glass-card`) which
 *    silently override `position: fixed` — the modal would otherwise be
 *    fixed to the card instead of the viewport.
 *
 * 2. Locks document.body scroll while open so the page underneath doesn't
 *    scroll along with the modal's internal scroll.
 *
 * Props:
 *   onClose   — called on ESC, overlay click, or × button
 *   header    — JSX for the modal header (left of close button)
 *   children  — modal body
 *   maxWidth  — px, default 720
 */
export default function Modal({ onClose, header, children, maxWidth = 720 }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        padding: "24px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--color-bg-secondary, #11131c)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "14px",
          width: `min(${maxWidth}px, 100%)`,
          maxHeight: "85vh",
          overflowY: "auto",
          padding: "22px 24px",
          boxShadow: "0 20px 60px rgba(0,0,0,0.45)",
        }}
      >
        {header !== undefined && (
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "12px",
            marginBottom: "14px",
          }}>
            <div style={{ minWidth: 0, flex: 1 }}>{header}</div>
            <button
              onClick={onClose}
              aria-label="Close"
              style={{
                background: "transparent",
                border: "1px solid var(--border-subtle)",
                color: "var(--color-text-muted)",
                width: "32px",
                height: "32px",
                borderRadius: "8px",
                cursor: "pointer",
                fontSize: "16px",
                lineHeight: 1,
                flexShrink: 0,
              }}
            >
              ×
            </button>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body,
  );
}
