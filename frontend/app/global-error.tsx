"use client";

// Last-resort boundary: catches errors thrown in the root layout itself
// (where the normal error.tsx cannot mount). Must render its own <html>/<body>.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          background: "#071018",
          color: "#edf3f8",
          fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          margin: 0,
        }}
      >
        <div style={{ maxWidth: 440, textAlign: "center", padding: 24 }}>
          <div
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "#ff7575",
              fontWeight: 700,
            }}
          >
            Application error
          </div>
          <h2 style={{ fontSize: "1.4rem", fontWeight: 700, margin: "6px 0 8px" }}>
            The Control Tower failed to load
          </h2>
          <p style={{ color: "#9db0c1", fontSize: "0.9rem" }}>
            A fatal error occurred while rendering the shell. Reloading usually fixes it.
          </p>
          <button
            onClick={() => reset()}
            style={{
              marginTop: 16,
              padding: "10px 20px",
              borderRadius: 12,
              border: "none",
              background: "linear-gradient(135deg, #57d4c0, #a0eedf)",
              color: "#071018",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
