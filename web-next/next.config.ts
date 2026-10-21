import type { NextConfig } from "next";

const TURBOPACK_ROOT = __dirname;
const WATCH_POLL_INTERVAL_MS = Number(process.env.NEXT_WATCH_POLL_INTERVAL_MS || "1000");

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_TRANSPORT_PROFILE: process.env.VENOM_OPERATOR_ACCESS || "secure" },
  // Ułatwia deployment produkcyjny (docker / serverless)
  output: "standalone",
  // Tracing i watcher dev muszą pracować na tym samym workspace root,
  // inaczej Next 16 ignoruje turbopack.root i wraca do szerszego zakresu repo.
  outputFileTracingRoot: TURBOPACK_ROOT,
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion", "chart.js", "mermaid"],
  },
  // Dev watcher musi być ograniczony do samego workspace frontendu.
  turbopack: {
    root: TURBOPACK_ROOT,
  },
  watchOptions: Number.isFinite(WATCH_POLL_INTERVAL_MS) && WATCH_POLL_INTERVAL_MS > 0
    ? { pollIntervalMs: WATCH_POLL_INTERVAL_MS }
    : undefined,
  // API and WS use the streaming Node entry (scripts/serve-with-proxy.mjs).
};

export default nextConfig;
