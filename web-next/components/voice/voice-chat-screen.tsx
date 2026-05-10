"use client";

import Link from "next/link";
import { useState, useCallback } from "react";
import type { LucideIcon } from "lucide-react";
import { ArrowLeft, Brain, MessageSquareText, Sparkles, ListTodo } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";
import {
  VoiceCommandCenter,
  type VoiceModePreset,
  type VoiceStatusUpdate,
} from "@/components/voice/voice-command-center";
import { VoiceStatusSidebar } from "@/components/voice/voice-status-sidebar";

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

export function VoiceChatScreen() {
  const [voiceModePreset, setVoiceModePreset] = useState<VoiceModePreset>("standard");
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatusUpdate | null>(null);
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

          {/* STT/TTS + Runtime status — compact info boxes for tuning */}
          <VoiceStatusSidebar status={voiceStatus} />
        </div>
      </div>
    </div>
  );
}
