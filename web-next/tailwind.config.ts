import type { Config } from "tailwindcss";
import animatePlugin from "tailwindcss-animate";

const config: Config = {
  darkMode: "class",
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
        sans: "var(--font-inter)",
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
        "orb-thinking": {
          "0%, 100%": { opacity: "0.6", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.15)" },
        },
        "orb-ripple": {
          "0%": { transform: "scale(1)", opacity: "0.55" },
          "100%": { transform: "scale(2.15)", opacity: "0" },
        },
        "orb-blob": {
          "0%, 100%": { borderRadius: "60% 40% 70% 30% / 50% 60% 40% 70%" },
          "25%": { borderRadius: "40% 60% 30% 70% / 65% 35% 70% 45%" },
          "50%": { borderRadius: "70% 30% 55% 45% / 40% 70% 55% 60%" },
          "75%": { borderRadius: "35% 65% 45% 55% / 70% 45% 60% 40%" },
        },
        "orb-flash": {
          "0%": { opacity: "0" },
          "25%": { opacity: "0.55" },
          "100%": { opacity: "0" },
        },
        "orb-burst": {
          "0%": { transform: "scale(1)", opacity: "0.75" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        "orb-shockwave": {
          "0%": { transform: "scale(1)", opacity: "0.75" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
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
        "orb-thinking": "orb-thinking 2.4s ease-in-out infinite",
        "orb-ripple": "orb-ripple 1.55s ease-out infinite",
        "orb-blob": "orb-blob 3.2s ease-in-out infinite",
        "orb-flash": "orb-flash 0.32s ease-out forwards",
        "orb-burst": "orb-burst 0.58s ease-out forwards",
        "orb-shockwave": "orb-shockwave 0.6s ease-out forwards",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [animatePlugin],
};

export default config;
