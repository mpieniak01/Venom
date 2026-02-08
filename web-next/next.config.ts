import type { NextConfig } from "next";
import path from "path";
import { applyHttpPolicyToUrl, buildHttpBaseUrl } from "./lib/url-policy";

const API_PROXY_TARGET =
  applyHttpPolicyToUrl(
    process.env.API_PROXY_TARGET ||
      process.env.NEXT_PUBLIC_API_BASE ||
      buildHttpBaseUrl("127.0.0.1", 8000)
  );

const nextConfig: NextConfig = {
  // Ułatwia deployment produkcyjny (docker / serverless)
  output: "standalone",
  // Pozwala uniknąć ostrzeżeń przy wielu lockfile w repo (monorepo).
  outputFileTracingRoot: path.join(__dirname, ".."),
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion", "chart.js", "mermaid"],
  },
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
