"use client";

import Link from "next/link";
import { AlertTriangle, Info, Save } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ParametersMessage(input: {
  message: { type: "success" | "error"; text: string } | null;
}) {
  const { message } = input;
  if (!message) return null;
  return (
    <div
      className={`rounded-xl border p-4 ${message.type === "success" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-red-500/30 bg-red-500/10 text-red-300"}`}
    >
      {message.text}
    </div>
  );
}

export function RestartRequiredNotice(input: {
  t: (key: string, vars?: Record<string, string>) => string;
  restartRequired: string[];
}) {
  const { t, restartRequired } = input;
  if (restartRequired.length === 0) return null;
  return (
    <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 text-yellow-400" />
        <div>
          <p className="font-semibold text-yellow-300">
            {t("config.parameters.restartRequired.title")}
          </p>
          <p className="mt-1 text-sm text-yellow-200">
            {t("config.parameters.restartRequired.message", {
              services: restartRequired.join(", "),
            })}
          </p>
          <p className="mt-2 text-xs text-yellow-200/80">
            {t("config.parameters.restartRequired.hint")}
          </p>
        </div>
      </div>
    </div>
  );
}

export function RuntimeInfoCard(input: {
  t: (key: string) => string;
  vllmAvailableInProfile: boolean;
}) {
  const { t, vllmAvailableInProfile } = input;
  return (
    <div className="glass-panel rounded-2xl border border-white/10 bg-gradient-to-r from-violet-500/10 to-cyan-500/10 p-6">
      <div className="flex items-start gap-3">
        <Info className="mt-0.5 h-5 w-5 text-cyan-400" />
        <div>
          <h3 className="heading-h3">{t("config.parameters.runtimeInfo.title")}</h3>
          <p className="mt-2 text-sm text-zinc-300">{t("config.parameters.runtimeInfo.ollama")}</p>
          {vllmAvailableInProfile ? (
            <p className="mt-2 text-sm text-zinc-300">
              {t("config.parameters.runtimeInfo.vllm")}
            </p>
          ) : null}
          <p className="mt-3 text-hint">
            {t("config.parameters.runtimeInfo.hint")}{" "}
            <Link href="/benchmark" className="text-emerald-400 hover:underline">
              {t("config.parameters.runtimeInfo.benchmark")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export function ParametersActionBar(input: {
  t: (key: string, vars?: Record<string, string>) => string;
  hasChanges: boolean;
  changedCount: number;
  saving: boolean;
  onReset: () => void;
  onSave: () => void;
}) {
  const { t, hasChanges, changedCount, saving, onReset, onSave } = input;
  return (
    <div className="glass-panel sticky bottom-6 rounded-2xl box-muted p-6 backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          {hasChanges ? (
            <p className="text-sm text-yellow-300">
              {t("config.parameters.unsavedChanges", { count: String(changedCount) })}
            </p>
          ) : null}
        </div>
        <div className="flex gap-3">
          <Button onClick={onReset} disabled={!hasChanges || saving} variant="secondary">
            {t("config.parameters.buttons.reset")}
          </Button>
          <Button onClick={onSave} disabled={!hasChanges || saving}>
            <Save className="mr-2 h-4 w-4" />
            {saving ? t("config.parameters.buttons.saving") : t("config.parameters.buttons.save")}
          </Button>
        </div>
      </div>
    </div>
  );
}
