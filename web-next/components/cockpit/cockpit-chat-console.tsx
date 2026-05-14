"use client";

import { useEffect, useMemo } from "react";
import type { ReactNode, RefObject } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { SectionHeading } from "@/components/ui/section-heading";
import { CockpitPanel3D } from "@/components/cockpit/cockpit-panel-3d";
import { Maximize2, Minimize2, RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { useGemma4Daemon } from "@/hooks/use-gemma4-daemon";
import {
  RuntimeDiagnosticsPanel,
  type RuntimeSummaryItem,
} from "@/components/runtime/runtime-diagnostics-panel";

type ChatPreset = {
  readonly id: string;
  readonly category: string;
  readonly description: string;
  readonly prompt: string;
  readonly icon: string;
};

type CockpitChatConsoleProps = Readonly<{
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
}>;

function resolveRuntimeEmptyStateTitle(loading: boolean, error: string | null): string {
  if (loading) return "Connecting to runtime daemon";
  if (error) return "Runtime daemon unavailable";
  return "Runtime diagnostics unavailable";
}

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
  const daemon = useGemma4Daemon(12_000);
  const runtimeStatus = daemon.status;
  const runtimeEmptyStateTitle = resolveRuntimeEmptyStateTitle(daemon.loading, daemon.error);
  const runtimeEmptyStateDescription = daemon.loading
    ? "Waiting for multi_runtime status."
    : daemon.error || "Daemon status is not available yet.";
  useEffect(() => {
    if (!chatFullscreen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [chatFullscreen]);

  const runtimeSummary = useMemo<RuntimeSummaryItem[]>(() => {
    if (!runtimeStatus) return [];
    return [
      {
        label: "Target",
        value: runtimeStatus.target_model,
        tone: runtimeStatus.target_loaded ? "success" : "warning",
        hint: runtimeStatus.mode,
      },
      {
        label: "Assistant",
        value: runtimeStatus.assistant_model ?? "—",
        tone: runtimeStatus.assistant_loaded ? "success" : "neutral",
        hint: runtimeStatus.params.assistant_mode,
      },
      {
        label: "Policy",
        value: runtimeStatus.params.execution_mode,
        tone: "neutral",
        hint: `image ${runtimeStatus.params.image_strategy}`,
      },
      {
        label: "Retrieval",
        value: runtimeStatus.params.retrieval_mode,
        tone: runtimeStatus.params.retrieval_mode === "off" ? "neutral" : "success",
        hint: `audio ${runtimeStatus.params.audio_output_mode}`,
      },
      {
        label: "Economy",
        value: runtimeStatus.params.economy_mode,
        tone: runtimeStatus.params.economy_mode === "auto" ? "warning" : "success",
        hint: `assistant ${runtimeStatus.params.assistant_mode}`,
      },
      {
        label: "Image budget",
        value: runtimeStatus.params.image_token_budget,
        tone: "neutral",
        hint: `thinking ${runtimeStatus.params.enable_thinking ? "on" : "off"}`,
      },
    ];
  }, [runtimeStatus]);

  const runtimeDegradations = useMemo(() => {
    if (!runtimeStatus) return [];
    const reasons = new Set<string>();
    for (const component of runtimeStatus.component_snapshot ?? []) {
      if (component.enabled && component.available === false) {
        reasons.add(`${component.component_id}: unavailable`);
      }
      if (component.last_error) {
        reasons.add(component.last_error);
      }
    }
    if (runtimeStatus.pending_reload && runtimeStatus.reload_reason) {
      reasons.add(runtimeStatus.reload_reason);
    }
    if (!runtimeStatus.target_loaded) {
      reasons.add("target model not loaded");
    }
    return Array.from(reasons);
  }, [runtimeStatus]);

  return (
    <div className="space-y-6">
      <CockpitPanel3D fullscreen={chatFullscreen}>
        <IconButton
          label={chatFullscreen ? t("cockpit.fullscreen.off") : t("cockpit.fullscreen.on")}
          size="xs"
          variant="outline"
          className="absolute right-6 top-6 z-20 border-[color:var(--ui-border)] text-[color:var(--text-primary)] pointer-events-auto"
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
                asChild
                variant="outline"
                size="xs"
              >
                <Link href="/voice">
                  {t("sidebar.nav.voice")}
                </Link>
              </Button>
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
              className="chat-history-scroll flex-1 min-h-0 space-y-4 overflow-x-hidden overflow-y-scroll pr-4 overscroll-contain"
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
                <p className="mt-2 text-xs text-tone-warning">{message}</p>
              )}
            </div>
          </div>
        </div>
      </CockpitPanel3D>
      <RuntimeDiagnosticsPanel
        title="Runtime diagnostics"
        description="Active daemon snapshot, component health and degradation reasons."
        summaryItems={runtimeSummary}
        componentSnapshot={runtimeStatus?.component_snapshot ?? []}
        degradationReasons={runtimeDegradations}
        emptyStateTitle={runtimeEmptyStateTitle}
        emptyStateDescription={runtimeEmptyStateDescription}
      />
      {!chatFullscreen && showSharedSections && showArtifacts && (
        <div className="mt-4 space-y-3 rounded-2xl box-base px-4 py-4 text-sm text-[color:var(--text-secondary)]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-caption">{t("cockpit.suggestions.eyebrow")}</p>
            <span className="text-caption text-[color:var(--ui-muted)]">
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
                className="w-full items-center gap-3 rounded-2xl box-muted px-4 py-3 text-left transition hover:border-[color:var(--accent)] hover:bg-[color:var(--ui-surface-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[color:var(--accent)]"
              >
                <span className="rounded-2xl bg-[color:var(--ui-border)] px-3 py-2 text-lg">
                  {preset.icon}
                </span>
                <div className="flex-1">
                  <p className="font-semibold text-[color:var(--text-heading)]">{preset.category}</p>
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
