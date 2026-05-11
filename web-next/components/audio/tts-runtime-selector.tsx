"use client";

import { useTranslation } from "@/lib/i18n";
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

const STATUS_LABEL_KEYS: Record<string, string> = {
  ready: "voice.controls.ttsStatusReady",
  fallback: "voice.controls.ttsStatusFallback",
  no_model: "voice.controls.ttsStatusNoModel",
  disabled: "voice.controls.ttsStatusDisabled",
  offline: "voice.controls.ttsStatusOffline",
  error: "voice.controls.ttsStatusError",
  unknown: "voice.controls.ttsStatusUnknown",
};

function StatusDot({ status }: { status: string }) {
  const t = useTranslation();
  const statusLabels: Record<string, string> = {
    ready: t("voice.controls.ttsStatusReady"),
    fallback: t("voice.controls.ttsStatusFallback"),
    no_model: t("voice.controls.ttsStatusNoModel"),
    disabled: t("voice.controls.ttsStatusDisabled"),
    offline: t("voice.controls.ttsStatusOffline"),
    error: t("voice.controls.ttsStatusError"),
    unknown: t("voice.controls.ttsStatusUnknown"),
  };
  const colorClass =
    status === "ready"
      ? "bg-emerald-400"
      : status === "fallback" || status === "offline"
        ? "bg-amber-400"
        : "bg-zinc-500";
  return (
    <span
      aria-label={statusLabels[status] ?? status}
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
        {engineChanging ? t("voice.controls.ttsRuntimeUpdating") : t("voice.controls.ttsRuntimeUnavailable")}
      </p>
    );
  }

  const { tts_engine, available_engines, options, current_option_id, engine_status } =
    runtimeState;

  const activeEngineStatus = engine_status[tts_engine] ?? "unknown";
  const activeEngineStatusLabel = t(STATUS_LABEL_KEYS[activeEngineStatus] ?? STATUS_LABEL_KEYS.unknown);
  const isDisabled = disabled || engineChanging;
  const showVoiceOptions = tts_engine === "piper_local" && options.length > 0;
  const isFishSpeech = tts_engine === "fish_speech";

  if (mode === "compact") {
    return (
      <div className="flex items-center gap-2 text-xs text-zinc-300">
        <StatusDot status={activeEngineStatus} />
        <span className="text-zinc-400">{t("voice.controls.ttsEngineShort")}</span>
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
          {t("voice.controls.ttsEngine")}
          <StatusDot status={activeEngineStatus} />
          <span className="text-zinc-500">{activeEngineStatusLabel}</span>
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
          <p className="mt-1 text-zinc-500">{t("voice.controls.ttsEngineSwitching")}</p>
        )}
      </div>

      {/* Voice / profile options */}
      {showVoiceOptions && (
        <div>
          <p className="text-caption mb-2">
            {tts_engine === "piper_local"
              ? t("voice.controls.ttsVoiceModel")
              : t("voice.controls.profile")}
          </p>
          <Select
            value={current_option_id ?? ""}
            onValueChange={onSelectOption}
            disabled={isDisabled || optionChanging || options.length === 0}
          >
            <SelectTrigger className="h-8 border-white/10 bg-white/5 text-xs text-zinc-100">
              <SelectValue placeholder={t("voice.controls.ttsVoiceSelect")} />
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
            <p className="mt-1 text-zinc-500">{t("voice.controls.ttsVoiceApplying")}</p>
          )}
        </div>
      )}

      {/* Fish Speech status notice */}
      {isFishSpeech && activeEngineStatus !== "ready" && (
        <p className="text-amber-400">
          {activeEngineStatus === "disabled"
            ? t("voice.controls.fishSpeechDisabled")
            : activeEngineStatus === "offline"
              ? t("voice.controls.fishSpeechOffline")
              : t("voice.controls.fishSpeechNotReady")}
        </p>
      )}

      {/* Fallback notice */}
      {runtimeState.fallback_enabled && tts_engine !== "piper_local" && (
        <p className="text-zinc-500">
          {t("voice.controls.fallbackToPiperEnabled")}
        </p>
      )}
    </div>
  );
}
