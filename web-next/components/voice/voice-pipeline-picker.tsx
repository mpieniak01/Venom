"use client";

import { useEffect, useRef, useState } from "react";
import { setActiveLlmServer } from "@/hooks/use-api";
import { apiFetch } from "@/lib/api-client";
import { useLanguage } from "@/lib/i18n";

type VoicePipelines = {
  active_model: string | null;
  gemma_models: string[];
  omni_model: string | null;
};

const lastGemmaKey = "venom:voice:last-gemma";
const gemmaFallback = "gemma4:e4b";

/** Prefer the active Gemma, then the last installed choice remembered by this browser. */
function chooseGemma(options: VoicePipelines): string | undefined {
  if (options.active_model && options.gemma_models.includes(options.active_model)) {
    return options.active_model;
  }
  let previous: string | null = null;
  try { previous = window.localStorage.getItem(lastGemmaKey); } catch { /* Optional preference. */ }
  if (previous && options.gemma_models.includes(previous)) return previous;
  return options.gemma_models.find(model => model === gemmaFallback) ?? options.gemma_models[0];
}

/** Offer only installed voice pipelines from the capability catalog for the current surface. */
export function VoicePipelinePicker({
  surface, disabled, onApplied, onSwitching, refreshKey,
}: Readonly<{
  surface: "chat2" | "voice";
  disabled?: boolean;
  onApplied?: (model: string) => void;
  onSwitching?: (pending: boolean) => void;
  refreshKey?: string | number | null;
}>) {
  const { t, language } = useLanguage();
  const [options, setOptions] = useState<VoicePipelines | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const busy = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    void apiFetch<VoicePipelines>("/api/v1/chat/audio/pipelines?" + new URLSearchParams({ surface, language }), {
      signal: controller.signal,
    }).then(result => {
      if (!controller.signal.aborted) setOptions(result);
    }).catch(() => {
      if (!controller.signal.aborted) setOptions(null);
    });
    return () => controller.abort();
  }, [surface, language, refreshKey, reload]);

  const gemma = options ? chooseGemma(options) : undefined;
  const omni = options?.omni_model;
  const active = options?.active_model;
  /** Serialize switches and keep the previous Gemma available when returning from Omni. */
  const apply = async (model: string | undefined | null) => {
    if (!model || model === active || disabled || busy.current) return;
    busy.current = true;
    setPending(true);
    onSwitching?.(true);
    setFailed(false);
    try {
      await setActiveLlmServer("ollama", model);
      const lastGemma = model === omni ? gemma : model;
      if (lastGemma) {
        try { window.localStorage.setItem(lastGemmaKey, lastGemma); } catch { /* Optional preference. */ }
      }
      setOptions(current => current && { ...current, active_model: model });
      onApplied?.(model);
    } catch {
      setFailed(true);
    } finally {
      busy.current = false;
      setPending(false);
      onSwitching?.(false);
      setReload(current => current + 1);
    }
  };
  const label = (model: string | undefined | null) => model != null && model === active;
  return <fieldset disabled={disabled || pending} className="space-y-2" aria-busy={pending}>
    <legend className="font-medium">{t("chat2.voicePipeline")}</legend>
    <div className="flex flex-wrap gap-2">
      <button type="button" className="rounded-lg border px-3 py-1 text-sm disabled:opacity-50" disabled={!gemma || label(gemma)}
        aria-pressed={label(gemma)} title={gemma} onClick={() => { void apply(gemma); }}>{t("chat2.voiceGemma")}</button>
      <button type="button" className="rounded-lg border px-3 py-1 text-sm disabled:opacity-50" disabled={!omni || label(omni)}
        aria-pressed={label(omni)} onClick={() => { void apply(omni); }}>{t("chat2.voiceOmni")}</button>
    </div>
    <p className="text-xs opacity-75">{t(omni ? "chat2.voicePipelineHint" : "chat2.voiceOmniUnavailable")}</p>
    {active && <p className="text-xs opacity-75">{t("chat2.voiceActiveModel", { model: active })}</p>}
    {failed && <p role="alert" className="text-xs">{t("chat2.voicePipelineError")}</p>}
  </fieldset>;
}
