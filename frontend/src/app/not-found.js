import Link from "next/link";

export const metadata = {
  title: "Page not found — FinContext",
};

export default function NotFound() {
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
          maxWidth: "460px",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "20px",
          padding: "36px",
          boxShadow: "var(--shadow-card)",
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: "44px",
            height: "44px",
            borderRadius: "12px",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontWeight: 700,
            fontSize: "20px",
            background:
              "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
            marginBottom: "20px",
          }}
        >
          F
        </div>

        <p
          className="gradient-text"
          style={{ fontSize: "56px", fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1 }}
        >
          404
        </p>
        <h1
          style={{
            fontSize: "20px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            marginTop: "12px",
          }}
        >
          We can't find that page
        </h1>
        <p
          style={{
            fontSize: "14px",
            color: "var(--color-text-secondary)",
            marginTop: "8px",
            lineHeight: 1.5,
          }}
        >
          The link may be outdated, or the page was moved. Let's get you back to your dashboard.
        </p>

        <Link
          href="/"
          style={{
            display: "inline-block",
            marginTop: "24px",
            padding: "11px 22px",
            borderRadius: "10px",
            fontSize: "14px",
            fontWeight: 600,
            color: "white",
            textDecoration: "none",
            background:
              "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-secondary))",
          }}
        >
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
