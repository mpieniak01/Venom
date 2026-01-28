"use client";

import {
  forwardRef,
  memo,
  useCallback,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import { ConversationBubble } from "@/components/cockpit/conversation-bubble";
import { useTranslation } from "@/lib/i18n";
import { filterSlashSuggestions } from "@/lib/slash-commands";
import type { SlashCommand } from "@/lib/slash-commands";
import { Settings, ThumbsDown, ThumbsUp } from "lucide-react";

export type ChatMode = "direct" | "normal" | "complex";

export type ChatMessage = {
  bubbleId: string;
  requestId: string | null;
  role: "user" | "assistant";
  text: string;
  status?: string | null;
  timestamp: string;
  prompt?: string;
  pending?: boolean;
  forcedTool?: string | null;
  forcedProvider?: string | null;
  modeLabel?: string | null;
  sourceLabel?: string | null;
  contextUsed?: {
    lessons?: string[];
    memory_entries?: string[];
  } | null;
};

export type ChatComposerHandle = {
  setDraft: (value: string) => void;
};

type ChatComposerProps = {
  onSend: (payload: string) => Promise<boolean>;
  sending: boolean;
  chatMode: ChatMode;
  setChatMode: (value: ChatMode) => void;
  labMode: boolean;
  setLabMode: (value: boolean) => void;
  selectedLlmServer: string;
  llmServerOptions: SelectMenuOption[];
  setSelectedLlmServer: (value: string) => void;
  selectedLlmModel: string;
  llmModelOptions: SelectMenuOption[];
  setSelectedLlmModel: (value: string) => void;
  onActivateModel?: (value: string) => void;
  hasModels: boolean;
  onOpenTuning: () => void;
  tuningLabel: string;
  compactControls?: boolean;
};

export const ChatComposer = memo(
  forwardRef<ChatComposerHandle, ChatComposerProps>(function ChatComposer(
    {
      onSend,
      sending,
      chatMode,
      setChatMode,
      labMode,
      setLabMode,
      selectedLlmServer,
      llmServerOptions,
      setSelectedLlmServer,
      selectedLlmModel,
      llmModelOptions,
      setSelectedLlmModel,
      onActivateModel,
      hasModels,
      onOpenTuning,
      tuningLabel,
      compactControls = false,
    },
    ref,
  ) {
    const t = useTranslation();
    const [draft, setDraft] = useState("");
    const [slashSuggestions, setSlashSuggestions] = useState<SlashCommand[]>([]);
    const [slashIndex, setSlashIndex] = useState(0);
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);
    const chatModeOptions: SelectMenuOption[] = [
      { value: "direct", label: t("cockpit.modes.directLabel") },
      { value: "normal", label: t("cockpit.modes.normalLabel") },
      { value: "complex", label: t("cockpit.modes.complexLabel") },
    ];

    useImperativeHandle(ref, () => ({
      setDraft: (value: string) => {
        setDraft(value);
        requestAnimationFrame(() => textareaRef.current?.focus());
      },
    }));

    const handleSendClick = useCallback(async () => {
      const ok = await onSend(draft);
      if (ok) {
        setDraft("");
      }
    }, [draft, onSend]);

    const applySlashSuggestion = useCallback((suggestion: SlashCommand) => {
      setDraft((current) => {
        const match = current.match(/^(\s*)\/[^\s]*/);
        if (!match) return `${suggestion.command} `;
        const prefix = match[1] ?? "";
        const rest = current.slice(match[0].length).replace(/^\s*/, " ");
        return `${prefix}${suggestion.command}${rest}`;
      });
      setSlashSuggestions([]);
      setSlashIndex(0);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }, []);

    const handleDraftChange = useCallback((value: string) => {
      setDraft(value);
      const matches = filterSlashSuggestions(value, 3);
      setSlashSuggestions(matches);
      setSlashIndex(0);
    }, []);

    const handleTextareaKeyDown = useCallback(
      (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (slashSuggestions.length > 0) {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setSlashIndex((prev) => (prev + 1) % slashSuggestions.length);
            return;
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            setSlashIndex((prev) => (prev - 1 + slashSuggestions.length) % slashSuggestions.length);
            return;
          }
          if (event.key === "Enter") {
            event.preventDefault();
            applySlashSuggestion(slashSuggestions[slashIndex]);
            return;
          }
          if (event.key === "Escape") {
            event.preventDefault();
            setSlashSuggestions([]);
            setSlashIndex(0);
            return;
          }
        }
        const isEnter = event.key === "Enter";
        const isModifier = event.ctrlKey || event.metaKey;
        if (isEnter && isModifier) {
          event.preventDefault();
          handleSendClick();
        }
      },
      [applySlashSuggestion, handleSendClick, slashIndex, slashSuggestions],
    );

    const labelClassName = compactControls ? "sr-only" : "text-caption shrink-0 whitespace-nowrap";
    const controlsWrapperClassName = compactControls
      ? "mt-2 flex flex-wrap items-center gap-2"
      : "mt-2 grid w-full max-w-full gap-2";
    const selectsRowClassName = compactControls
      ? "flex flex-wrap items-center gap-2"
      : "grid w-full max-w-full items-center gap-2 md:grid-cols-[auto_auto_auto] md:justify-between";
    const secondaryRowClassName = compactControls
      ? "flex flex-wrap items-center gap-2"
      : "flex w-full flex-wrap items-center gap-2";
    const controlStackClassName = compactControls
      ? "flex min-w-[150px] flex-1 flex-col gap-2"
      : "flex min-w-0 items-center gap-1.5";
    const modelControlClassName = compactControls
      ? controlStackClassName
      : "flex min-w-0 items-center gap-1.5";
    const modelMinWidthCh = useMemo(() => {
      const longest = llmModelOptions.reduce((max, option) => {
        return Math.max(max, option.label.length);
      }, 0);
      return Math.max(longest + 4, 22);
    }, [llmModelOptions]);
    const actionsClassName = compactControls
      ? "ml-auto flex flex-wrap items-center gap-2"
      : "ml-auto flex flex-wrap items-center justify-end gap-2";

    return (
      <div className="mt-3 shrink-0 border-t border-white/5 pt-3">
        <div className="relative">
          <textarea
            ref={textareaRef}
            rows={2}
            className="min-h-[64px] w-full rounded-xl box-base p-2 text-sm text-white outline-none placeholder:text-zinc-500 focus:border-violet-500/60 2xl:text-base"
            placeholder={t("cockpit.inputPlaceholder")}
            value={draft}
            onChange={(event) => handleDraftChange(event.target.value)}
            onKeyDown={handleTextareaKeyDown}
            data-testid="cockpit-prompt-input"
          />
          {slashSuggestions.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-10 mt-2 overflow-hidden rounded-2xl border border-white/10 bg-[#0c0f1c] shadow-xl">
              {slashSuggestions.map((suggestion, index) => (
                <button
                  key={suggestion.id}
                  type="button"
                  onClick={() => applySlashSuggestion(suggestion)}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left text-xs transition ${index === slashIndex ? "bg-white/10 text-white" : "text-zinc-300 hover:bg-white/5"
                    }`}
                >
                  <span className="font-semibold text-zinc-100">{suggestion.command}</span>
                  <span className="text-[11px] text-zinc-500">{suggestion.detail}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className={controlsWrapperClassName}>
          <div className={selectsRowClassName}>
            <div className={controlStackClassName}>
              <label className={labelClassName}>Serwer</label>
              <SelectMenu
                value={selectedLlmServer}
                options={llmServerOptions}
                onChange={setSelectedLlmServer}
                ariaLabel="Wybierz serwer LLM"
                buttonTestId="llm-server-select"
                placeholder="Wybierz serwer"
                buttonClassName="w-full justify-between rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-xs text-white whitespace-nowrap"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
            </div>
            <div
              className={modelControlClassName}
              style={
                !compactControls
                  ? {
                    width: `${modelMinWidthCh}ch`,
                    minWidth: `${modelMinWidthCh}ch`,
                    maxWidth: `${modelMinWidthCh}ch`,
                  }
                  : undefined
              }
            >
              <label className={labelClassName}>Model</label>
              <SelectMenu
                value={selectedLlmModel}
                options={llmModelOptions}
                onChange={(value) => {
                  setSelectedLlmModel(value);
                  if (value && value !== selectedLlmModel) {
                    onActivateModel?.(value);
                  }
                }}
                ariaLabel="Wybierz model LLM (czat)"
                buttonTestId="llm-model-select"
                placeholder="Brak modeli"
                disabled={!hasModels}
                buttonClassName="w-full justify-between rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-xs text-white whitespace-nowrap overflow-hidden text-ellipsis"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
            </div>
            <div className={controlStackClassName}>
              <label className={labelClassName}>Tryb</label>
              <SelectMenu
                value={chatMode}
                options={chatModeOptions}
                onChange={(value) => setChatMode(value as ChatMode)}
                ariaLabel="Wybierz tryb czatu"
                buttonTestId="chat-mode-select"
                menuTestId="chat-mode-menu"
                optionTestIdPrefix="chat-mode-option"
                buttonClassName="w-full justify-between rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-xs text-white whitespace-nowrap"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
            </div>
          </div>
          <div className={secondaryRowClassName}>
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={labMode}
                onChange={(event) => setLabMode(event.target.checked)}
              />
              Lab Mode (nie zapisuj lekcji)
            </label>
            <div className={actionsClassName}>
              <Button
                variant="outline"
                size="sm"
                onClick={onOpenTuning}
                className="border-emerald-400/40 bg-emerald-500/10 text-emerald-200 hover:border-emerald-300/70 hover:bg-emerald-500/20 hover:text-white"
                title="Dostosuj parametry generacji"
              >
                <Settings className="h-4 w-4 mr-1" />
                {tuningLabel}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDraft("")}
                className="text-zinc-300"
              >
                Wyczyść
              </Button>
              <Button
                onClick={handleSendClick}
                disabled={sending}
                size="sm"
                variant="macro"
                className="px-6"
                data-testid="cockpit-send-button"
              >
                {sending ? "Wysyłanie..." : "Wyślij"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }),
);

type FeedbackState = {
  rating?: "up" | "down" | null;
  comment?: string;
  message?: string | null;
};

type CockpitChatThreadProps = {
  chatMessages: ChatMessage[];
  selectedRequestId: string | null;
  historyLoading: boolean;
  feedbackByRequest: Record<string, FeedbackState>;
  feedbackSubmittingId: string | null;
  onOpenRequestDetail: (requestId: string, prompt?: string) => void;
  onFeedbackClick: (requestId: string, rating: "up" | "down") => void;
  onFeedbackSubmit: (requestId: string) => void;
  onUpdateFeedbackState: (requestId: string, patch: Partial<FeedbackState>) => void;
};

export function CockpitChatThread({
  chatMessages,
  selectedRequestId,
  historyLoading,
  feedbackByRequest,
  feedbackSubmittingId,
  onOpenRequestDetail,
  onFeedbackClick,
  onFeedbackSubmit,
  onUpdateFeedbackState,
}: CockpitChatThreadProps) {
  const content = useMemo(
    () => (
      <>
        {chatMessages.length === 0 && (
          <p className="text-sm text-zinc-500">
            Brak historii – wyślij pierwsze zadanie.
          </p>
        )}
        {chatMessages.map((msg) => {
          const requestId = msg.requestId;
          const isSelected = selectedRequestId === requestId;
          const canInspect = Boolean(requestId) && !msg.pending;
          const handleSelect =
            canInspect && requestId
              ? () => onOpenRequestDetail(requestId, msg.prompt)
              : undefined;
          const feedbackState =
            msg.role === "assistant" && requestId ? feedbackByRequest[requestId] : undefined;
          const feedbackLocked = Boolean(feedbackState?.rating);
          const feedbackActions =
            msg.role === "assistant" && requestId ? (
              <div className="flex items-center gap-2">
                <IconButton
                  label="Kciuk w górę"
                  variant="outline"
                  size="xs"
                  className={
                    feedbackState?.rating === "up"
                      ? "border-emerald-400/60 bg-emerald-500/10 focus-visible:outline-none focus-visible:ring-0"
                      : "focus-visible:outline-none focus-visible:ring-0"
                  }
                  icon={
                    <ThumbsUp
                      strokeWidth={2.5}
                      className={
                        feedbackState?.rating === "up"
                          ? "h-3.5 w-3.5 text-emerald-300"
                          : "h-3.5 w-3.5"
                      }
                    />
                  }
                  disabled={feedbackSubmittingId === requestId || feedbackLocked}
                  onClick={(event) => {
                    event.stopPropagation();
                    onFeedbackClick(requestId, "up");
                  }}
                />
                <IconButton
                  label="Kciuk w dół"
                  variant="outline"
                  size="xs"
                  className={
                    feedbackState?.rating === "down"
                      ? "border-rose-400/60 bg-rose-500/10 focus-visible:outline-none focus-visible:ring-0"
                      : "focus-visible:outline-none focus-visible:ring-0"
                  }
                  icon={
                    <ThumbsDown
                      strokeWidth={2.5}
                      className={
                        feedbackState?.rating === "down"
                          ? "h-3.5 w-3.5 text-rose-300"
                          : "h-3.5 w-3.5"
                      }
                    />
                  }
                  disabled={feedbackSubmittingId === requestId || feedbackLocked}
                  onClick={(event) => {
                    event.stopPropagation();
                    onFeedbackClick(requestId, "down");
                  }}
                />
                {feedbackState?.rating === "down" && feedbackState.comment !== undefined ? (
                  <Button
                    variant="outline"
                    size="xs"
                    disabled={
                      feedbackSubmittingId === requestId ||
                      !(feedbackState.comment || "").trim()
                    }
                    onClick={(event) => {
                      event.stopPropagation();
                      onFeedbackSubmit(requestId);
                    }}
                  >
                    {feedbackSubmittingId === requestId ? "Wysyłam..." : "Zapisz"}
                  </Button>
                ) : null}
              </div>
            ) : null;
          const feedbackExtra =
            msg.role === "assistant" &&
              requestId &&
              !msg.pending &&
              feedbackState?.rating === "down" ? (
              <>
                <textarea
                  className="min-h-[70px] w-full rounded-2xl box-muted px-3 py-2 text-xs text-white outline-none placeholder:text-zinc-500"
                  placeholder="Opisz krótko, co było nie tak i czego oczekujesz."
                  value={feedbackState.comment || ""}
                  onChange={(event) =>
                    onUpdateFeedbackState(requestId, {
                      comment: event.target.value,
                    })
                  }
                  onClick={(event) => event.stopPropagation()}
                  onKeyDown={(event) => event.stopPropagation()}
                />
                {feedbackState.message && (
                  <p className="mt-2 text-xs text-zinc-400">
                    {feedbackState.message}
                  </p>
                )}
              </>
            ) : null;
          const forcedLabel = msg.forcedProvider
            ? `/${msg.forcedProvider}`
            : msg.forcedTool
              ? `/${msg.forcedTool}`
              : null;

          return (
            <div key={msg.bubbleId}>
              <ConversationBubble
                role={msg.role}
                timestamp={msg.timestamp}
                text={msg.text}
                status={msg.status}
                requestId={msg.role === "assistant" ? msg.requestId ?? undefined : undefined}
                isSelected={isSelected}
                pending={msg.pending}
                onSelect={handleSelect}
                footerActions={feedbackActions}
                footerExtra={feedbackExtra}
                forcedLabel={forcedLabel}
                modeLabel={msg.modeLabel}
                sourceLabel={msg.sourceLabel}
                contextUsed={msg.contextUsed ?? undefined}
              />
            </div>
          );
        })}
        {historyLoading && (
          <p className="text-hint">Odświeżam historię…</p>
        )}
      </>
    ),
    [
      chatMessages,
      selectedRequestId,
      onOpenRequestDetail,
      feedbackByRequest,
      feedbackSubmittingId,
      onFeedbackClick,
      onFeedbackSubmit,
      onUpdateFeedbackState,
      historyLoading,
    ],
  );

  return content;
}
