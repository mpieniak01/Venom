import { readlink, stat } from "node:fs/promises";

export default async function globalSetup() {
  if (process.env.CI !== "true" || process.env.GITHUB_ACTIONS !== "true" ||
      process.env.RUNNER_ENVIRONMENT !== "github-hosted" || process.getuid?.() === 0) {
    throw new Error("The real API E2E runs only as an unprivileged user on GitHub-hosted runners.");
  }
  for (const namespace of ["net", "mnt"]) {
    if (await readlink(`/proc/self/ns/${namespace}`) === await readlink(`/proc/1/ns/${namespace}`)) {
      throw new Error(`A private ${namespace} namespace is required.`);
    }
  }
  for (const path of ["/run/docker.sock", "/var/run/docker.sock", "/run/containerd/containerd.sock", "/run/dbus/system_bus_socket", `/run/user/${process.getuid()}/bus`]) {
    const info = await stat(path).catch(() => null);
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
