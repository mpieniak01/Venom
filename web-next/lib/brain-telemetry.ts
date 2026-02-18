export type BrainTelemetryMetric =
  | "brain_first_shell_ms"
  | "brain_graph_ready_ms"
  | "brain_focus_mode_usage"
  | "brain_full_mode_usage";

export function emitBrainMetric(name: BrainTelemetryMetric, value: number): void {
  if (typeof window === "undefined") return;
  try {
    if (process.env.NODE_ENV !== "production") {
      console.info(`[brain-telemetry] ${name}=${value}`);
    }
    window.dispatchEvent(
      new CustomEvent("venom:brain:metric", {
        detail: { name, value, timestamp: Date.now() },
      }),
    );
  } catch {
    // no-op telemetry failure
  }
}
