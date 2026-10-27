import { execFileSync } from "node:child_process";
import { stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";

export default async function globalSetup() {
  if (process.env.CI !== "true" || process.env.GITHUB_ACTIONS !== "true" ||
      process.env.RUNNER_ENVIRONMENT !== "github-hosted" || process.getuid?.() === 0) {
    throw new Error("The real API E2E runs only as an unprivileged user on GitHub-hosted runners.");
  }
  execFileSync("python3", [fileURLToPath(new URL("../../scripts/ci/verify_github_e2e_namespace.py", import.meta.url))], { stdio: "inherit" });
  for (const path of ["/run/docker.sock", "/var/run/docker.sock", "/run/containerd/containerd.sock", "/run/dbus/system_bus_socket", `/run/user/${process.getuid()}/bus`]) {
    const info = await stat(path).catch((error) => {
      if (error.code === "ENOENT" || error.code === "ENOTDIR") return null;
      throw error;
    });
    if (info?.isSocket()) throw new Error(`Host socket must be masked: ${path}`);
  }
  for (const base of ["http://127.0.0.1:18800", "http://127.0.0.1:13300"]) {
    const result = await fetch(`${base}/api/v1/system/llm-servers/active`);
    if (!result.ok) throw new Error(`No live backend behind ${base}`);
    const active = await result.json();
    if (active.active_model !== "ci-fake-llm" || active.active_endpoint !== "http://127.0.0.1:11434/v1") {
      throw new Error(`Unexpected backend runtime at ${base}`);
    }
  }
}
