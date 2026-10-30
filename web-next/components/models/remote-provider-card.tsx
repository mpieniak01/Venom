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
const controlsKey = "models.sections.remote.controls.";
function providerName(provider: string): string {
  if (provider === "openai") return "OpenAI";
  if (provider === "google") return "Google";
  if (provider === "openrouter") return "OpenRouter";
  if (provider === "vast_ollama") return "VAST · Ollama";
  return provider;
}
function availabilityLabel(available: RemoteProviderStatus["available"]): string {
  if (available === true) return "available";
  if (available === false) return "unavailable";
  return "unchecked";
}

function ManagedProviderBadges({ provider, t }: Readonly<Pick<Props, "provider" | "t">>) {
  return <>
    <Badge tone={provider.enabled ? "success" : "neutral"}>{t(controlsKey + (provider.enabled ? "enabled" : "disabled"))}</Badge>
    <Badge tone={provider.configured ? "success" : "warning"}>{t(controlsKey + (provider.configured ? "configured" : "unconfigured"))}</Badge>
    <Badge tone={provider.available ? "success" : "neutral"}>{t(controlsKey + availabilityLabel(provider.available))}</Badge>
    {provider.provider === "vast_ollama" && provider.available === true && <Badge tone="success">{t("models.vast.connected")}</Badge>}
    {provider.selected && <Badge tone="warning">{t(controlsKey + "selected")}</Badge>}
  </>;
}

function ProviderObservations({ provider, t }: Readonly<Pick<Props, "provider" | "t">>) {
  return <div className="mt-3 flex flex-wrap gap-4 text-xs text-[color:var(--ui-muted)]">
    {provider.latency_ms !== null && <span>{t("models.sections.remote.providerStatus.latency")}: {provider.latency_ms.toFixed(0)}ms</span>}
    <span>{t("models.sections.remote.providerStatus.lastCheck")}: {provider.last_check ? formatDateTime(provider.last_check) : t(controlsKey + "unchecked")}</span>
    {provider.error && <Badge tone="danger">{provider.error}</Badge>}
  </div>;
}

function VastConnectionControls({ provider, pending, connectVast, t }: Readonly<Pick<Props, "provider" | "pending" | "connectVast" | "t">>) {
  const [planId, setPlanId] = useState("");
  const planInputId = useId();
  const normalizedPlanId = planId.trim().toLowerCase();
  const validPlan = /^[a-f0-9]{32}$/.test(normalizedPlanId);
  return <>
    <div className="mt-3 flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 text-xs text-[color:var(--ui-muted)]" htmlFor={planInputId}>{t(controlsKey + "planId")}
        <input id={planInputId} value={planId} onChange={event => setPlanId(event.target.value)} maxLength={32} spellCheck={false} autoComplete="off" className="rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-2 text-[color:var(--text-primary)]" />
      </label>
      <Button size="sm" variant="secondary" disabled={pending || !provider.enabled || !validPlan} onClick={() => void connectVast(normalizedPlanId)}>{t(controlsKey + "attach")}</Button>
      <Button size="sm" variant="secondary" disabled={pending || !provider.configured} onClick={() => void connectVast(null)}>{t(controlsKey + "detach")}</Button>
    </div>
    <p className="mt-2 text-xs text-[color:var(--ui-muted)]">{t(controlsKey + "vastHint")} <Link className="underline underline-offset-4" href="/models?tab=vast">{t(controlsKey + "manageInfrastructure")}</Link></p>
  </>;
}

export function RemoteProviderCard({ provider, pending, manage, connectVast, t }: Readonly<Props>) {
  const managed = ["openai", "google", "openrouter", "vast_ollama"].includes(provider.provider);
  const name = providerName(provider.provider);
  const toggleLabel = t(controlsKey + (provider.enabled ? "disable" : "enable"));
  return <div className="rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">{name}</span>
        {managed ? <ManagedProviderBadges provider={provider} t={t} /> : <Badge tone={provider.status === "configured" ? "success" : "neutral"}>{provider.status}</Badge>}
      </div>
      {managed && <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={pending} onClick={() => void manage(provider.provider)}>{t(controlsKey + "check")}</Button>
        <Button size="sm" variant="secondary" disabled={pending} aria-label={name + ": " + toggleLabel} onClick={() => void manage(provider.provider, !provider.enabled)}>{toggleLabel}</Button>
      </div>}
    </div>
    <ProviderObservations provider={provider} t={t} />
    {managed && <p className="mt-3 text-xs text-[color:var(--ui-muted)]">{t(controlsKey + "enableHint")}</p>}
    {provider.provider === "vast_ollama" && <VastConnectionControls provider={provider} pending={pending} connectVast={connectVast} t={t} />}
  </div>;
}
