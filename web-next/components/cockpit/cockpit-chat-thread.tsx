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
import { ApiError } from "@/lib/api-client";
import {
  activateAdapter,
  auditAdapters,
  type AdapterAuditItem,
  deactivateAdapter,
  getUnifiedModelCatalog,
  resolveAcademyApiErrorMessage,
} from "@/lib/academy-api";
import {
  buildCockpitAdapterOptions,
  isBlockedCockpitAdapterAudit,
} from "@/lib/academy-adapter-options";
import { normalizeRuntimeId } from "@/lib/cockpit-runtime-selection";
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
  activeRuntimeModel?: string;
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

function resolveSelectedCanonicalModel(
  selectedLlmModel: string,
  llmModelMetadata?: Record<string, { canonical_model_id?: string | null }>,
): string {
  return String(llmModelMetadata?.[selectedLlmModel]?.canonical_model_id || selectedLlmModel || "")
    .trim()
    .toLowerCase();
}

function resolveScopedAdapters(
  catalog: Awaited<ReturnType<typeof getUnifiedModelCatalog>>,
  selectedRuntimeId: string,
  selectedCanonical: string,
) {
  const byRuntimeModel = catalog.adapter_catalog.by_runtime_model || {};
  const byRuntime = catalog.adapter_catalog.by_runtime || {};
  const scopedByModel = selectedRuntimeId
    ? byRuntimeModel?.[selectedRuntimeId]?.[selectedCanonical]
    : undefined;
  const scopedByRuntime = (selectedRuntimeId ? byRuntime?.[selectedRuntimeId] : []) || [];
  if (selectedCanonical.length > 0) {
    if (Array.isArray(scopedByModel) && scopedByModel.length > 0) {
      return scopedByModel;
    }
    return scopedByRuntime;
  }
  return scopedByRuntime;
}

function buildAdapterAuditMap(adapters: AdapterAuditItem[]): Record<string, AdapterAuditItem> {
  return adapters.reduce<Record<string, AdapterAuditItem>>((acc, item) => {
    acc[item.adapter_id] = item;
    return acc;
  }, {});
}

async function switchCockpitAdapterSelection({
  value,
  baseModelAdapterValue,
  adapters,
  applySelectedModel,
  selectedRuntimeId,
  selectedLlmModel,
}: {
  value: string;
  baseModelAdapterValue: string;
  adapters: Array<{
    adapter_id: string;
    adapter_path: string;
    base_model: string;
    canonical_base_model_id?: string;
  }>;
  applySelectedModel?: () => Promise<boolean>;
  selectedRuntimeId: string;
  selectedLlmModel: string;
}): Promise<{ chatModel: string | null }> {
  if (value === baseModelAdapterValue) {
    await deactivateAdapter({ deploy_to_chat_runtime: false });
    if (applySelectedModel) {
      await applySelectedModel();
    }
    return { chatModel: null };
  }
  const adapter = adapters.find((entry) => entry.adapter_id === value);
  if (!adapter) {
    return { chatModel: null };
  }
  const requestedRuntime = selectedRuntimeId.trim();
  const selectedModel = selectedLlmModel.trim();
  const adapterBaseModel = String(
    adapter.canonical_base_model_id || adapter.base_model || "",
  ).trim();
  const runtimeKey = requestedRuntime.toLowerCase();
  const requestedModel =
    runtimeKey === "onnx"
      ? adapterBaseModel || selectedModel
      : selectedModel || adapterBaseModel;
  if (!requestedRuntime) {
    throw new Error("ADAPTER_RUNTIME_REQUIRED: Select target runtime before adapter activation.");
  }
  if (!requestedModel) {
    throw new Error("ADAPTER_RUNTIME_MODEL_REQUIRED: Select runtime model before adapter activation.");
  }
  const activateForModel = async (modelId: string) =>
    activateAdapter({
      adapter_id: adapter.adapter_id,
      adapter_path: adapter.adapter_path,
      runtime_id: requestedRuntime,
      model_id: modelId,
      deploy_to_chat_runtime: true,
    });
  let activation;
  try {
    activation = await activateForModel(requestedModel);
  } catch (error) {
    const shouldRetryWithAdapterBase =
      error instanceof ApiError &&
      error.status === 400 &&
      Boolean(selectedModel) &&
      Boolean(adapterBaseModel) &&
      selectedModel !== adapterBaseModel;
    if (!shouldRetryWithAdapterBase) {
      throw error;
    }
    activation = await activateForModel(adapterBaseModel);
  }
  return {
    chatModel: String(activation.chat_model || "").trim() || requestedModel || adapterBaseModel,
  };
}

function useChatAdapterSelection({
  adapterDeploySupported,
  applySelectedModel,
  llmModelMetadata,
  selectedLlmModel,
  selectedRuntimeId,
  t,
}: {
  adapterDeploySupported: boolean;
  applySelectedModel?: () => Promise<boolean>;
  llmModelMetadata?: Record<string, { canonical_model_id?: string | null }>;
  selectedLlmModel: string;
  selectedRuntimeId: string;
  t: ReturnType<typeof useTranslation>;
}) {
  const baseModelAdapterValue = "__base_model__";
  const noModelOptionValue = "__none__";
  const [adapterSelectLoading, setAdapterSelectLoading] = useState(false);
  const [adapterMutationPending, setAdapterMutationPending] = useState(false);
  const [adapterMutationError, setAdapterMutationError] = useState("");
  const [adapterAuditById, setAdapterAuditById] = useState<Record<string, AdapterAuditItem>>({});
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
  const [selectedAdapter, setSelectedAdapter] = useState(baseModelAdapterValue);

  const adapterOptions = useMemo<SelectMenuOption[]>(() => {
    return buildCockpitAdapterOptions({
      adapters,
      auditById: adapterAuditById,
      adapterDeploySupported,
      baseOptionValue: baseModelAdapterValue,
      baseOptionLabel: t("cockpit.models.adapterBase"),
      compatibleLabel: t("cockpit.models.adapterCompatible"),
      blockedLabel: t("cockpit.models.adapterBlocked"),
      unknownStatusLabel: t("cockpit.models.adapterStatusUnknown"),
    });
  }, [adapterAuditById, adapterDeploySupported, adapters, baseModelAdapterValue, t]);

  const activeAdapterAudit = useMemo(
    () => Object.values(adapterAuditById).find((item) => item.is_active) ?? null,
    [adapterAuditById],
  );

  const activeAdapterBlocked = isBlockedCockpitAdapterAudit(activeAdapterAudit);

  const loadAdapters = useCallback(async () => {
    try {
      setAdapterSelectLoading(true);
      const catalog = await getUnifiedModelCatalog();
      const selectedCanonical = resolveSelectedCanonicalModel(selectedLlmModel, llmModelMetadata);
      const next = resolveScopedAdapters(catalog, selectedRuntimeId, selectedCanonical);
      setAdapters(next);
      const active = next.find((adapter) => adapter.is_active);
      setSelectedAdapter(active?.adapter_id ?? baseModelAdapterValue);
    } catch (error) {
      console.error("Failed to load Academy adapters for chat selector:", error);
    } finally {
      setAdapterSelectLoading(false);
    }
  }, [baseModelAdapterValue, llmModelMetadata, selectedLlmModel, selectedRuntimeId]);

  useEffect(() => {
    loadAdapters().catch((error) => {
      console.error("Failed to initialize adapter selector dependencies:", error);
    });
  }, [loadAdapters]);

  useEffect(() => {
    if (!adapterDeploySupported && selectedAdapter !== baseModelAdapterValue) {
      setSelectedAdapter(baseModelAdapterValue);
    }
  }, [adapterDeploySupported, baseModelAdapterValue, selectedAdapter]);

  useEffect(() => {
    if (!adapterDeploySupported || !selectedRuntimeId || !selectedLlmModel) {
      setAdapterAuditById({});
      setSelectedAdapter(baseModelAdapterValue);
      return;
    }
    async function loadAdapterAudit() {
      try {
        const payload = await auditAdapters({
          runtime_id: selectedRuntimeId,
          model_id: selectedLlmModel,
        });
        const auditedAdapters = payload.adapters ?? [];
        setAdapterAuditById(buildAdapterAuditMap(auditedAdapters));
        const activeAudited = auditedAdapters.find((item) => item.is_active);
        setSelectedAdapter(activeAudited?.adapter_id ?? baseModelAdapterValue);
      } catch (error) {
        console.error("Failed to load adapter audit for chat selector:", error);
        setAdapterAuditById({});
        setSelectedAdapter(baseModelAdapterValue);
      }
    }
    loadAdapterAudit().catch((error) => {
      console.error("Failed to refresh adapter audit for chat selector:", error);
    });
  }, [
    adapterDeploySupported,
    baseModelAdapterValue,
    selectedLlmModel,
    selectedRuntimeId,
  ]);

  useEffect(() => {
    if (!adapterOptions.some((option) => option.value === selectedAdapter)) {
      setSelectedAdapter(baseModelAdapterValue);
    }
  }, [adapterOptions, baseModelAdapterValue, selectedAdapter]);

  const handleAdapterSelect = useCallback(
    async (value: string) => {
      const option = adapterOptions.find((entry) => entry.value === value);
      if (option?.disabled) {
        const blockedAudit = adapterAuditById[value];
        if (isBlockedCockpitAdapterAudit(blockedAudit)) {
          setAdapterMutationError(blockedAudit?.message || t("cockpit.models.adapterBlocked"));
        }
        return;
      }
      setSelectedAdapter(value);
      try {
        setAdapterMutationError("");
        setAdapterMutationPending(true);
        await switchCockpitAdapterSelection({
          value,
          baseModelAdapterValue,
          adapters,
          applySelectedModel,
          selectedRuntimeId,
          selectedLlmModel,
        });
        await loadAdapters();
      } catch (error) {
        console.error("Failed to switch Academy adapter from chat selector:", error);
        const resolved = resolveAcademyApiErrorMessage(error);
        setAdapterMutationError(resolved || t("academy.common.unknownError"));
        await loadAdapters();
      } finally {
        setAdapterMutationPending(false);
      }
    },
    [
      adapterAuditById,
      adapterOptions,
      adapters,
      applySelectedModel,
      baseModelAdapterValue,
      loadAdapters,
      selectedLlmModel,
      selectedRuntimeId,
      t,
    ],
  );

  return {
    adapterOptions,
    adapterSelectLoading,
    adapterMutationPending,
    adapterMutationError,
    activeAdapterAudit,
    activeAdapterBlocked,
    selectedAdapter,
    setSelectedAdapter,
    handleAdapterSelect,
    baseModelAdapterValue,
    noModelOptionValue,
  };
}

type ComposerLayoutClasses = {
  labelClassName: string;
  controlsWrapperClassName: string;
  selectsRowClassName: string;
  secondaryRowClassName: string;
  controlStackClassName: string;
  modelControlClassName: string;
  actionsClassName: string;
};

function resolveComposerLayoutClasses(compactControls: boolean): ComposerLayoutClasses {
  if (compactControls) {
    return {
      labelClassName: "sr-only",
      controlsWrapperClassName: "mt-2 flex flex-wrap items-center gap-2",
      selectsRowClassName: "flex flex-wrap items-center gap-2",
      secondaryRowClassName: "flex flex-wrap items-center gap-2",
      controlStackClassName: "flex min-w-[150px] flex-1 flex-col gap-2",
      modelControlClassName: "flex min-w-[150px] flex-1 flex-col gap-2",
      actionsClassName: "ml-auto flex flex-wrap items-center gap-2",
    };
  }

  return {
    labelClassName: "text-caption shrink-0 whitespace-nowrap",
    controlsWrapperClassName: "mt-2 grid w-full max-w-full gap-2",
    selectsRowClassName: "flex flex-wrap items-center gap-3",
    secondaryRowClassName: "flex w-full flex-wrap items-center gap-2",
    controlStackClassName: "flex min-w-0 items-center gap-1.5",
    modelControlClassName: "flex min-w-0 items-center gap-1.5",
    actionsClassName: "ml-auto flex flex-wrap items-center justify-end gap-2",
  };
}

async function applyModelSelectionChange({
  value,
  noModelOptionValue,
  selectedLlmModel,
  selectedAdapter,
  baseModelAdapterValue,
  handleAdapterSelect,
  onActivateModel,
  setSelectedLlmModel,
}: {
  value: string;
  noModelOptionValue: string;
  selectedLlmModel: string;
  selectedAdapter: string;
  baseModelAdapterValue: string;
  handleAdapterSelect: (value: string) => Promise<void>;
  onActivateModel?: (value: string) => Promise<boolean> | boolean;
  setSelectedLlmModel: (value: string) => void;
}) {
  const normalizedValue = value === noModelOptionValue ? "" : value;
  if (normalizedValue === selectedLlmModel) {
    return;
  }
  if (!normalizedValue) {
    setSelectedLlmModel("");
    return;
  }
  if (selectedAdapter !== baseModelAdapterValue) {
    await handleAdapterSelect(baseModelAdapterValue);
  }
  if (!onActivateModel) {
    setSelectedLlmModel(normalizedValue);
    return;
  }
  await onActivateModel(normalizedValue);
}

function suggestionOptionClassName(isActive: boolean): string {
  if (isActive) {
    return "flex w-full items-center justify-between px-3 py-2 text-left text-xs transition bg-[color:var(--ui-menu-item-active)] text-[color:var(--text-primary)]";
  }
  return "flex w-full items-center justify-between px-3 py-2 text-left text-xs transition text-[color:var(--text-secondary)] hover:bg-[color:var(--ui-surface-hover)]";
}

function withRuntimeModelContextOption({
  options,
  selectedBaseModelValue,
  activeRuntimeModelValue,
  noModelOptionValue,
  noModelLabel,
  activeRuntimeModelLabel,
}: {
  options: SelectMenuOption[];
  selectedBaseModelValue: string;
  activeRuntimeModelValue: string;
  noModelOptionValue: string;
  noModelLabel: string;
  activeRuntimeModelLabel: string;
}): SelectMenuOption[] {
  if (selectedBaseModelValue || !activeRuntimeModelValue) {
    return options;
  }
  const noSelectionLabel = `${noModelLabel} · ${activeRuntimeModelLabel}: ${activeRuntimeModelValue}`;
  return options.map((option) =>
    option.value === noModelOptionValue
      ? { ...option, label: noSelectionLabel }
      : option,
  );
}

function resolveApplySelectedModelCallback({
  onActivateModel,
  selectedLlmModel,
}: {
  onActivateModel?: (value: string) => Promise<boolean> | boolean;
  selectedLlmModel: string;
}): (() => Promise<boolean>) | undefined {
  if (!onActivateModel) {
    return undefined;
  }
  return async () => {
    if (!selectedLlmModel) {
      return false;
    }
    return Boolean(await onActivateModel(selectedLlmModel));
  };
}

function createTextareaKeyDownHandler({
  event,
  slashSuggestions,
  slashIndex,
  setSlashIndex,
  applySlashSuggestion,
  setSlashSuggestions,
  handleSendClick,
}: {
  event: KeyboardEvent<HTMLTextAreaElement>;
  slashSuggestions: SlashCommand[];
  slashIndex: number;
  setSlashIndex: (value: number | ((prev: number) => number)) => void;
  applySlashSuggestion: (suggestion: SlashCommand) => void;
  setSlashSuggestions: (
    value: SlashCommand[] | ((prev: SlashCommand[]) => SlashCommand[]),
  ) => void;
  handleSendClick: () => void;
}): void {
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
  const isEnterWithModifier =
    event.key === "Enter" && (event.ctrlKey || event.metaKey);
  if (isEnterWithModifier) {
    event.preventDefault();
    handleSendClick();
  }
}

type ActiveAdapterRuntimeCardProps = Readonly<{
  activeAdapterAudit: AdapterAuditItem | null;
  activeAdapterBlocked: boolean;
  t: ReturnType<typeof useTranslation>;
}>;

function ActiveAdapterRuntimeCard({
  activeAdapterAudit,
  activeAdapterBlocked,
  t,
}: ActiveAdapterRuntimeCardProps) {
  const activeAdapterStateLabel = activeAdapterBlocked
    ? t("cockpit.models.activeAdapterBlocked")
    : t("cockpit.models.activeAdapterCompatible");
  const activeAdapterStateClass = activeAdapterBlocked ? "mt-1 text-amber-300" : "mt-1 text-emerald-300";

  return (
    <div className="rounded-lg border border-white/10 bg-black/10 p-2 text-[11px] text-theme-muted">
      <p className="font-medium text-[color:var(--text-primary)]">
        {t("cockpit.models.activeAdapterLabel")}
      </p>
      {activeAdapterAudit ? (
        <>
          <p className="mt-1 font-mono text-[color:var(--text-primary)]">
            {activeAdapterAudit.adapter_id}
          </p>
          <p className="mt-1">
            {t("academy.adapters.baseModel")}: {activeAdapterAudit.base_model}
          </p>
          <p className={activeAdapterStateClass}>{activeAdapterStateLabel}</p>
          <p className="mt-1">{activeAdapterAudit.message}</p>
          {activeAdapterBlocked ? (
            <p className="mt-1 text-amber-200">
              {t("cockpit.models.activeAdapterSwitchHint")}
            </p>
          ) : null}
        </>
      ) : (
        <p className="mt-1">{t("cockpit.models.activeAdapterNone")}</p>
      )}
    </div>
  );
}

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
      activeRuntimeModel,
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
    const selectedRuntimeId = useMemo(
      () => normalizeRuntimeId(selectedLlmServer).toLowerCase(),
      [selectedLlmServer],
    );
    const applySelectedModel = useMemo(
      () =>
        resolveApplySelectedModelCallback({
          onActivateModel,
          selectedLlmModel,
        }),
      [onActivateModel, selectedLlmModel],
    );

    const {
      adapterOptions,
      adapterSelectLoading,
      adapterMutationPending,
      adapterMutationError,
      activeAdapterAudit,
      activeAdapterBlocked,
      selectedAdapter,
      handleAdapterSelect,
      baseModelAdapterValue,
      noModelOptionValue,
    } = useChatAdapterSelection({
      adapterDeploySupported,
      applySelectedModel,
      llmModelMetadata,
      selectedLlmModel,
      selectedRuntimeId,
      t,
    });

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
        createTextareaKeyDownHandler({
          event,
          slashSuggestions,
          slashIndex,
          setSlashIndex,
          applySlashSuggestion,
          setSlashSuggestions,
          handleSendClick,
        });
      },
      [applySlashSuggestion, handleSendClick, slashIndex, slashSuggestions],
    );

    const {
      labelClassName,
      controlsWrapperClassName,
      selectsRowClassName,
      secondaryRowClassName,
      controlStackClassName,
      modelControlClassName,
      actionsClassName,
    } = useMemo(() => resolveComposerLayoutClasses(compactControls), [compactControls]);
    const adapterDeployUnsupported = adapterDeploySupported === false;
    const showAdapterRuntimeContext = Boolean(
      adapterDeploySupported && selectedRuntimeId && selectedLlmModel,
    );
    const activeRuntimeModelValue = (activeRuntimeModel || "").trim();
    const selectedBaseModelValue = (selectedLlmModel || "").trim();
    const showActiveRuntimeModelContext = Boolean(activeRuntimeModelValue);
    const llmModelOptionsWithRuntimeContext = useMemo(
      () =>
        withRuntimeModelContextOption({
          options: llmModelOptions,
          selectedBaseModelValue,
          activeRuntimeModelValue,
          noModelOptionValue,
          noModelLabel: t("cockpit.models.noneSelected"),
          activeRuntimeModelLabel: t("cockpit.models.activeRuntimeModelLabel"),
        }),
      [
        selectedBaseModelValue,
        activeRuntimeModelValue,
        llmModelOptions,
        noModelOptionValue,
        t,
      ],
    );
    const adapterUnsupportedReason = adapterDeployReason
      || t("cockpit.models.adapterRuntimeNotSupported", { runtime: selectedLlmServer });
    const adapterSelectionHint = selectedAdapter === baseModelAdapterValue
      ? t("cockpit.models.adapterSelectionBaseHint")
      : t("cockpit.models.adapterSelectionAdapterHint");

    const handleModelSelect = useCallback((value: string) => {
      applyModelSelectionChange({
        value,
        noModelOptionValue,
        selectedLlmModel,
        selectedAdapter,
        baseModelAdapterValue,
        handleAdapterSelect,
        onActivateModel,
        setSelectedLlmModel,
      }).catch((error) => {
        console.error("Model activation action failed:", error);
      });
    }, [
      baseModelAdapterValue,
      handleAdapterSelect,
      noModelOptionValue,
      onActivateModel,
      selectedAdapter,
      selectedLlmModel,
      setSelectedLlmModel,
    ]);

    const handleAdapterMenuSelect = useCallback((value: string) => {
      handleAdapterSelect(value).catch((error) => {
        console.error("Adapter switch action failed:", error);
      });
    }, [handleAdapterSelect]);

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
                  className={suggestionOptionClassName(index === slashIndex)}
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
                optionTestIdPrefix="llm-server-option"
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
                value={selectedLlmModel || noModelOptionValue}
                options={llmModelOptionsWithRuntimeContext}
                onChange={handleModelSelect}
                ariaLabel={t("cockpit.actions.selectModel")}
                buttonTestId="llm-model-select"
                optionTestIdPrefix="llm-model-option"
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
                onChange={handleAdapterMenuSelect}
                ariaLabel={t("cockpit.actions.selectAdapter")}
                buttonTestId="chat-adapter-select"
                optionTestIdPrefix="chat-adapter-option"
                placeholder={t("cockpit.models.loadingAdapters")}
                disabled={
                  adapterSelectLoading ||
                  adapterMutationPending ||
                  adapterDeployUnsupported ||
                  !selectedRuntimeId
                }
                buttonClassName="w-full justify-between rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2.5 py-2 text-xs text-[color:var(--text-primary)] whitespace-nowrap"
                menuClassName="w-full max-h-72 overflow-y-auto"
              />
              {adapterDeployUnsupported && <p className="text-[11px] text-hint">{adapterUnsupportedReason}</p>}
              {adapterMutationError && !adapterDeployUnsupported ? (
                <p className="text-[11px] text-red-300">{adapterMutationError}</p>
              ) : null}
              {showAdapterRuntimeContext ? (
                <p className="text-[11px] text-hint">{adapterSelectionHint}</p>
              ) : null}
              {showAdapterRuntimeContext ? (
                <ActiveAdapterRuntimeCard
                  activeAdapterAudit={activeAdapterAudit}
                  activeAdapterBlocked={activeAdapterBlocked}
                  t={t}
                />
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
            {showActiveRuntimeModelContext ? (
              <p className="text-[11px] text-hint">
                <span className="font-medium">{t("cockpit.models.activeRuntimeModelLabel")}:</span>{" "}
                <span className="font-mono text-[color:var(--text-primary)]">{activeRuntimeModelValue}</span>
                {selectedBaseModelValue ? (
                  <>
                    {" "}
                    <span className="font-medium">{t("cockpit.models.selectedBaseModelLabel")}:</span>{" "}
                    <span className="font-mono text-[color:var(--text-primary)]">{selectedBaseModelValue}</span>
                  </>
                ) : null}
              </p>
            ) : null}
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
