"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

const ToastContext = createContext(null);

const VARIANT_STYLES = {
  success: {
    accent: "var(--color-accent-green)",
    bg: "rgba(16, 185, 129, 0.10)",
    border: "rgba(16, 185, 129, 0.30)",
    icon: "✓",
  },
  error: {
    accent: "var(--color-accent-red)",
    bg: "rgba(239, 68, 68, 0.10)",
    border: "rgba(239, 68, 68, 0.30)",
    icon: "!",
  },
  info: {
    accent: "var(--color-accent-secondary)",
    bg: "rgba(99, 102, 241, 0.10)",
    border: "rgba(99, 102, 241, 0.30)",
    icon: "i",
  },
};

let nextId = 1;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message, variant = "info", { duration = 4000 } = {}) => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, message, variant }]);
      if (duration > 0) {
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== id));
        }, duration);
      }
      return id;
    },
    []
  );

  const value = {
    success: (m, opts) => push(m, "success", opts),
    error: (m, opts) => push(m, "error", opts),
    info: (m, opts) => push(m, "info", opts),
    dismiss,
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        style={{
          position: "fixed",
          top: "20px",
          right: "20px",
          zIndex: 9999,
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          maxWidth: "calc(100vw - 40px)",
          width: "360px",
          pointerEvents: "none",
        }}
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }) {
  const v = VARIANT_STYLES[toast.variant] || VARIANT_STYLES.info;
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const t = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(t);
  }, []);

  return (
    <div
      role="status"
      style={{
        pointerEvents: "auto",
        background: "var(--color-bg-card)",
        border: `1px solid ${v.border}`,
        borderRadius: "12px",
        padding: "12px 14px",
        boxShadow: "var(--shadow-card)",
        display: "flex",
        alignItems: "flex-start",
        gap: "12px",
        opacity: entered ? 1 : 0,
        transform: entered ? "translateX(0)" : "translateX(20px)",
        transition: "opacity 0.2s ease-out, transform 0.2s ease-out",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div
        style={{
          flexShrink: 0,
          width: "22px",
          height: "22px",
          borderRadius: "50%",
          background: v.bg,
          color: v.accent,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "13px",
          fontWeight: 700,
          marginTop: "1px",
        }}
      >
        {v.icon}
      </div>
      <div
        style={{
          flex: 1,
          fontSize: "13px",
          lineHeight: 1.45,
          color: "var(--color-text-primary)",
        }}
      >
        {toast.message}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        style={{
          flexShrink: 0,
          background: "transparent",
          border: "none",
          color: "var(--color-text-muted)",
          cursor: "pointer",
          fontSize: "16px",
          lineHeight: 1,
          padding: "2px 4px",
          borderRadius: "4px",
        }}
      >
        ×
      </button>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Soft fallback — never crash a page just because the provider isn't mounted.
    return {
      success: (m) => console.info("[toast]", m),
      error: (m) => console.error("[toast]", m),
      info: (m) => console.info("[toast]", m),
      dismiss: () => {},
    };
  }
  return ctx;
}
