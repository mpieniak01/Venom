import type { Config } from "tailwindcss";
import animatePlugin from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1440px",
      },
    },
    extend: {
      colors: {
        background: "var(--background)",
        panel: "var(--panel)",
        border: "var(--border)",
        accent: "var(--accent)",
        accent2: "var(--accent-2)",
        muted: "var(--muted)",
        terminal: "#050b0f",
      },
      fontFamily: {
        sans: "var(--font-geist-sans)",
        mono: "var(--font-jetbrains)",
      },
      borderRadius: {
        dashboard: "24px",
        panel: "20px",
      },
      boxShadow: {
        neon: "0 0 20px rgba(124, 58, 237, 0.35)",
        card: "0 15px 60px rgba(8, 8, 10, 0.45)",
      },
      keyframes: {
        "pulse-signal": {
          "0%, 100%": { opacity: "0.4", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.2)" },
        },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "pulse-signal": "pulse-signal 1.6s ease-in-out infinite",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [animatePlugin],
};

export default config;
