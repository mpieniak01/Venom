"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TtsRuntimeEngineOption, TtsRuntimeState, TtsVoiceOption } from "@/lib/types";

const ENGINE_LABELS: Record<string, string> = {
  piper_local: "Piper Local",
  fish_speech: "Fish Speech",
};

const STATUS_LABELS: Record<string, string> = {
  ready: "Ready",
  fallback: "Fallback",
  no_model: "No model",
  disabled: "Disabled",
  offline: "Offline",
  error: "Error",
  unknown: "Unknown",
};

function StatusDot({ status }: { status: string }) {
  const colorClass =
    status === "ready"
      ? "bg-emerald-400"
      : status === "fallback" || status === "offline"
        ? "bg-amber-400"
        : "bg-zinc-500";
  return (
    <span
      aria-label={STATUS_LABELS[status] ?? status}
      className={`inline-block h-2 w-2 rounded-full ${colorClass}`}
    />
  );
}

type TtsRuntimeSelectorProps = {
  runtimeState: TtsRuntimeState | null;
  onSelectEngine: (engineId: string) => void;
  onSelectOption: (optionId: string) => void;
  engineChanging?: boolean;
  optionChanging?: boolean;
  mode?: "compact" | "full";
  disabled?: boolean;
};

export function TtsRuntimeSelector({
  runtimeState,
  onSelectEngine,
  onSelectOption,
  engineChanging = false,
  optionChanging = false,
  mode = "full",
  disabled = false,
}: TtsRuntimeSelectorProps) {
  if (!runtimeState) {
    return (
      <p className="text-xs text-zinc-500">
        {engineChanging ? "Updating TTS runtime…" : "TTS runtime unavailable"}
      </p>
    );
  }

  const { tts_engine, available_engines, options, current_option_id, engine_status } =
    runtimeState;

  const activeEngineStatus = engine_status[tts_engine] ?? "unknown";
  const isDisabled = disabled || engineChanging;

  if (mode === "compact") {
    return (
      <div className="flex items-center gap-2 text-xs text-zinc-300">
        <StatusDot status={activeEngineStatus} />
        <span className="text-zinc-400">TTS:</span>
        <Select value={tts_engine} onValueChange={onSelectEngine} disabled={isDisabled}>
          <SelectTrigger className="h-7 w-36 border-white/10 bg-white/5 text-xs text-zinc-100">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="border-white/10 bg-zinc-950 text-zinc-100">
            {available_engines.map((eng: TtsRuntimeEngineOption) => (
              <SelectItem key={eng.engine_id} value={eng.engine_id}>
                {ENGINE_LABELS[eng.engine_id] ?? eng.engine_id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {engineChanging && <span className="text-zinc-500">…</span>}
      </div>
    );
  }

  return (
    <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300 space-y-3">
      {/* Engine selector row */}
      <div>
        <p className="text-caption mb-2 flex items-center gap-2">
          TTS Engine
          <StatusDot status={activeEngineStatus} />
          <span className="text-zinc-500">{STATUS_LABELS[activeEngineStatus] ?? activeEngineStatus}</span>
        </p>
        <Select value={tts_engine} onValueChange={onSelectEngine} disabled={isDisabled}>
          <SelectTrigger className="h-8 border-white/10 bg-white/5 text-xs text-zinc-100">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="border-white/10 bg-zinc-950 text-zinc-100">
            {available_engines.map((eng: TtsRuntimeEngineOption) => (
              <SelectItem key={eng.engine_id} value={eng.engine_id}>
                <span className="flex items-center gap-2">
                  <StatusDot status={eng.status} />
                  {ENGINE_LABELS[eng.engine_id] ?? eng.engine_id}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {engineChanging && (
          <p className="mt-1 text-zinc-500">Switching TTS engine…</p>
        )}
      </div>

      {/* Voice / profile options */}
      {options.length > 0 && (
        <div>
          <p className="text-caption mb-2">
            {tts_engine === "piper_local" ? "Voice model" : "Profile"}
          </p>
          <Select
            value={current_option_id ?? ""}
            onValueChange={onSelectOption}
            disabled={isDisabled || optionChanging || options.length === 0}
          >
            <SelectTrigger className="h-8 border-white/10 bg-white/5 text-xs text-zinc-100">
              <SelectValue placeholder="Select voice…" />
            </SelectTrigger>
            <SelectContent className="border-white/10 bg-zinc-950 text-zinc-100">
              {options.map((opt: TtsVoiceOption) => (
                <SelectItem key={opt.path} value={opt.path}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {optionChanging && (
            <p className="mt-1 text-zinc-500">Applying voice…</p>
          )}
        </div>
      )}

      {/* Fish Speech status notice */}
      {tts_engine === "fish_speech" && activeEngineStatus !== "ready" && (
        <p className="text-amber-400">
          Fish Speech daemon {activeEngineStatus === "disabled"
            ? "is disabled (set FISH_SPEECH_ENABLED=true)"
            : activeEngineStatus === "offline"
              ? "is offline — responses will fall back to Piper"
              : "is not ready"}
        </p>
      )}

      {/* Fallback notice */}
      {runtimeState.fallback_enabled && tts_engine !== "piper_local" && (
        <p className="text-zinc-500">
          Fallback to {ENGINE_LABELS[runtimeState.fallback_target ?? "piper_local"] ?? runtimeState.fallback_target} is enabled
        </p>
      )}
    </div>
  );
}
