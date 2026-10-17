"use client";

import { useState } from "react";
import { Settings, Server, FileCode, Network, ShieldCheck, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { THEME_TAB_BAR_CLASS, getThemeTabClass } from "@/lib/theme-ui";
import { useConfigNavigation, type ConfigTab } from "@/lib/config-navigation";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { ServicesPanel } from "./services-panel";
import { ParametersPanel } from "./parameters-panel";
import { ApiMap } from "./api-map";
import { AuditPanel } from "./audit-panel";
import { PermissionsPanel } from "./permissions-panel";
import { IntegrationTopologyBoundary } from "./integration-topology-boundary";
import { IntegrationLinks } from "./integration-links";

/** Render configuration tabs while retaining visited parameter drafts across tab changes. */
export function ConfigHome() {
  const t = useTranslation();
  const navigation = useConfigNavigation();
  const [parametersVisited, setParametersVisited] = useState(false);
  const activeTab = navigation.tab;
  if (activeTab === "parameters" && !parametersVisited) setParametersVisited(true);
  const tabs = [
    ["services", Server, "config.tabs.services"], ["parameters", FileCode, "config.tabs.parameters"],
    ["integrations", Network, "config.apiMap.title"], ["topology", Network, "config.topology.title"], ["audit", ShieldCheck, "config.tabs.audit"],
    ["permissions", KeyRound, "config.tabs.permissions"],
  ] as const;
  const selectTab = (tab: ConfigTab) => {
    if (tab === "parameters") setParametersVisited(true);
    navigation.navigate(tab === activeTab ? { tab } : { tab, query: "" });
  };

  const tabKeyIndex = (key: string, index: number) => {
    switch (key) {
      case "ArrowRight": return (index + 1) % tabs.length;
      case "ArrowLeft": return (index + tabs.length - 1) % tabs.length;
      case "Home": return 0;
      case "End": return tabs.length - 1;
      default: return null;
    }
  };

  return <div className="space-y-6 pb-48 sm:pb-12">
    <SectionHeading eyebrow={t("config.title")} title={t("config.title")} description={t("config.description")} as="h1" size="lg" rightSlot={<Settings className="page-heading-icon" />} />
    {navigation.invalidTab && <output className="text-sm text-theme-muted">{t("config.navigation.unknownTab")}</output>}
    <div role="tablist" aria-label={t("config.title")} className={cn(THEME_TAB_BAR_CLASS, "flex-wrap sm:flex-nowrap")}>
      {tabs.map(([tab, Icon, label], index) => <Button key={tab} id={`config-tab-${tab}`} role="tab" aria-selected={activeTab === tab} aria-controls={`config-panel-${tab}`} tabIndex={activeTab === tab ? 0 : -1}
        onKeyDown={(event) => {
          const next = tabKeyIndex(event.key, index);
          if (next === null) return;
          event.preventDefault(); selectTab(tabs[next][0]); document.getElementById(`config-tab-${tabs[next][0]}`)?.focus();
        }}
        onClick={() => selectTab(tab)} variant="ghost" size="sm" className={cn(getThemeTabClass(activeTab === tab))}><Icon className="h-4 w-4" />{t(label)}</Button>)}
    </div>
    <div className="min-h-[500px]">
      {activeTab === "services" && <div role="tabpanel" id="config-panel-services" aria-labelledby="config-tab-services" className="space-y-4"><IntegrationLinks /><ServicesPanel /></div>}
      {(parametersVisited || activeTab === "parameters") && <div role="tabpanel" id="config-panel-parameters" aria-labelledby="config-tab-parameters" hidden={activeTab !== "parameters"}><ParametersPanel active={activeTab === "parameters"} navigation={navigation} /></div>}
      {activeTab === "integrations" && <div role="tabpanel" id="config-panel-integrations" aria-labelledby="config-tab-integrations"><ApiMap navigation={navigation} /></div>}
      {activeTab === "topology" && <div role="tabpanel" id="config-panel-topology" aria-labelledby="config-tab-topology"><IntegrationTopologyBoundary navigation={navigation} /></div>}
      {activeTab === "audit" && <div role="tabpanel" id="config-panel-audit" aria-labelledby="config-tab-audit"><AuditPanel /></div>}
      {activeTab === "permissions" && <div role="tabpanel" id="config-panel-permissions" aria-labelledby="config-tab-permissions"><PermissionsPanel /></div>}
    </div>
  </div>;
}
