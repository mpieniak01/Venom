"use client";

import Link from "next/link";
import { useState, useCallback } from "react";
import type { LucideIcon } from "lucide-react";
import { ArrowLeft, Brain, MessageSquareText, Sparkles, ListTodo } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";
import { isMultiRuntime } from "@/lib/runtime-id";
import { buildVoiceRuntimeStateView } from "@/lib/voice-runtime-state";
import {
  VoiceCommandCenter,
  type VoiceModePreset,
  type VoiceStatusUpdate,
} from "@/components/voice/voice-command-center";
import { VoiceStatusSidebar } from "@/components/voice/voice-status-sidebar";
import { ImageProbeCard } from "@/components/gemma4/gemma4-runtime-control";

type VoiceModeCard = {
  mode: VoiceModePreset;
  titleKey: string;
  descriptionKey: string;
  icon: LucideIcon;
};

const VOICE_MODES: VoiceModeCard[] = [
  {
    mode: "standard",
    titleKey: "voice.modes.standard.title",
    descriptionKey: "voice.modes.standard.description",
    icon: MessageSquareText,
  },
  {
    mode: "deep_analysis",
    titleKey: "voice.modes.deepAnalysis.title",
    descriptionKey: "voice.modes.deepAnalysis.description",
    icon: Brain,
  },
  {
    mode: "summary",
    titleKey: "voice.modes.summary.title",
    descriptionKey: "voice.modes.summary.description",
    icon: Sparkles,
  },
  {
    mode: "action_items",
    titleKey: "voice.modes.actionItems.title",
    descriptionKey: "voice.modes.actionItems.description",
    icon: ListTodo,
  },
];

type VoiceChatScreenProps = Readonly<{
  isDevMode?: boolean;
}>;

export function VoiceChatScreen({ isDevMode = false }: VoiceChatScreenProps) {
  const [voiceModePreset, setVoiceModePreset] = useState<VoiceModePreset>("standard");
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatusUpdate | null>(null);
  const [statusRefreshSignal, setStatusRefreshSignal] = useState(0);
  const t = useTranslation();

  const handleStatusUpdate = useCallback((s: VoiceStatusUpdate | null) => {
    setVoiceStatus(s);
  }, []);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow={t("voice.page.eyebrow")}
        title={t("voice.page.title")}
        description={t("voice.page.description")}
        rightSlot={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="success">{t("voice.modes.title")}</Badge>
            <Button asChild variant="outline" size="xs">
              <Link href="/chat">
                <ArrowLeft className="mr-1.5 h-3 w-3" />
                {t("voice.page.backToChat")}
              </Link>
            </Button>
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,0.85fr)]">
        <VoiceCommandCenter
          voiceModePreset={voiceModePreset}
          onStatusUpdate={handleStatusUpdate}
          statusRefreshSignal={statusRefreshSignal}
          isDevMode={isDevMode}
        />
        <div className="space-y-4">
          {/* Mode selector */}
          <div className="rounded-3xl box-muted p-4">
            <p className="eyebrow">{t("voice.modes.title")}</p>
            <p className="mt-1 text-sm text-zinc-300">{t("voice.modes.description")}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              {VOICE_MODES.map((item) => {
                const Icon = item.icon;
                const selected = voiceModePreset === item.mode;
                const title = t(item.titleKey);
                const description = t(item.descriptionKey);
                return (
                  <Button
                    key={item.mode}
                    type="button"
                    variant={selected ? "primary" : "outline"}
                    className="h-auto justify-start rounded-2xl px-4 py-3 text-left"
                    onClick={() => setVoiceModePreset(item.mode)}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="flex flex-col items-start gap-0.5">
                      <span className="font-semibold">{title}</span>
                      <span className="text-[11px] leading-snug opacity-80">{description}</span>
                    </span>
                  </Button>
                );
              })}
            </div>
            <p className="mt-3 text-xs text-zinc-400">{t("voice.modes.hint")}</p>
          </div>

          {/* F3-01: System status bar */}
          <VoiceSystemStatusBar status={voiceStatus} />

          {/* Obsługa obrazu — osobny box bezpośrednio po Tryby voice */}
          <ImageProbeCard />

          {/* STT/TTS + Runtime status — compact info boxes for tuning */}
          <VoiceStatusSidebar
            status={voiceStatus}
            isDevMode={isDevMode}
            onRuntimeApplied={() => {
              setStatusRefreshSignal((current) => current + 1);
            }}
          />
        </div>
      </div>
    </div>
  );
}

function VoiceSystemStatusBar({ status }: Readonly<{ status: VoiceStatusUpdate | null }>) {
  const t = useTranslation();
  if (!status) return null;

  const sttReady = toReadiness(status.stt_ready);
  const ttsReady = toReadiness(status.tts_ready);
  const runtimeState = buildVoiceRuntimeStateView(status);
  const runtimeProvider = runtimeState.active.runtimeId;
  const runtimeModel = runtimeState.active.modelName;
  const sessionRuntimeProvider = runtimeState.response.runtimeId;
  const sessionRuntimeModel = runtimeState.response.modelName;
  const probeStatus = status.runtime_snapshot?.runtime_capabilities?.probe_status ?? null;
  const hasRuntimeFromSnapshot = runtimeProvider.length > 0 && runtimeModel.length > 0;
  const hasRuntimeFromLatestSession = sessionRuntimeProvider.length > 0 && sessionRuntimeModel.length > 0;
  const llmReady = hasRuntimeFromSnapshot || hasRuntimeFromLatestSession ? "ready" : "unknown";
  const isNativeVoiceRuntime = isMultiRuntime(runtimeProvider);
  const voiceProbeFailed = probeStatus === "failed";
  const voiceProbeBlocking = voiceProbeFailed && isNativeVoiceRuntime;
  const hasHardFailure = sttReady === "not_ready" || ttsReady === "not_ready" || voiceProbeBlocking;
  const hasPositiveSignal = llmReady === "ready" || sttReady === "ready" || ttsReady === "ready";
  const allOk = !hasHardFailure && hasPositiveSignal;
  const voiceProbeToneClass = resolveVoiceProbeToneClass(voiceProbeFailed, voiceProbeBlocking);
  const voiceProbeDotClass = resolveVoiceProbeDotClass(voiceProbeFailed, voiceProbeBlocking);
  const containerClass = allOk
    ? "border border-emerald-500/20 bg-emerald-500/[0.04] text-emerald-400"
    : "border border-amber-500/20 bg-amber-500/[0.04] text-amber-400";

  return (
    <div
      className={`rounded-2xl px-4 py-2 flex items-center justify-between gap-3 text-[11px] ${containerClass}`}
    >
      <span className="font-medium">
        {allOk ? t("voice.status.systemReady") : t("voice.status.systemPartial")}
      </span>
      <span className="flex items-center gap-3">
        <span className={`flex items-center gap-1 ${resolveReadinessToneClass(llmReady)}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${resolveReadinessDotClass(llmReady)}`} />
          {" "}
          LLM
        </span>
        <span className={`flex items-center gap-1 ${resolveReadinessToneClass(sttReady)}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${resolveReadinessDotClass(sttReady)}`} />
          {" "}
          STT
        </span>
        <span className={`flex items-center gap-1 ${resolveReadinessToneClass(ttsReady)}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${resolveReadinessDotClass(ttsReady)}`} />
          {" "}
          TTS
        </span>
        <span
          className={`flex items-center gap-1 ${voiceProbeToneClass}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${voiceProbeDotClass}`} />
          {" "}
          {probeStatus ?? "—"}
        </span>
      </span>
    </div>
  );
}

type Readiness = "ready" | "not_ready" | "unknown";

function toReadiness(flag: boolean | null | undefined): Readiness {
  if (flag === true) return "ready";
  if (flag === false) return "not_ready";
  return "unknown";
}

function resolveReadinessToneClass(readiness: Readiness): string {
  if (readiness === "ready") return "text-emerald-400";
  if (readiness === "not_ready") return "text-rose-400";
  return "text-zinc-600";
}

function resolveReadinessDotClass(readiness: Readiness): string {
  if (readiness === "ready") return "bg-emerald-400";
  if (readiness === "not_ready") return "bg-rose-400";
  return "bg-zinc-600";
}

function resolveVoiceProbeToneClass(
  voiceProbeFailed: boolean,
  voiceProbeBlocking: boolean,
): string {
  if (!voiceProbeFailed) return "text-emerald-400";
  if (voiceProbeBlocking) return "text-rose-400";
  return "text-amber-400";
}

function resolveVoiceProbeDotClass(
  voiceProbeFailed: boolean,
  voiceProbeBlocking: boolean,
): string {
  if (!voiceProbeFailed) return "bg-emerald-400";
  if (voiceProbeBlocking) return "bg-rose-400";
  return "bg-amber-400";
}
