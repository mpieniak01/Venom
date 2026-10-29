import { useId, useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/date";
import type { RemoteProviderStatus } from "./hooks/use-remote-models";

interface Props {
  provider: RemoteProviderStatus;
  pending: boolean;
  manage: (provider: string, enabled?: boolean) => Promise<void>;
  connectVast: (planId: string | null) => Promise<void>;
  t: (key: string) => string;
}

export function RemoteProviderCard({ provider, pending, manage, connectVast, t }: Readonly<Props>) {
  const [planId, setPlanId] = useState("");
  const planInputId = useId();
  const normalizedPlanId = planId.trim().toLowerCase();
  const validPlan = /^[a-f0-9]{32}$/.test(normalizedPlanId);
  const managed = provider.provider === "openrouter" || provider.provider === "vast_ollama";
  const name = provider.provider === "openrouter" ? "OpenRouter" : provider.provider === "vast_ollama" ? "VAST · Ollama" : provider.provider;
  const key = "models.sections.remote.controls.";
  return <div className="rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">{name}</span>
        {managed ? <>
          <Badge tone={provider.enabled ? "success" : "neutral"}>{t(key + (provider.enabled ? "enabled" : "disabled"))}</Badge>
          <Badge tone={provider.configured ? "success" : "warning"}>{t(key + (provider.configured ? "configured" : "unconfigured"))}</Badge>
          <Badge tone={provider.available ? "success" : "neutral"}>{t(key + (provider.available === true ? "available" : provider.available === false ? "unavailable" : "unchecked"))}</Badge>
          {provider.selected && <Badge tone="warning">{t(key + "selected")}</Badge>}
        </> : <Badge tone={provider.status === "configured" ? "success" : "neutral"}>{provider.status}</Badge>}
      </div>
      {managed && <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={pending} onClick={() => void manage(provider.provider)}>{t(key + "check")}</Button>
        <Button size="sm" variant="secondary" disabled={pending} aria-label={name + ": " + t(key + (provider.enabled ? "disable" : "enable"))} onClick={() => void manage(provider.provider, !provider.enabled)}>{t(key + (provider.enabled ? "disable" : "enable"))}</Button>
      </div>}
    </div>
    <div className="mt-3 flex flex-wrap gap-4 text-xs text-[color:var(--ui-muted)]">
      {provider.latency_ms !== null && <span>{t("models.sections.remote.providerStatus.latency")}: {provider.latency_ms.toFixed(0)}ms</span>}
      <span>{t("models.sections.remote.providerStatus.lastCheck")}: {provider.last_check ? formatDateTime(provider.last_check) : t(key + "unchecked")}</span>
      {provider.error && <Badge tone="danger">{provider.error}</Badge>}
    </div>
    {managed && <p className="mt-3 text-xs text-[color:var(--ui-muted)]">{t(key + "enableHint")}</p>}
    {provider.provider === "vast_ollama" && <div className="mt-3 flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 text-xs text-[color:var(--ui-muted)]" htmlFor={planInputId}>{t(key + "planId")}
        <input id={planInputId} value={planId} onChange={(event) => setPlanId(event.target.value)} maxLength={32} spellCheck={false} autoComplete="off" className="rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-2 text-[color:var(--text-primary)]" />
      </label>
      <Button size="sm" variant="secondary" disabled={pending || !provider.enabled || !validPlan} onClick={() => void connectVast(normalizedPlanId)}>{t(key + "attach")}</Button>
      <Button size="sm" variant="secondary" disabled={pending || !provider.configured} onClick={() => void connectVast(null)}>{t(key + "detach")}</Button>
    </div>}
    {provider.provider === "vast_ollama" && <p className="mt-2 text-xs text-[color:var(--ui-muted)]">{t(key + "vastHint")} <Link className="underline underline-offset-4" href="/config?tab=integrations&integration=core%3Avast">{t(key + "manageInfrastructure")}</Link></p>}
  </div>;
}
