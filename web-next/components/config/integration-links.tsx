"use client";

import Link from "next/link";
import { useTranslation } from "@/lib/i18n";
import { configHref } from "@/lib/config-navigation";
import { useIntegrationInventory } from "@/lib/integration-inventory";

export function IntegrationLinks({ parameter, active = true }: { parameter?: string; active?: boolean }) {
  const t = useTranslation();
  const { data } = useIntegrationInventory(active);
  const entries = (data?.integrations ?? []).filter((entry) => parameter ? entry.configuration_keys?.includes(parameter) : entry.configuration === "configured" || entry.kind === "module");
  return <nav aria-label={t("config.navigation.relatedIntegrations")} className="flex flex-wrap items-center gap-2 text-sm">
    <span className="text-theme-muted">{t("config.navigation.relatedIntegrations")}:</span>
    {entries.map((entry) => <Link key={entry.id} className="rounded-lg border border-theme px-2 py-1 hover:bg-theme-overlay" href={configHref({ tab: "integrations", integration: entry.id, visibility: "all" })}>{entry.label}</Link>)}
    {!entries.length && <Link className="underline" href={configHref({ tab: "integrations" })}>{t("config.apiMap.title")}</Link>}
  </nav>;
}
