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
import { type Gemma4DaemonState, useGemma4Daemon } from "@/hooks/use-gemma4-daemon";

const CACHE_OPTIONS = [
  { value: "", label: "default" },
  { value: "static", label: "static" },
  { value: "quantized", label: "quantized" },
  { value: "offloaded_static", label: "offloaded_static" },
] as const;

type Variant = "cockpit" | "voice";

type Props = Readonly<{
  variant?: Variant;
  pollingIntervalMs?: number;
}>;

export function Gemma4RuntimeControl({
  variant = "voice",
  pollingIntervalMs,
}: Props) {
  const daemon = useGemma4Daemon(pollingIntervalMs);
  return <Gemma4RuntimeControlInner daemon={daemon} variant={variant} />;
}

type InnerProps = Readonly<{
  daemon: Gemma4DaemonState;
  variant: Variant;
}>;

export function Gemma4RuntimeControlInner({ daemon, variant }: InnerProps) {
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
    localTokens !== "" ? localTokens : String(status?.params.max_new_tokens ?? 128);
  const effectiveCache =
    localCache !== null ? localCache : (status?.params.cache_implementation ?? "");

  const hasLocalChanges =
    localThinking !== null ||
    localTokens !== "" ||
    localCache !== null;

  async function handleApply() {
    const params: import("@/lib/gemma4-daemon-api").DaemonConfigRequest = {};
    if (localThinking !== null) params.enable_thinking = localThinking;
    if (localTokens !== "") {
      const n = parseInt(localTokens, 10);
      if (!isNaN(n) && n > 0) params.max_new_tokens = n;
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
    return (
      <DaemonCard variant={variant}>
        <p className="text-xs text-rose-400 py-1">{t("voice.daemon.daemonUnavailable")}</p>
        <p className="text-[10px] text-zinc-500 truncate">{error}</p>
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
          {!status?.target_loaded && (
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
              <span className="text-[10px] text-zinc-500">
                {localThinking !== null
                  ? t("voice.daemon.signalLive")
                  : status.params.enable_thinking
                  ? t("voice.daemon.thinkingOn")
                  : t("voice.daemon.thinkingOff")}
              </span>
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
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase tracking-widest text-zinc-500">
              {t("voice.daemon.vram")}
            </span>
            <span className="text-[10px] text-zinc-400">
              {vram.backend === "cuda"
                ? `${vram.allocated_mb} / ${vram.total_mb} MB`
                : t("voice.daemon.vramCpu")}
            </span>
          </div>
          {vram.backend === "cuda" && vramPercent !== null && (
            <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
              <div
                data-testid="vram-bar"
                className={`h-full rounded-full transition-all ${
                  vramPercent > 90
                    ? "bg-rose-500"
                    : vramPercent > 70
                    ? "bg-amber-400"
                    : "bg-emerald-400"
                }`}
                style={{ width: `${vramPercent}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* Drafter */}
      <div className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] uppercase tracking-widest text-zinc-500">
            {t("voice.daemon.assistantDrafter")}
          </span>
          {status?.assistant_model ? (
            <Button
              size="xs"
              variant="ghost"
              onClick={daemon.detachAssistant}
              disabled={busy}
            >
              {actionPending === "detach"
                ? t("voice.daemon.busy")
                : t("voice.daemon.detachDrafter")}
            </Button>
          ) : (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setShowDrafterInput((v) => !v)}
              disabled={busy}
            >
              {t("voice.daemon.attachDrafter")}
            </Button>
          )}
        </div>
        {status?.assistant_model ? (
          <p className="mt-1 text-xs text-white truncate">{status.assistant_model}</p>
        ) : (
          <p className="mt-1 text-[10px] text-zinc-600">{t("voice.daemon.noDrafter")}</p>
        )}
        {showDrafterInput && !status?.assistant_model && (
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
              onClick={handleAttach}
              disabled={busy || !drafterInput.trim()}
            >
              {actionPending === "attach" ? t("voice.daemon.busy") : t("voice.daemon.ok")}
            </Button>
          </div>
        )}
      </div>

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

        <ConfirmDialog>
          <ConfirmDialogTrigger asChild>
            <Button size="xs" variant="secondary" disabled={busy} data-testid="reload-button">
              {actionPending === "reload"
                ? t("voice.daemon.reloading")
                : t("voice.daemon.reload")}
            </Button>
          </ConfirmDialogTrigger>
          <ConfirmDialogContent>
            <ConfirmDialogTitle>{t("voice.daemon.confirmReloadTitle")}</ConfirmDialogTitle>
            <ConfirmDialogDescription>
              {t("voice.daemon.confirmReloadDesc")}
            </ConfirmDialogDescription>
            <ConfirmDialogActions
              onConfirm={daemon.reload}
              onCancel={() => {}}
              confirmLabel={t("voice.daemon.reload")}
            />
          </ConfirmDialogContent>
        </ConfirmDialog>

        <ConfirmDialog>
          <ConfirmDialogTrigger asChild>
            <Button size="xs" variant="ghost" disabled={busy} data-testid="restart-button">
              {actionPending === "restart"
                ? t("voice.daemon.restarting")
                : t("voice.daemon.restart")}
            </Button>
          </ConfirmDialogTrigger>
          <ConfirmDialogContent>
            <ConfirmDialogTitle>{t("voice.daemon.confirmRestartTitle")}</ConfirmDialogTitle>
            <ConfirmDialogDescription>
              {t("voice.daemon.confirmRestartDesc")}
            </ConfirmDialogDescription>
            <ConfirmDialogActions
              onConfirm={daemon.restart}
              onCancel={() => {}}
              confirmLabel={t("voice.daemon.restart")}
              confirmVariant="danger"
            />
          </ConfirmDialogContent>
        </ConfirmDialog>

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
