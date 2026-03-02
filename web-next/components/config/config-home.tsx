"use client";

import { useState } from "react";
import { Settings, Server, FileCode, Network, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { THEME_TAB_BAR_CLASS, getThemeTabClass } from "@/lib/theme-ui";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { ServicesPanel } from "./services-panel";
import { ParametersPanel } from "./parameters-panel";
import { ApiMap } from "./api-map";
import { AuditPanel } from "./audit-panel";

export function ConfigHome() {
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState<"services" | "parameters" | "apiMap" | "audit">("services");

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow={t("config.title")}
        title={t("config.title")}
        description={t("config.description")}
        as="h1"
        size="lg"
        rightSlot={<Settings className="page-heading-icon" />}
      />

      {/* Tabs */}
      <div className={THEME_TAB_BAR_CLASS}>
        <Button
          onClick={() => setActiveTab("services")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "services"))}
        >
          <Server className="h-4 w-4" />
          {t("config.tabs.services")}
        </Button>
        <Button
          onClick={() => setActiveTab("parameters")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "parameters"))}
        >
          <FileCode className="h-4 w-4" />
          {t("config.tabs.parameters")}
        </Button>
        <Button
          onClick={() => setActiveTab("apiMap")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "apiMap"))}
        >
          <Network className="h-4 w-4" />
          {t("config.apiMap.title")}
        </Button>
        <Button
          onClick={() => setActiveTab("audit")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "audit"))}
        >
          <ShieldCheck className="h-4 w-4" />
          {t("config.tabs.audit")}
        </Button>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {activeTab === "services" && <ServicesPanel />}
        {activeTab === "parameters" && <ParametersPanel />}
        {activeTab === "apiMap" && <ApiMap />}
        {activeTab === "audit" && <AuditPanel />}
      </div>
    </div>
  );
}
