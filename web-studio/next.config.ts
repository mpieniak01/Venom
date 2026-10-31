import path from "node:path";
import type { NextConfig } from "next";
import { nextDistDir } from "../web-next/scripts/build-paths.mjs";
import { trustedLanDevOrigins } from "../web-next/scripts/transport-config.mjs";

// Shared Chat2 sources live outside this app, but route discovery stays in app/.
const repositoryRoot = path.resolve(__dirname, "..");
const nextConfig: NextConfig = {
  distDir: nextDistDir(),
  allowedDevOrigins: trustedLanDevOrigins(),
  env: { NEXT_PUBLIC_TRANSPORT_PROFILE: process.env.VENOM_OPERATOR_ACCESS || "secure" },
  output: "standalone",
  outputFileTracingRoot: repositoryRoot,
  turbopack: { root: repositoryRoot },
  experimental: { optimizePackageImports: ["lucide-react"] },
};

export default nextConfig;
