"use client";

import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
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
import { filterSlashSuggestions, filterAgentSuggestions } from "@/lib/slash-commands";
import type { SlashCommand } from "@/lib/slash-commands";
import {
  activateAdapter,
  deactivateAdapter,
  getUnifiedModelCatalog,
} from "@/lib/academy-api";
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
  policyBlocked?: boolean;
  reasonCode?: string | null;
  userMessage?: string | null;
};

export type ChatComposerHandle = {
  setDraft: (value: string) => void;
};

type ChatComposerProps = Readonly<{
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
  llmModelMetadata?: Record<string, { canonical_model_id?: string | null }>;
  setSelectedLlmModel: (value: string) => void;
  onActivateModel?: (value: string) => Promise<boolean> | boolean;
  hasModels: boolean;
  onOpenTuning: () => void;
  tuningLabel: string;
  adapterDeploySupported: boolean;
  adapterDeployReason?: string | null;
  modelAuditIssuesCount?: number;
  compactControls?: boolean;
}>;

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
      llmModelMetadata,
      setSelectedLlmModel,
      onActivateModel,
      hasModels,
      onOpenTuning,
      tuningLabel,
      adapterDeploySupported,
      adapterDeployReason,
      modelAuditIssuesCount = 0,
      compactControls = false,
    },
    ref,
  ) {
    const BASE_MODEL_ADAPTER_VALUE = "__base_model__";
    const t = useTranslation();
    const [draft, setDraft] = useState("");
    const [adapterSelectLoading, setAdapterSelectLoading] = useState(false);
    const [adapterMutationPending, setAdapterMutationPending] = useState(false);
    const [adapters, setAdapters] = useState<
      Array<{
        adapter_id: string;
        adapter_path: string;
        base_model: string;
        canonical_base_model_id?: string;
        is_active: boolean;
        compatible_runtimes?: string[];
      }>
    >([]);
    const [selectedAdapter, setSelectedAdapter] = useState(BASE_MODEL_ADAPTER_VALUE);
    const [slashSuggestions, setSlashSuggestions] = useState<SlashCommand[]>([]);
    const [slashIndex, setSlashIndex] = useState(0);
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);
    const chatModeOptions: SelectMenuOption[] = [
      { value: "direct", label: t("cockpit.modes.directLabel") },
      { value: "normal", label: t("cockpit.modes.normalLabel") },
      { value: "complex", label: t("cockpit.modes.complexLabel") },
    ];
    const selectedRuntimeId = useMemo(
      () => selectedLlmServer.trim().toLowerCase(),
      [selectedLlmServer],
    );

    const adapterOptions = useMemo<SelectMenuOption[]>(() => {
      const baseOption: SelectMenuOption = {
        value: BASE_MODEL_ADAPTER_VALUE,
        label: t("cockpit.models.adapterBase"),
      };
      if (!adapterDeploySupported) {
        return [baseOption];
      }
      return [
        baseOption,
        ...adapters.map((adapter) => ({
          value: adapter.adapter_id,
          label: adapter.adapter_id,
          description: adapter.base_model,
        })),
      ];
    }, [adapterDeploySupported, adapters, t]);

    const loadAdapters = useCallback(async () => {
      try {
        setAdapterSelectLoading(true);
        const catalog = await getUnifiedModelCatalog();
        const selectedModelMeta = llmModelMetadata?.[selectedLlmModel];
        const selectedCanonical = String(
          selectedModelMeta?.canonical_model_id || selectedLlmModel || "",
        )
          .trim()
          .toLowerCase();
        const byRuntimeModel = catalog.adapter_catalog.by_runtime_model || {};
        const byRuntime = catalog.adapter_catalog.by_runtime || {};
        const scopedByModel =
          (selectedRuntimeId && selectedCanonical
            ? byRuntimeModel?.[selectedRuntimeId]?.[selectedCanonical]
            : []) || [];
        const scopedByRuntime =
          (selectedRuntimeId ? byRuntime?.[selectedRuntimeId] : []) || [];
        const next = (scopedByModel.length > 0 ? scopedByModel : scopedByRuntime) || [];
        setAdapters(next);
        const active = next.find((adapter) => adapter.is_active);
        setSelectedAdapter(active?.adapter_id ?? BASE_MODEL_ADAPTER_VALUE);
      } catch (error) {
        console.error("Failed to load Academy adapters for chat selector:", error);
      } finally {
        setAdapterSelectLoading(false);
      }
    }, [llmModelMetadata, selectedLlmModel, selectedRuntimeId]);

    useEffect(() => {
      async function loadAdapterDependencies() {
        await loadAdapters();
      }
      loadAdapterDependencies().catch((error) => {
        console.error("Failed to initialize adapter selector dependencies:", error);
      });
    }, [loadAdapters]);

    useEffect(() => {
      if (!adapterDeploySupported && selectedAdapter !== BASE_MODEL_ADAPTER_VALUE) {
        setSelectedAdapter(BASE_MODEL_ADAPTER_VALUE);
      }
    }, [adapterDeploySupported, selectedAdapter]);

    useEffect(() => {
      if (adapterOptions.some((option) => option.value === selectedAdapter)) {
        return;
      }
      setSelectedAdapter(BASE_MODEL_ADAPTER_VALUE);
    }, [adapterOptions, selectedAdapter]);

    const handleAdapterSelect = useCallback(
      async (value: string) => {
        const option = adapterOptions.find((entry) => entry.value === value);
        if (option?.disabled) {
          return;
        }
        setSelectedAdapter(value);
        try {
          setAdapterMutationPending(true);
          if (value === BASE_MODEL_ADAPTER_VALUE) {
            await deactivateAdapter();
          } else {
            const adapter = adapters.find((entry) => entry.adapter_id === value);
            if (!adapter) {
              return;
            }
            await activateAdapter({
              adapter_id: adapter.adapter_id,
              adapter_path: adapter.adapter_path,
              runtime_id: selectedRuntimeId,
            });
          }
          await loadAdapters();
        } catch (error) {
          console.error("Failed to switch Academy adapter from chat selector:", error);
          await loadAdapters();
        } finally {
          setAdapterMutationPending(false);
        }
      },
      [adapterOptions, adapters, loadAdapters, selectedRuntimeId],
    );

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
        const match = current.match(/^(\s*)[@/][^\s]*/);
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
      const agentMatches = filterAgentSuggestions(value, 3);
      const matches = agentMatches.length > 0 ? agentMatches : filterSlashSuggestions(value, 3);
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
      : "flex flex-wrap items-center gap-3";
    const secondaryRowClassName = compactControls
      ? "flex flex-wrap items-center gap-2"
      : "flex w-full flex-wrap items-center gap-2";
    const controlStackClassName = compactControls
      ? "flex min-w-[150px] flex-1 flex-col gap-2"
      : "flex min-w-0 items-center gap-1.5";
    const modelControlClassName = compactControls
      ? controlStackClassName
      : "flex min-w-0 items-center gap-1.5";

    const actionsClassName = compactControls
      ? "ml-auto flex flex-wrap items-center gap-2"
      : "ml-auto flex flex-wrap items-center justify-end gap-2";

    return (
      <div className="mt-3 shrink-0 border-t border-[color:var(--ui-border)] pt-3">
        <div className="relative">
          <textarea
            ref={textareaRef}
            rows={2}
            className="min-h-[64px] w-full rounded-xl box-base p-2 text-sm text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--ui-muted)] focus:border-[color:var(--accent)] 2xl:text-base"
            placeholder={t("cockpit.inputPlaceholder")}
            value={draft}
            onChange={(event) => handleDraftChange(event.target.value)}
            onKeyDown={handleTextareaKeyDown}
            data-testid="cockpit-prompt-input"
          />
          {slashSuggestions.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-10 mt-2 overflow-hidden rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--bg-panel)] shadow-xl">
              {slashSuggestions.map((suggestion, index) => (
                <button
                  key={suggestion.id}
                  type="button"
                  onClick={() => applySlashSuggestion(suggestion)}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left text-xs transition ${index === slashIndex ? "bg-[color:var(--ui-menu-item-active)] text-[color:var(--text-primary)]" : "text-[color:var(--text-secondary)] hover:bg-[color:var(--ui-surface-hover)]"
                    }`}
                >
                  <span className="font-semibold text-[color:var(--text-heading)]">{suggestion.command}</span>
                  <span className="text-[11px] text-hint">{suggestion.detail}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className={controlsWrapperClassName}>
          <div className={selectsRowClassName}>
            <div className={controlStackClassName}>
              <label className={labelClassName}>{t("cockpit.models.server")}</label>
              <SelectMenu
                value={selectedLlmServer}
                options={llmServerOptions}
                onChange={setSelectedLlmServer}
                ariaLabel={t("cockpit.actions.selectServer")}
                buttonTestId="llm-server-select"
                placeholder={t("cockpit.models.chooseServer")}
                buttonClassName="w-full justify-between rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2.5 py-2 text-xs text-[color:var(--text-primary)] whitespace-nowrap"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
            </div>
            <div
              className={`${modelControlClassName} w-56`}
            >
              <label className={labelClassName}>{t("cockpit.models.model")}</label>
              <SelectMenu
                value={selectedLlmModel}
                options={llmModelOptions}
                onChange={(value) => {
                  if (!value || value === selectedLlmModel) {
                    return;
                  }
                  if (!onActivateModel) {
                    setSelectedLlmModel(value);
                    return;
                  }
                  Promise.resolve(onActivateModel(value)).catch((error) => {
                    console.error("Model activation action failed:", error);
                  });
                }}
                ariaLabel={t("cockpit.actions.selectModel")}
                buttonTestId="llm-model-select"
                placeholder={t("cockpit.models.noModels")}
                disabled={!hasModels}
                menuWidth="content"
                buttonClassName="w-full justify-between rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2.5 py-2 text-xs text-[color:var(--text-primary)] whitespace-nowrap overflow-hidden text-ellipsis"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
            </div>
            <div className={controlStackClassName}>
              <label className={labelClassName}>{t("cockpit.models.adapter")}</label>
              <SelectMenu
                value={selectedAdapter}
                options={adapterOptions}
                onChange={(value) => {
                  handleAdapterSelect(value).catch((error) => {
                    console.error("Adapter switch action failed:", error);
                  });
                }}
                ariaLabel={t("cockpit.actions.selectAdapter")}
                buttonTestId="chat-adapter-select"
                placeholder={t("cockpit.models.loadingAdapters")}
                disabled={
                  adapterSelectLoading || adapterMutationPending || !adapterDeploySupported
                }
                buttonClassName="w-full justify-between rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2.5 py-2 text-xs text-[color:var(--text-primary)] whitespace-nowrap"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
              {!adapterDeploySupported ? (
                <p className="text-[11px] text-hint">
                  {adapterDeployReason ||
                    t("cockpit.models.adapterRuntimeNotSupported", {
                      runtime: selectedLlmServer,
                    })}
                </p>
              ) : null}
            </div>
            <div className={controlStackClassName}>
              <label className={labelClassName}>{t("cockpit.modes.mode")}</label>
              <SelectMenu
                value={chatMode}
                options={chatModeOptions}
                onChange={(value) => setChatMode(value as ChatMode)}
                ariaLabel={t("cockpit.actions.selectMode")}
                buttonTestId="chat-mode-select"
                menuTestId="chat-mode-menu"
                optionTestIdPrefix="chat-mode-option"
                buttonClassName="w-full justify-between rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2.5 py-2 text-xs text-[color:var(--text-primary)] whitespace-nowrap"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
            </div>
          </div>
          <div className={secondaryRowClassName}>
            {modelAuditIssuesCount > 0 ? (
              <p className="text-[11px] text-amber-300">
                {t("cockpit.models.runtimeModelAuditWarning", {
                  count: String(modelAuditIssuesCount),
                })}
              </p>
            ) : null}
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={labMode}
                onChange={(event) => setLabMode(event.target.checked)}
              />
              {t("cockpit.modes.labMode")}
            </label>
            <div className={actionsClassName}>
              <Button
                variant="outline"
                size="sm"
                onClick={onOpenTuning}
                className="border-emerald-400/40 bg-emerald-500/10 text-emerald-200 hover:border-emerald-300/70 hover:bg-emerald-500/20 hover:text-white"
                title={t("cockpit.actions.tuning")}
              >
                <Settings className="h-4 w-4 mr-1" />
                {tuningLabel}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDraft("")}
                className="text-[color:var(--text-secondary)]"
              >
                {t("cockpit.actions.clear")}
              </Button>
              <Button
                onClick={handleSendClick}
                disabled={sending}
                size="sm"
                variant="macro"
                className="px-6"
                data-testid="cockpit-send-button"
              >
                {sending ? t("cockpit.actions.sending") : t("cockpit.actions.send")}
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

type CockpitChatThreadProps = Readonly<{
  chatMessages: ChatMessage[];
  selectedRequestId: string | null;
  historyLoading: boolean;
  feedbackByRequest: Record<string, FeedbackState>;
  feedbackSubmittingId: string | null;
  onOpenRequestDetail: (requestId: string, prompt?: string) => void;
  onFeedbackClick: (requestId: string, rating: "up" | "down") => void;
  onFeedbackSubmit: (requestId: string) => void;
  onUpdateFeedbackState: (requestId: string, patch: Partial<FeedbackState>) => void;
}>;

type CockpitThreadItemProps = Readonly<{
  msg: ChatMessage;
  isSelected: boolean;
  t: ReturnType<typeof useTranslation>;
  feedbackState?: FeedbackState;
  feedbackSubmittingId: string | null;
  onOpenRequestDetail: (requestId: string, prompt?: string) => void;
  onFeedbackClick: (requestId: string, rating: "up" | "down") => void;
  onFeedbackSubmit: (requestId: string) => void;
  onUpdateFeedbackState: (requestId: string, patch: Partial<FeedbackState>) => void;
}>;

const getForcedLabel = (msg: ChatMessage): string | null => {
  if (msg.forcedProvider) return `@${msg.forcedProvider}`;
  if (msg.forcedTool) return `/${msg.forcedTool}`;
  return null;
};

function renderFeedbackActions(input: {
  msg: ChatMessage;
  requestId: string | null;
  feedbackState?: FeedbackState;
  feedbackSubmittingId: string | null;
  feedbackLocked: boolean;
  t: ReturnType<typeof useTranslation>;
  onFeedbackClick: (requestId: string, rating: "up" | "down") => void;
  onFeedbackSubmit: (requestId: string) => void;
}) {
  const {
    msg,
    requestId,
    feedbackState,
    feedbackSubmittingId,
    feedbackLocked,
    t,
    onFeedbackClick,
    onFeedbackSubmit,
  } = input;
  if (msg.role !== "assistant" || !requestId) return null;
  return (
    <div className="flex items-center gap-2">
      <IconButton
        label={t("cockpit.feedback.up")}
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
        label={t("cockpit.feedback.down")}
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
          {feedbackSubmittingId === requestId
            ? t("cockpit.feedback.submitting")
            : t("cockpit.feedback.submit")}
        </Button>
      ) : null}
    </div>
  );
}

function renderFeedbackExtra(input: {
  msg: ChatMessage;
  requestId: string | null;
  feedbackState?: FeedbackState;
  t: ReturnType<typeof useTranslation>;
  onUpdateFeedbackState: (requestId: string, patch: Partial<FeedbackState>) => void;
}) {
  const { msg, requestId, feedbackState, t, onUpdateFeedbackState } = input;
  if (msg.role !== "assistant" || !requestId || msg.pending || feedbackState?.rating !== "down") return null;
  return (
    <>
      <textarea
        className="min-h-[70px] w-full rounded-2xl box-muted px-3 py-2 text-xs text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--ui-muted)]"
        placeholder={t("cockpit.feedback.placeholder")}
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
  );
}

function CockpitThreadItem({
  msg,
  isSelected,
  t,
  feedbackState,
  feedbackSubmittingId,
  onOpenRequestDetail,
  onFeedbackClick,
  onFeedbackSubmit,
  onUpdateFeedbackState,
}: CockpitThreadItemProps) {
  const requestId = msg.requestId;
  const canInspect = Boolean(requestId) && !msg.pending;
  const handleSelect =
    canInspect && requestId
      ? () => onOpenRequestDetail(requestId, msg.prompt)
      : undefined;
  const feedbackLocked = Boolean(feedbackState?.rating);
  const forcedLabel = getForcedLabel(msg);

  const feedbackActions = renderFeedbackActions({
    msg,
    requestId,
    feedbackState,
    feedbackSubmittingId,
    feedbackLocked,
    t,
    onFeedbackClick,
    onFeedbackSubmit,
  });

  const feedbackExtra = renderFeedbackExtra({
    msg,
    requestId,
    feedbackState,
    t,
    onUpdateFeedbackState,
  });

  return (
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
      policyBlocked={msg.policyBlocked}
      reasonCode={msg.reasonCode}
      userMessage={msg.userMessage}
    />
  );
}

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
  const t = useTranslation();

  const content = useMemo(
    () => (
      <>
        {chatMessages.length === 0 && (
          <p className="text-sm text-hint">
            {t("cockpit.history.empty")}
          </p>
        )}
        {chatMessages.map((msg) => {
          const requestId = msg.requestId;
          const feedbackState =
            msg.role === "assistant" && requestId ? feedbackByRequest[requestId] : undefined;
          return (
            <div key={msg.bubbleId}>
              <CockpitThreadItem
                msg={msg}
                isSelected={selectedRequestId === requestId}
                t={t}
                feedbackState={feedbackState}
                feedbackSubmittingId={feedbackSubmittingId}
                onOpenRequestDetail={onOpenRequestDetail}
                onFeedbackClick={onFeedbackClick}
                onFeedbackSubmit={onFeedbackSubmit}
                onUpdateFeedbackState={onUpdateFeedbackState}
              />
            </div>
          );
        })}
        {historyLoading && (
          <p className="text-hint">{t("cockpit.history.refreshing")}</p>
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
      t,
    ],
  );

  return content;
}
