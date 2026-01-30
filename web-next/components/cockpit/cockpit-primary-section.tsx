"use client";

import type { ComponentProps, ComponentPropsWithRef, RefObject } from "react";
import { CockpitActions } from "@/components/cockpit/cockpit-actions";
import {
  ChatComposer,
  CockpitChatThread,
} from "@/components/cockpit/cockpit-chat-thread";
import { CockpitChatConsole } from "@/components/cockpit/cockpit-chat-console";
import { CockpitHiddenPromptsPanel } from "@/components/cockpit/cockpit-hidden-prompts-panel";
import { CockpitHistoryPanel } from "@/components/cockpit/cockpit-history-panel";
import { CockpitLlmOpsPanel } from "@/components/cockpit/cockpit-llm-ops-panel";
import { CockpitMetrics } from "@/components/cockpit/cockpit-metrics";
import { CockpitSidebar } from "@/components/cockpit/cockpit-sidebar";

type ChatThreadProps = ComponentProps<typeof CockpitChatThread>;
type ChatComposerProps = ComponentPropsWithRef<typeof ChatComposer>;
type LlmOpsPanelProps = ComponentProps<typeof CockpitLlmOpsPanel>;
type HiddenPromptsPanelProps = ComponentProps<typeof CockpitHiddenPromptsPanel>;
type HistoryPanelProps = ComponentProps<typeof CockpitHistoryPanel>;
type CockpitMetricsProps = ComponentProps<typeof CockpitMetrics>;

type CockpitPrimarySectionProps = {
  chatFullscreen: boolean;
  setChatFullscreen: (value: boolean) => void;
  showArtifacts: boolean;
  showReferenceSections: boolean;
  showSharedSections: boolean;
  labMode: boolean;
  responseBadgeTone: "success" | "warning" | "neutral" | "danger";
  responseBadgeTitle: string;
  responseBadgeText: string;
  chatThreadProps: ChatThreadProps;
  chatScrollRef: RefObject<HTMLDivElement>;
  onChatScroll: () => void;
  composerProps: ChatComposerProps;
  quickActionsOpen: boolean;
  setQuickActionsOpen: (value: boolean) => void;
  message: string | null;
  promptPresets: ReadonlyArray<{ id: string; category: string; description: string; prompt: string; icon: string }>;
  onSuggestionClick: (prompt: string) => void;
  llmOpsPanelProps: LlmOpsPanelProps;
  hiddenPromptsPanelProps: HiddenPromptsPanelProps;
  historyPanelProps: HistoryPanelProps;
  metricsProps: CockpitMetricsProps;
};

export function CockpitPrimarySection({
  chatFullscreen,
  setChatFullscreen,
  showArtifacts,
  showReferenceSections,
  showSharedSections,
  labMode,
  responseBadgeTone,
  responseBadgeTitle,
  responseBadgeText,
  chatThreadProps,
  chatScrollRef,
  onChatScroll,
  composerProps,
  quickActionsOpen,
  setQuickActionsOpen,
  message,
  promptPresets,
  onSuggestionClick,
  llmOpsPanelProps,
  hiddenPromptsPanelProps,
  historyPanelProps,
  metricsProps,
}: CockpitPrimarySectionProps) {
  const hiddenPromptsPanel = <CockpitHiddenPromptsPanel {...hiddenPromptsPanelProps} />;
  const historyRequestsPanel = <CockpitHistoryPanel {...historyPanelProps} />;

  return (
    <section
      className={`grid gap-6 ${chatFullscreen
          ? "lg:grid-cols-1"
          : "lg:grid-cols-[minmax(0,360px)_1fr] xl:grid-cols-[minmax(0,440px)_1fr] 2xl:grid-cols-[minmax(0,520px)_1fr]"
        }`}
    >
      <CockpitSidebar
        chatFullscreen={chatFullscreen}
        showArtifacts={showArtifacts}
        showReferenceSections={showReferenceSections}
        referencePanel={<CockpitLlmOpsPanel {...llmOpsPanelProps} />}
        fallbackPanels={(
          <>
            {historyRequestsPanel}
            {hiddenPromptsPanel}
          </>
        )}
      />
      <div className="space-y-6">
        <CockpitChatConsole
          chatFullscreen={chatFullscreen}
          onToggleFullscreen={() => setChatFullscreen(!chatFullscreen)}
          labMode={labMode}
          responseBadgeTone={responseBadgeTone}
          responseBadgeTitle={responseBadgeTitle}
          responseBadgeText={responseBadgeText}
          chatList={<CockpitChatThread {...chatThreadProps} />}
          chatScrollRef={chatScrollRef}
          onChatScroll={onChatScroll}
          composer={<ChatComposer {...composerProps} />}
          quickActions={(
            <CockpitActions
              open={quickActionsOpen}
              onOpenChange={setQuickActionsOpen}
            />
          )}
          message={message}
          showArtifacts={showArtifacts}
          showSharedSections={showSharedSections}
          promptPresets={promptPresets}
          onSuggestionClick={onSuggestionClick}
        />
        <CockpitMetrics {...metricsProps} />
      </div>
    </section>
  );
}
