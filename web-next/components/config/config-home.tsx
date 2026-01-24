"use client";

import { useState } from "react";
import { Settings, Server, FileCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { ServicesPanel } from "./services-panel";
import { ParametersPanel } from "./parameters-panel";

export function ConfigHome() {
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState<"services" | "parameters">("services");

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
      <div className="flex gap-2 border-b border-white/10">
        <Button
          onClick={() => setActiveTab("services")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "services"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Server className="h-4 w-4" />
          {t("config.tabs.services")}
        </Button>
        <Button
          onClick={() => setActiveTab("parameters")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "parameters"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <FileCode className="h-4 w-4" />
          {t("config.tabs.parameters")}
        </Button>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {activeTab === "services" && <ServicesPanel />}
        {activeTab === "parameters" && <ParametersPanel />}
      </div>
    </div>
  );
}
