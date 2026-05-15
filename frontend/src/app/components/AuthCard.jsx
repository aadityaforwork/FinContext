"use client";

/**
 * AuthCard — shared shell for /login, /signup, /forgot-password, /reset-password.
 *
 * "Editorial terminal" aesthetic to match the dashboard:
 *   - solid surfaces, no radial-gradient backdrops
 *   - flat monogram (matches Sidebar) — no gradient block
 *   - hairline borders, 12px card / 8px control radius
 *   - solid accent CTA, no two-stop gradient
 */
export default function AuthCard({ title, subtitle, children }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background: "var(--color-bg-primary)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card, 12px)",
          padding: "28px",
        }}
      >
        {/* Brand — flat monogram, matches Sidebar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "11px",
            marginBottom: "26px",
            paddingBottom: "20px",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <div
            style={{
              width: "30px",
              height: "30px",
              borderRadius: "7px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-text-primary)",
              fontWeight: 700,
              fontSize: "15px",
              flexShrink: 0,
              background: "var(--color-bg-card-hover)",
              border: "1px solid var(--border-strong)",
              letterSpacing: "-0.03em",
            }}
          >
            F
          </div>
          <div style={{ lineHeight: 1.25 }}>
            <h1
              style={{
                fontSize: "14px",
                fontWeight: 700,
                color: "var(--color-text-primary)",
                letterSpacing: "-0.02em",
              }}
            >
              FinContext
            </h1>
            <p
              style={{
                fontSize: "10.5px",
                color: "var(--color-text-muted)",
                letterSpacing: "0.01em",
              }}
            >
              Market intelligence
            </p>
          </div>
        </div>

        <h2
          style={{
            fontSize: "20px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            marginBottom: "6px",
            letterSpacing: "-0.01em",
          }}
        >
          {title}
        </h2>
        {subtitle ? (
          <p
            style={{
              fontSize: "13px",
              color: "var(--color-text-secondary)",
              marginBottom: "22px",
              lineHeight: 1.5,
            }}
          >
            {subtitle}
          </p>
        ) : (
          <div style={{ marginBottom: "16px" }} />
        )}

        {children}
      </div>
    </div>
  );
}

// Inputs — hairline border, slightly recessed surface, focus is the global
// :focus-visible ring from globals.css so we stay consistent with the dashboard.
export const authInputStyle = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "var(--radius-control, 8px)",
  border: "1px solid var(--border-subtle)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text-primary)",
  fontSize: "13.5px",
  outline: "none",
};

// Primary CTA — solid accent, no gradient. Matches the Run/Refresh buttons
// across the dashboard for visual consistency.
export const authButtonStyle = {
  width: "100%",
  padding: "11px 16px",
  borderRadius: "var(--radius-control, 8px)",
  border: "1px solid var(--color-accent-primary)",
  cursor: "pointer",
  fontSize: "13.5px",
  fontWeight: 600,
  color: "#fff",
  background: "var(--color-accent-primary)",
  transition: "filter 0.15s, opacity 0.15s",
  letterSpacing: "0.01em",
};

// Secondary CTA (used for the Google button when re-enabled) — hairline outline.
export const authGoogleButtonStyle = {
  width: "100%",
  padding: "10px 16px",
  borderRadius: "var(--radius-control, 8px)",
  border: "1px solid var(--border-subtle)",
  background: "var(--color-bg-card)",
  color: "var(--color-text-primary)",
  fontSize: "13.5px",
  fontWeight: 600,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "10px",
  transition: "border-color 0.15s, background 0.15s",
};

export function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961l3.007 2.332C4.672 5.166 6.656 3.58 9 3.58z"
      />
    </svg>
  );
}
