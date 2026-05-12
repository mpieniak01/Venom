"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ConfirmDialog,
  ConfirmDialogActions,
  ConfirmDialogContent,
  ConfirmDialogDescription,
  ConfirmDialogTitle,
  ConfirmDialogTrigger,
} from "@/components/ui/confirm-dialog";
import { Switch } from "@/components/ui/switch";
import { useTranslation } from "@/lib/i18n";
import type { DaemonConfigRequest } from "@/lib/gemma4-daemon-api";
import { type Gemma4DaemonState, useGemma4Daemon } from "@/hooks/use-gemma4-daemon";

const CACHE_OPTIONS = [
  { value: "", label: "default" },
  { value: "static", label: "static" },
  { value: "quantized", label: "quantized" },
  { value: "offloaded_static", label: "offloaded_static" },
] as const;

type Variant = "cockpit" | "voice";

type RuntimeSnapshotLike = Readonly<{
  runtime_id?: string | null;
  provider?: string | null;
  model_name?: string | null;
  endpoint?: string | null;
  config_hash?: string | null;
  runtime_capabilities?: {
    compatibility_profile?: string | null;
    probe_status?: string | null;
    capabilities?: Record<string, boolean | string | null | undefined>;
    probes?: Record<string, { status?: string | null; reason?: string | null }>;
    fallbacks?: Record<string, string | null | undefined>;
  } | null;
  voice_pipeline?: {
    profile?: string | null;
    stt?: string | null;
    reasoning?: string | null;
    tools?: string | null;
    vision?: string | null;
    tts?: string | null;
    notes?: string[] | null;
  } | null;
  error?: string | null;
}> | null;

type Props = Readonly<{
  variant?: Variant;
  pollingIntervalMs?: number;
  runtimeSnapshot?: RuntimeSnapshotLike;
}>;

export function Gemma4RuntimeControl({
  variant = "voice",
  pollingIntervalMs,
  runtimeSnapshot = null,
}: Props) {
  const daemon = useGemma4Daemon(pollingIntervalMs);
  return (
    <Gemma4RuntimeControlInner
      daemon={daemon}
      variant={variant}
      runtimeSnapshot={runtimeSnapshot}
    />
  );
}

type InnerProps = Readonly<{
  daemon: Gemma4DaemonState;
  variant: Variant;
  runtimeSnapshot?: RuntimeSnapshotLike;
}>;

function vramBarColor(pct: number): string {
  if (pct > 90) return "bg-rose-500";
  if (pct > 70) return "bg-amber-400";
  return "bg-emerald-400";
}

function parseTokenInput(raw: string): number | undefined {
  const n = Number.parseInt(raw, 10);
  return Number.isNaN(n) || n <= 0 ? undefined : n;
}

export function Gemma4RuntimeControlInner({
  daemon,
  variant,
  runtimeSnapshot = null,
}: InnerProps) {
  const t = useTranslation();
  const { status, loading, error, actionPending } = daemon;

  const [localTokens, setLocalTokens] = useState<string>("");
  const [localThinking, setLocalThinking] = useState<boolean | null>(null);
  const [localCache, setLocalCache] = useState<string | null>(null);
  const [drafterInput, setDrafterInput] = useState("");
  const [showDrafterInput, setShowDrafterInput] = useState(false);

  const busy = actionPending !== null;

  const effectiveThinking = localThinking ?? status?.params.enable_thinking ?? false;
  const effectiveTokens =
    localTokens === "" ? String(status?.params.max_new_tokens ?? 128) : localTokens;
  const effectiveCache =
    localCache === null ? (status?.params.cache_implementation ?? "") : localCache;

  const hasLocalChanges = localThinking !== null || localTokens !== "" || localCache !== null;

  async function handleApply() {
    const params: DaemonConfigRequest = {};
    if (localThinking !== null) params.enable_thinking = localThinking;
    if (localTokens !== "") {
      const n = parseTokenInput(localTokens);
      if (n !== undefined) params.max_new_tokens = n;
    }
    if (localCache !== null) {
      params.cache_implementation = localCache === "" ? null : localCache;
    }
    const result = await daemon.applyConfig(params);
    if (result) {
      setLocalThinking(null);
      setLocalTokens("");
      setLocalCache(null);
    }
  }

  async function handleAttach() {
    const id = drafterInput.trim();
    if (!id) return;
    await daemon.attachAssistant(id);
    setDrafterInput("");
    setShowDrafterInput(false);
  }

  const vram = status?.vram;
  const vramPercent =
    vram && vram.total_mb > 0
      ? Math.min(100, Math.round((vram.allocated_mb / vram.total_mb) * 100))
      : null;

  if (loading && !status) {
    return (
      <DaemonCard variant={variant}>
        <p className="text-hint text-xs py-2">{t("voice.daemon.daemonLoading")}</p>
      </DaemonCard>
    );
  }

  if (error && !status) {
    const hasRuntimeSnapshot = Boolean(runtimeSnapshot?.provider || runtimeSnapshot?.model_name);
    return (
      <DaemonCard variant={variant}>
        <p className="text-xs text-rose-400 py-1">{t("voice.daemon.daemonUnavailable")}</p>
        <p className="text-[10px] text-zinc-500 truncate">{error}</p>
        {hasRuntimeSnapshot && (
          <RuntimeSnapshotSummary snapshot={runtimeSnapshot} />
        )}
      </DaemonCard>
    );
  }

  return (
    <DaemonCard variant={variant}>
      {/* Header row — model + mode badges */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-white truncate">
            {status?.target_model ?? "—"}
          </p>
          <p className="text-[10px] text-zinc-500 truncate mt-0.5">
            {t("voice.daemon.targetModel")}
          </p>
        </div>
        <div className="flex gap-1 flex-shrink-0">
          {status?.target_loaded === false && (
            <Badge tone="warning" className="text-[10px]">{t("voice.daemon.warming")}</Badge>
          )}
          {status?.mode === "target_with_assistant" && (
            <Badge tone="success" className="text-[10px]">
              {t("voice.daemon.assistantActive")}
            </Badge>
          )}
        </div>
      </div>

      {/* Pending reload banner */}
      {status?.pending_reload && (
        <div
          data-testid="reload-banner"
          className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300"
        >
          <span className="font-semibold">{t("voice.daemon.reloadRequired")}: </span>
          {status.reload_reason}
        </div>
      )}

      {runtimeSnapshot && (
        <RuntimeSnapshotSummary snapshot={runtimeSnapshot} compact />
      )}

      {/* Params */}
      <div className="space-y-2.5 mb-3">
        {/* Thinking toggle */}
        <div className="flex items-center justify-between gap-2">
          <label className="text-xs text-zinc-400">{t("voice.daemon.thinking")}</label>
          <div className="flex items-center gap-2">
            <Switch
              checked={effectiveThinking}
              onCheckedChange={(v) => setLocalThinking(v)}
              disabled={busy}
              aria-label={t("voice.daemon.thinking")}
            />
            {status && (
              <ThinkingStatusLabel localThinking={localThinking} enabled={status.params.enable_thinking} />
            )}
          </div>
        </div>

        {/* Max tokens */}
        <div className="flex items-center justify-between gap-2">
          <label className="text-xs text-zinc-400">{t("voice.daemon.maxTokens")}</label>
          <input
            type="number"
            min={1}
            max={4096}
            value={effectiveTokens}
            onChange={(e) => setLocalTokens(e.target.value)}
            disabled={busy}
            className="w-20 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-right text-xs text-white focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            aria-label={t("voice.daemon.maxTokens")}
          />
        </div>

        {/* Cache strategy */}
        <div className="flex items-center justify-between gap-2">
          <label className="text-xs text-zinc-400">{t("voice.daemon.cacheStrategy")}</label>
          <select
            value={effectiveCache}
            onChange={(e) => setLocalCache(e.target.value)}
            disabled={busy}
            className="rounded-lg border border-white/10 bg-zinc-900 px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            aria-label={t("voice.daemon.cacheStrategy")}
          >
            {CACHE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.value === "" ? t("voice.daemon.cacheDefault") : opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* VRAM */}
      {vram && (
        <VramSection vram={vram} vramPercent={vramPercent} />
      )}

      {/* Drafter */}
      <DrafterBox
        daemon={daemon}
        assistantModel={status?.assistant_model ?? null}
        busy={busy}
        actionPending={actionPending}
        drafterInput={drafterInput}
        setDrafterInput={setDrafterInput}
        showDrafterInput={showDrafterInput}
        setShowDrafterInput={setShowDrafterInput}
        onAttach={handleAttach}
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button
          size="xs"
          variant="primary"
          onClick={handleApply}
          disabled={busy || !hasLocalChanges}
          data-testid="apply-button"
        >
          {actionPending === "config"
            ? t("voice.daemon.applying")
            : t("voice.daemon.applyConfig")}
        </Button>

        {[
          {
            key: "reload",
            buttonVariant: "secondary" as const,
            actionName: "reload",
            pendingLabel: t("voice.daemon.reloading"),
            buttonLabel: t("voice.daemon.reload"),
            title: t("voice.daemon.confirmReloadTitle"),
            description: t("voice.daemon.confirmReloadDesc"),
            confirmLabel: t("voice.daemon.reload"),
            onConfirm: daemon.reload,
            testId: "reload-button",
          },
          {
            key: "restart",
            buttonVariant: "ghost" as const,
            actionName: "restart",
            pendingLabel: t("voice.daemon.restarting"),
            buttonLabel: t("voice.daemon.restart"),
            title: t("voice.daemon.confirmRestartTitle"),
            description: t("voice.daemon.confirmRestartDesc"),
            confirmLabel: t("voice.daemon.restart"),
            confirmVariant: "danger" as const,
            onConfirm: daemon.restart,
            testId: "restart-button",
          },
        ].map((action) => (
          <DaemonConfirmActionButton
            key={action.key}
            buttonVariant={action.buttonVariant}
            busy={busy}
            actionPending={actionPending}
            actionName={action.actionName}
            pendingLabel={action.pendingLabel}
            buttonLabel={action.buttonLabel}
            title={action.title}
            description={action.description}
            confirmLabel={action.confirmLabel}
            confirmVariant={action.confirmVariant}
            onConfirm={action.onConfirm}
            testId={action.testId}
          />
        ))}

        <Button
          size="xs"
          variant="ghost"
          onClick={daemon.fallback}
          disabled={busy}
          data-testid="fallback-button"
        >
          {actionPending === "fallback" ? t("voice.daemon.busy") : t("voice.daemon.fallback")}
        </Button>
      </div>

      {/* Last signal feedback */}
      {daemon.lastAppliedSignal && daemon.lastAppliedSignal !== "none" && (
        <p className="mt-2 text-[10px] text-amber-300">
          {daemon.lastAppliedSignal === "soft_reload"
            ? t("voice.daemon.signalReload")
            : t("voice.daemon.signalRestart")}
        </p>
      )}

      {error && (
        <p className="mt-2 text-[10px] text-rose-400 truncate">{error}</p>
      )}
    </DaemonCard>
  );
}

// ── Sub-components extracted to reduce cognitive complexity ───────────────────

function ThinkingStatusLabel({
  localThinking,
  enabled,
}: Readonly<{ localThinking: boolean | null; enabled: boolean }>) {
  const t = useTranslation();
  if (localThinking !== null) {
    return <span className="text-[10px] text-zinc-500">{t("voice.daemon.signalLive")}</span>;
  }
  const label = enabled ? t("voice.daemon.thinkingOn") : t("voice.daemon.thinkingOff");
  return <span className="text-[10px] text-zinc-500">{label}</span>;
}

type VramInfo = Readonly<{
  backend: string;
  allocated_mb: number;
  total_mb: number;
}>;

function VramSection({
  vram,
  vramPercent,
}: Readonly<{ vram: VramInfo; vramPercent: number | null }>) {
  const t = useTranslation();
  const label =
    vram.backend === "cuda"
      ? `${vram.allocated_mb} / ${vram.total_mb} MB`
      : t("voice.daemon.vramCpu");

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          {t("voice.daemon.vram")}
        </span>
        <span className="text-[10px] text-zinc-400">{label}</span>
      </div>
      {vram.backend === "cuda" && vramPercent !== null && (
        <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
          <div
            data-testid="vram-bar"
            className={`h-full rounded-full transition-all ${vramBarColor(vramPercent)}`}
            style={{ width: `${vramPercent}%` }}
          />
        </div>
      )}
    </div>
  );
}

type RuntimeSnapshotSummaryProps = Readonly<{
  snapshot: RuntimeSnapshotLike;
  compact?: boolean;
}>;

function RuntimeSnapshotSummary({
  snapshot,
  compact = false,
}: RuntimeSnapshotSummaryProps) {
  const t = useTranslation();
  if (!snapshot) return null;

  const provider = snapshot.provider ?? "—";
  const model = snapshot.model_name ?? "—";
  const profile = snapshot.runtime_capabilities?.compatibility_profile ?? snapshot.voice_pipeline?.profile ?? null;
  const title = t("voice.daemon.runtimeSnapshot");

  return (
    <div className={`mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 ${compact ? "" : "mt-2"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">{title}</span>
        {snapshot.runtime_capabilities?.probe_status && (
          <span className="text-[10px] text-zinc-400">
            {snapshot.runtime_capabilities.probe_status}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-white truncate">
        {provider} / {model}
      </p>
      {profile && (
        <p className="mt-0.5 text-[10px] text-zinc-500 truncate">
          {t("voice.controls.profile")}: {profile}
        </p>
      )}
      {snapshot.voice_pipeline?.tts && (
        <p className="mt-0.5 text-[10px] text-zinc-500 truncate">
          {t("voice.controls.tts")}: {snapshot.voice_pipeline.tts}
        </p>
      )}
      {snapshot.error && (
        <p className="mt-0.5 text-[10px] text-rose-400 truncate">{snapshot.error}</p>
      )}
    </div>
  );
}

type DrafterBoxProps = Readonly<{
  daemon: Gemma4DaemonState;
  assistantModel: string | null;
  busy: boolean;
  actionPending: string | null;
  drafterInput: string;
  setDrafterInput: (v: string) => void;
  showDrafterInput: boolean;
  setShowDrafterInput: (v: boolean) => void;
  onAttach: () => void;
}>;

function DrafterBox({
  daemon,
  assistantModel,
  busy,
  actionPending,
  drafterInput,
  setDrafterInput,
  showDrafterInput,
  setShowDrafterInput,
  onAttach,
}: DrafterBoxProps) {
  const t = useTranslation();

  return (
    <div className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          {t("voice.daemon.assistantDrafter")}
        </span>
        {assistantModel ? (
          <Button size="xs" variant="ghost" onClick={daemon.detachAssistant} disabled={busy}>
            {actionPending === "detach" ? t("voice.daemon.busy") : t("voice.daemon.detachDrafter")}
          </Button>
        ) : (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => setShowDrafterInput(!showDrafterInput)}
            disabled={busy}
          >
            {t("voice.daemon.attachDrafter")}
          </Button>
        )}
      </div>

      {assistantModel ? (
        <p className="mt-1 text-xs text-white truncate">{assistantModel}</p>
      ) : (
        <p className="mt-1 text-[10px] text-zinc-600">{t("voice.daemon.noDrafter")}</p>
      )}

      {showDrafterInput && !assistantModel && (
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={drafterInput}
            onChange={(e) => setDrafterInput(e.target.value)}
            placeholder={t("voice.daemon.drafterModelPlaceholder")}
            disabled={busy}
            className="flex-1 min-w-0 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
          />
          <Button
            size="xs"
            variant="primary"
            onClick={onAttach}
            disabled={busy || !drafterInput.trim()}
          >
            {actionPending === "attach" ? t("voice.daemon.busy") : t("voice.daemon.ok")}
          </Button>
        </div>
      )}
    </div>
  );
}

function DaemonCard({
  variant,
  children,
}: Readonly<{ variant: Variant; children: React.ReactNode }>) {
  const t = useTranslation();
  if (variant === "voice") {
    return (
      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-3 text-xs text-zinc-300">
        <p className="eyebrow mb-2">{t("voice.daemon.title")}</p>
        {children}
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs text-zinc-400">
      <p className="mb-2 text-[10px] uppercase tracking-widest text-zinc-500">
        {t("voice.daemon.title")}
      </p>
      {children}
    </div>
  );
}

type DaemonConfirmActionButtonProps = Readonly<{
  busy: boolean;
  actionPending: string | null;
  actionName: string;
  pendingLabel: string;
  buttonLabel: string;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
  buttonVariant: "ghost" | "secondary";
  confirmVariant?: "default" | "danger";
  testId: string;
}>;

function DaemonConfirmActionButton({
  busy,
  actionPending,
  actionName,
  pendingLabel,
  buttonLabel,
  title,
  description,
  confirmLabel,
  onConfirm,
  buttonVariant,
  confirmVariant,
  testId,
}: DaemonConfirmActionButtonProps) {
  return (
    <ConfirmDialog>
      <ConfirmDialogTrigger asChild>
        <Button size="xs" variant={buttonVariant} disabled={busy} data-testid={testId}>
          {actionPending === actionName ? pendingLabel : buttonLabel}
        </Button>
      </ConfirmDialogTrigger>
      <ConfirmDialogContent>
        <ConfirmDialogTitle>{title}</ConfirmDialogTitle>
        <ConfirmDialogDescription>{description}</ConfirmDialogDescription>
        <ConfirmDialogActions
          onConfirm={onConfirm}
          onCancel={() => {}}
          confirmLabel={confirmLabel}
          confirmVariant={confirmVariant}
        />
      </ConfirmDialogContent>
    </ConfirmDialog>
  );
}
