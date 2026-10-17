"use client";

import { useTranslation } from "@/lib/i18n";
import type { Integration } from "@/lib/integration-inventory";
import type { Resource } from "@/lib/integration-topology";

export function IntegrationStatusDetails({ entry, resource, generatedAt }: Readonly<{ entry: Integration; resource?: Resource; generatedAt?: string | null }>) {
  const t = useTranslation();
  const observedAt = resource ? resource.observed_at : entry.observed_at;
  const date = observedAt ? new Date(observedAt) : null;
  const snapshotTime = generatedAt ? new Date(generatedAt).getTime() : Number.NaN;
  const minutes = date && Number.isFinite(date.getTime()) && Number.isFinite(snapshotTime) ? Math.max(0, Math.floor((snapshotTime - date.getTime()) / 60000)) : null;
  return <>
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 break-words text-sm">
      <dt>{t("config.integrations.configuration")}</dt><dd>{t(`config.integrations.configurationStates.${resource?.configuration ?? entry.configuration}`)}</dd>
      {!resource && <><dt>{t("config.integrations.activation")}</dt><dd>{t(`config.integrations.activationStates.${entry.activation}`)}</dd></>}
      <dt>{t("config.integrations.connectivity")}</dt><dd>{resource ? t(`config.integrations.states.${resource.state}`) : t(`config.apiMap.filters.status.${entry.connectivity}`)}</dd>
      <dt>{t("config.integrations.location")}</dt><dd>{t(`config.integrations.locations.${entry.location}`)}</dd>
      <dt>{t("config.integrations.evidence")}</dt><dd>{t(`config.integrations.sources.${resource?.source ?? entry.source}`)}</dd>
      <dt>{t("config.integrations.observedAt")}</dt><dd>{date && Number.isFinite(date.getTime()) ? <><time dateTime={observedAt!}>{date.toLocaleString()}</time>{minutes != null && <> · {minutes} {t("config.topology.ageMinutes")}</>}</> : t("config.integrations.unknown")}</dd>
    </dl>
    <p className="rounded-lg bg-theme-overlay p-3 text-sm">{t(`config.integrations.reasons.${resource?.reason_code ?? entry.reason_code}`)}</p>
    {resource && <div className="space-y-2 text-sm">{(["supported", "reported", "available"] as const).map((kind) => <p key={kind}>{t(`config.navigation.${kind}Capabilities`)}: {resource[`${kind}_capabilities`] == null ? t("config.integrations.unknown") : resource[`${kind}_capabilities`]!.map((capability) => t(`config.integrations.capabilities.${capability}`)).join(" · ") || t("config.navigation.noCapabilities")}</p>)}</div>}
  </>;
}
