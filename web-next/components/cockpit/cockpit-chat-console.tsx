"use client";

import type { ReactNode, RefObject } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { SectionHeading } from "@/components/ui/section-heading";
import { CockpitPanel3D } from "@/components/cockpit/cockpit-panel-3d";
import { Maximize2, Minimize2, RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n";

type ChatPreset = {
  readonly id: string;
  readonly category: string;
  readonly description: string;
  readonly prompt: string;
  readonly icon: string;
};

type CockpitChatConsoleProps = {
  chatFullscreen: boolean;
  onToggleFullscreen: () => void;
  labMode: boolean;
  responseBadgeTone: "success" | "warning" | "danger" | "neutral";
  responseBadgeTitle?: string;
  responseBadgeText: string;
  chatList: ReactNode;
  chatScrollRef: RefObject<HTMLDivElement>;
  onChatScroll: () => void;
  composer: ReactNode;
  quickActions: ReactNode;
  message?: string | null;
  showArtifacts: boolean;
  showSharedSections: boolean;
  promptPresets: ReadonlyArray<ChatPreset>;
  onSuggestionClick: (prompt: string) => void;
  onNewChat: () => void;
};

export function CockpitChatConsole({
  chatFullscreen,
  onToggleFullscreen,
  labMode,
  responseBadgeTone,
  responseBadgeTitle,
  responseBadgeText,
  chatList,
  chatScrollRef,
  onChatScroll,
  composer,
  quickActions,
  message,
  showArtifacts,
  showSharedSections,
  promptPresets,
  onSuggestionClick,
  onNewChat,
}: CockpitChatConsoleProps) {
  const t = useTranslation();

  return (
    <div className="space-y-6">
      <CockpitPanel3D fullscreen={chatFullscreen}>
        <IconButton
          label={chatFullscreen ? t("cockpit.fullscreen.off") : t("cockpit.fullscreen.on")}
          size="xs"
          variant="outline"
          className="absolute right-6 top-6 z-20 border-white/10 text-white pointer-events-auto"
          icon={
            chatFullscreen ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )
          }
          onClick={onToggleFullscreen}
        />
        <SectionHeading
          eyebrow={t("cockpit.header.eyebrow")}
          title={t("cockpit.header.title")}
          description={t("cockpit.header.description")}
          as="h2"
          size="md"
          className="items-center"
          rightSlot={
            <div className="flex flex-wrap items-center gap-2 pr-10">
              <Button
                variant="amber"
                size="xs"
                onClick={onNewChat}
              >
                <RefreshCw className="mr-1.5 h-3 w-3" />
                {t("cockpit.newChat")}
              </Button>
              <Badge tone={labMode ? "warning" : "success"}>
                {labMode ? t("cockpit.status.lab") : t("cockpit.status.prod")}
              </Badge>
              <Badge tone={responseBadgeTone} title={responseBadgeTitle}>
                {t("cockpit.responseLabel", { text: responseBadgeText })}
              </Badge>
            </div>
          }
        />
        <div className="grid-overlay relative mt-5 flex-1 min-h-0 rounded-3xl box-muted p-6 !overflow-hidden pb-10 flex flex-col">
          <div className="flex flex-1 min-h-0 flex-col">
            <div
              className="chat-history-scroll flex-1 min-h-0 space-y-4 overflow-y-auto pr-4 overscroll-contain"
              ref={chatScrollRef}
              onScroll={onChatScroll}
              data-testid="cockpit-chat-history"
            >
              {chatList}
            </div>
            <div className="shrink-0">
              {composer}
              {quickActions}
              {message && (
                <p className="mt-2 text-xs text-amber-300">{message}</p>
              )}
            </div>
          </div>
        </div>
      </CockpitPanel3D>
      {!chatFullscreen && showSharedSections && showArtifacts && (
        <div className="mt-4 space-y-3 rounded-2xl box-base px-4 py-4 text-sm text-zinc-300">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-caption">{t("cockpit.suggestions.eyebrow")}</p>
            <span className="text-caption text-zinc-600">
              {t("cockpit.suggestions.hint")}
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {promptPresets.map((preset) => (
              <Button
                key={preset.id}
                type="button"
                onClick={() => onSuggestionClick(preset.prompt)}
                title={preset.description}
                data-testid={`cockpit-preset-${preset.id}`}
                variant="ghost"
                size="sm"
                className="w-full items-center gap-3 rounded-2xl box-muted px-4 py-3 text-left transition hover:border-violet-400/50 hover:bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/60"
              >
                <span className="rounded-2xl bg-white/10 px-3 py-2 text-lg">
                  {preset.icon}
                </span>
                <div className="flex-1">
                  <p className="font-semibold text-white">{preset.category}</p>
                  <p className="text-hint">{preset.description}</p>
                </div>
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
