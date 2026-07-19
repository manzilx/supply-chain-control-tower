import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#071018",
        surface: "#0f1b27",
        panel: "rgba(14, 26, 40, 0.96)",
        line: "rgba(132, 165, 191, 0.18)",
        ink: "#edf3f8",
        muted: "#9db0c1",
        accent: "#57d4c0",
        "accent-strong": "#11b29e",
        warning: "#f0b44c",
        danger: "#ff7575",
        steady: "#8caac7",
        sev: {
          low: "#8caac7",
          medium: "#f0b44c",
          high: "#ff9187",
          critical: "#ff7575",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"Avenir Next"', '"Segoe UI"', "sans-serif"],
        mono: ['"IBM Plex Mono"', '"SFMono-Regular"', "monospace"],
      },
      boxShadow: {
        panel: "0 28px 60px rgba(2, 6, 12, 0.42)",
        glow: "0 0 0 1px rgba(87, 212, 192, 0.35), 0 12px 32px rgba(87, 212, 192, 0.15)",
      },
      borderRadius: {
        panel: "20px",
      },
      keyframes: {
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.6s infinite",
        "fade-up": "fade-up 0.4s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
