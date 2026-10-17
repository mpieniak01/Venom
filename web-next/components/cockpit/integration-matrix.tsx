"use client";

import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { ListCard } from "@/components/ui/list-card";
import type { ServiceStatus } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";
import { configHref } from "@/lib/config-navigation";
import { useIntegrationInventory } from "@/lib/integration-inventory";

type IntegrationMatrixProps = Readonly<{
  services?: ServiceStatus[] | null;
  events: Array<{ id: string; ts: number; payload: unknown }>;
}>;

function integrationTone(state: string) {
  if (state === "connected") return "success";
  if (["unavailable", "degraded"].includes(state)) return "warning";
  return "neutral";
}

export function IntegrationMatrix({ events }: IntegrationMatrixProps) {
  const t = useTranslation();
  const { data, failed } = useIntegrationInventory();
  const entries = (data?.integrations ?? []).filter((entry) => entry.configuration === "configured" || entry.kind === "module");
  return <Panel title={t("config.apiMap.title")} description={t("config.navigation.overviewDescription")}>
    <Link className="text-sm underline" href={configHref({ tab: "integrations" })}>{t("config.navigation.overviewShortcut")}</Link>
    {failed && <output className="mt-2 block text-sm text-theme-muted">{t("config.integrations.refreshFailed")}</output>}
    {!data && <p className="mt-2 text-sm text-theme-muted">{t("config.integrations.loading")}</p>}
    <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {entries.map((entry) => <Link key={entry.id} href={configHref({ tab: "integrations", integration: entry.id, visibility: "all" })} className="rounded-xl border border-theme p-3">
        <p className="font-medium">{entry.label}</p>
        <Badge tone={integrationTone(entry.state ?? "")}>{t(`config.integrations.states.${entry.state}`)}</Badge>
        <p className="mt-2 text-xs text-theme-muted">{t("config.integrations.resources")}: {entry.resource_count ?? t("config.integrations.unknown")}</p>
      </Link>)}
    </div>
    <div className="mt-4 space-y-2">
      <h3 className="text-sm font-medium">{t("config.navigation.operations")}</h3>
      {!events.length && <p className="text-xs text-theme-muted">{t("config.navigation.noEvents")}</p>}
      {events.slice(0, 4).map((event) => {
        const payload = typeof event.payload === "object" && event.payload !== null ? event.payload as Record<string, unknown> : {};
        const title = typeof event.payload === "string" ? event.payload.slice(0, 60) : String(payload.event ?? payload.type ?? t("config.navigation.systemEvent"));
        return <ListCard key={event.id} title={title} subtitle={typeof payload.detail === "string" ? payload.detail : t("config.navigation.eventDetails")} badge={<Badge tone="neutral">{new Date(event.ts).toLocaleTimeString()}</Badge>} />;
      })}
    </div>
  </Panel>;
}
