"use client";

export default function AuthCard({ title, subtitle, children }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background:
          "radial-gradient(1200px 600px at 50% -10%, rgba(99,102,241,0.12), transparent 70%), var(--color-bg-primary)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "20px",
          padding: "32px",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
          <div
            style={{
              width: "40px",
              height: "40px",
              borderRadius: "12px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontWeight: 700,
              fontSize: "18px",
              background:
                "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
            }}
          >
            F
          </div>
          <div>
            <h1 style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>
              FinContext
            </h1>
            <p style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>
              Market Intelligence
            </p>
          </div>
        </div>

        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            marginBottom: "6px",
          }}
        >
          {title}
        </h2>
        {subtitle ? (
          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "20px" }}>
            {subtitle}
          </p>
        ) : (
          <div style={{ marginBottom: "12px" }} />
        )}

        {children}
      </div>
    </div>
  );
}

export const authInputStyle = {
  width: "100%",
  padding: "10px 14px",
  borderRadius: "10px",
  border: "1px solid var(--border-subtle)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text-primary)",
  fontSize: "14px",
  outline: "none",
};

export const authButtonStyle = {
  width: "100%",
  padding: "11px 16px",
  borderRadius: "10px",
  border: "none",
  cursor: "pointer",
  fontSize: "14px",
  fontWeight: 600,
  color: "white",
  background:
    "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-secondary))",
  transition: "opacity 0.15s",
};

export const authGoogleButtonStyle = {
  width: "100%",
  padding: "10px 16px",
  borderRadius: "10px",
  border: "1px solid var(--border-subtle)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text-primary)",
  fontSize: "14px",
  fontWeight: 600,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "10px",
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
