"use client";

import { useTranslation } from "@/lib/i18n";
import type { DaemonRespondResponse, RuntimeComponentSnapshotItem } from "@/lib/gemma4-daemon-api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StageHealth = "ok" | "degraded" | "skipped" | "fallback" | "empty" | "stub";

type ParsedTrace = {
  name: string;
  outcome: StageHealth;
};

type PolicyFields = {
  execution_mode?: string | null;
  image_strategy?: string | null;
  retrieval_mode?: string | null;
  audio_output_mode?: string | null;
  assistant_mode?: string | null;
  economy_mode?: string | null;
};

export type PipelineDiagnosticsPanelProps = Readonly<{
  response: DaemonRespondResponse | null;
}>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parsePolicy(raw: string | null | undefined): PolicyFields {
  if (!raw) return {};
  // format: "balanced|vlm_only|off|off|off|off"
  const parts = raw.split("|");
  return {
    execution_mode: parts[0] ?? null,
    image_strategy: parts[1] ?? null,
    retrieval_mode: parts[2] ?? null,
    audio_output_mode: parts[3] ?? null,
    assistant_mode: parts[4] ?? null,
    economy_mode: parts[5] ?? null,
  };
}

function parseTrace(trace: string[]): ParsedTrace[] {
  return trace.map((entry) => {
    const colonIdx = entry.lastIndexOf(":");
    if (colonIdx > 0) {
      return { name: entry.slice(0, colonIdx), outcome: entry.slice(colonIdx + 1) as StageHealth };
    }
    return { name: entry, outcome: "ok" };
  });
}

function stageIcon(outcome: StageHealth): string {
  if (outcome === "ok") return "✓";
  if (outcome === "skipped") return "–";
  if (outcome === "degraded" || outcome === "fallback") return "⚠";
  if (outcome === "empty") return "∅";
  return "·";
}

function stageColor(outcome: StageHealth): string {
  if (outcome === "ok") return "text-emerald-400";
  if (outcome === "skipped" || outcome === "empty") return "text-zinc-500";
  if (outcome === "degraded" || outcome === "fallback") return "text-amber-400";
  return "text-zinc-400";
}

function componentHealthColor(health: string): string {
  if (health === "ok") return "text-emerald-400";
  if (health === "degraded") return "text-amber-400";
  return "text-zinc-500";
}

function componentHealthLabel(health: string): string {
  if (health === "ok") return "ok";
  if (health === "degraded") return "degraded";
  return "off";
}

// ---------------------------------------------------------------------------
// Sub-sections
// ---------------------------------------------------------------------------

function PolicySection({ policy, title }: Readonly<{ policy: PolicyFields; title: string }>) {
  const rows: [string, string | null | undefined][] = [
    ["mode", policy.execution_mode],
    ["image", policy.image_strategy],
    ["retrieval", policy.retrieval_mode],
    ["audio out", policy.audio_output_mode],
    ["assistant", policy.assistant_mode],
    ["economy", policy.economy_mode],
  ];

  return (
    <div>
      <p className="mb-1 text-[9px] uppercase tracking-widest text-zinc-600">{title}</p>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {rows.map(([label, value]) =>
          value ? (
            <span key={label} className="text-[10px] text-zinc-400">
              <span className="text-zinc-600">{label}:</span> {value}
            </span>
          ) : null,
        )}
      </div>
    </div>
  );
}

function StagesSection({ traces, title }: Readonly<{ traces: ParsedTrace[]; title: string }>) {
  if (!traces.length) return null;
  return (
    <div>
      <p className="mb-1 text-[9px] uppercase tracking-widest text-zinc-600">{title}</p>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {traces.map(({ name, outcome }) => (
          <span key={name} className="text-[10px]">
            <span className={stageColor(outcome)}>{stageIcon(outcome)}</span>{" "}
            <span className="text-zinc-400">{name}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ComponentsSection({
  snapshot,
  title,
}: Readonly<{ snapshot: RuntimeComponentSnapshotItem[]; title: string }>) {
  const active = snapshot.filter((c) => c.health !== "disabled" || c.enabled);
  if (!active.length) return null;
  return (
    <div>
      <p className="mb-1 text-[9px] uppercase tracking-widest text-zinc-600">{title}</p>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {active.map((c) => (
          <span key={c.component_id} className="text-[10px]">
            <span className={componentHealthColor(c.health)}>
              {componentHealthLabel(c.health)}
            </span>{" "}
            <span className="text-zinc-400">{c.component_id}</span>
            {c.backend && c.backend !== "builtin" && (
              <span className="text-zinc-600"> ({c.backend})</span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

function DegradationsSection({ reasons, title }: Readonly<{ reasons: string[]; title: string }>) {
  if (!reasons.length) return null;
  return (
    <div>
      <p className="mb-1 text-[9px] uppercase tracking-widest text-amber-600">{title}</p>
      <ul className="space-y-0.5">
        {reasons.map((r, i) => (
          <li key={`${i}:${r}`} className="text-[10px] text-amber-400">
            ⚠ {r}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AudioOutputSection({
  audioBytes,
  sampleRate,
  title,
}: Readonly<{
  audioBytes: string | null | undefined;
  sampleRate: number | null | undefined;
  title: string;
}>) {
  if (!audioBytes) return null;
  const kbSize = Math.round((audioBytes.length * 3) / 4 / 1024);
  return (
    <div>
      <p className="mb-1 text-[9px] uppercase tracking-widest text-zinc-600">{title}</p>
      <p className="text-[10px] text-emerald-400">
        ✓ {kbSize} KB WAV{sampleRate ? ` @ ${sampleRate} Hz` : ""}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function PipelineDiagnosticsPanel({ response }: PipelineDiagnosticsPanelProps) {
  const t = useTranslation();
  const pd = (key: string) => t(`voice.daemon.pipelineDiagnostics.${key}`);

  if (!response) {
    return (
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
        <p className="text-[10px] text-zinc-600">{pd("noData")}</p>
      </div>
    );
  }

  const policy = parsePolicy(response.selected_policy);
  const traces = parseTrace(response.execution_trace ?? []);

  return (
    <div className="space-y-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      <PolicySection policy={policy} title={pd("policy")} />
      <StagesSection traces={traces} title={pd("stages")} />
      <ComponentsSection snapshot={response.component_snapshot ?? []} title={pd("components")} />
      <DegradationsSection reasons={response.degradation_reasons ?? []} title={pd("degradations")} />
      <AudioOutputSection
        audioBytes={response.audio_output_bytes}
        sampleRate={response.audio_output_sample_rate}
        title={pd("audioOutput")}
      />
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 border-t border-white/[0.04] pt-2">
        {response.retrieval_used && (
          <span className="text-[10px] text-zinc-400">
            {pd("retrieval")}: <span className="text-emerald-400">{response.retrieval_route ?? "on"}</span>
            {response.retrieval_context_items ? ` (${response.retrieval_context_items} items)` : ""}
          </span>
        )}
        {response.assistant_used && (
          <span className="text-[10px] text-zinc-400">
            {pd("assistant")}: <span className="text-emerald-400">{pd("used")}</span>
          </span>
        )}
        {response.economy_mode_activated && (
          <span className="text-[10px] text-amber-400">{pd("economyModeActive")}</span>
        )}
        {response.selected_image_strategy && response.selected_image_strategy !== "none" && (
          <span className="text-[10px] text-zinc-400">
            {pd("image")}: <span className="text-zinc-300">{response.selected_image_strategy}</span>
          </span>
        )}
      </div>
    </div>
  );
}
