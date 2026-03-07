import type { NextConfig } from "next";
import path from "path";

const API_PROXY_TARGET =
  process.env.API_PROXY_TARGET ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://127.0.0.1:8000";
const TURBOPACK_ROOT = __dirname;
const WATCH_POLL_INTERVAL_MS = Number(process.env.NEXT_WATCH_POLL_INTERVAL_MS || "1000");

const nextConfig: NextConfig = {
  // Ułatwia deployment produkcyjny (docker / serverless)
  output: "standalone",
  // Pozwala uniknąć ostrzeżeń przy wielu lockfile w repo (monorepo).
  outputFileTracingRoot: path.join(__dirname, ".."),
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion", "chart.js", "mermaid"],
  },
  // Dev watcher musi być ograniczony do samego workspace frontendu.
  // Produkcyjny tracing może dalej obejmować root repo, ale Turbopack nie powinien
  // próbować obserwować całego monorepo z logs/data/test-results.
  turbopack: {
    root: TURBOPACK_ROOT,
  },
  watchOptions: Number.isFinite(WATCH_POLL_INTERVAL_MS) && WATCH_POLL_INTERVAL_MS > 0
    ? { pollIntervalMs: WATCH_POLL_INTERVAL_MS }
    : undefined,
  // Proxy do FastAPI w trybie dev, żeby uniknąć problemów z CORS.
  async rewrites() {
    if (!API_PROXY_TARGET) {
      return [];
    }

    return [
      {
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
      {
        // WS nie są przepisywane automatycznie, ale ten rewrite pozwala
        // przynajmniej trzymać jednolity prefix w fetchach.
        source: "/ws/:path*",
        destination: `${API_PROXY_TARGET}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
