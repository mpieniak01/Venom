"use client";

import { VastEnvironmentsSection } from "./vast-environments-section";
import { OpenRouterModelsSection } from "./openrouter-models-section";
import { ModelResourcesControl } from "./model-resources-control";
import React, { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { configHref } from "@/lib/config-navigation";
import { Layers, Newspaper, Server, Cloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { THEME_TAB_BAR_CLASS, getThemeTabClass } from "@/lib/theme-ui";
import { cn } from "@/lib/utils";
import { useModelsViewerLogic } from "./use-models-viewer-logic";
import {
  RuntimeSection,
  SearchSection,
  NewsSection,
  RecommendedAndCatalog,
  InstalledAndOperations,
  RemoteModelsSection
} from "./models-viewer-sections";

type ModelsTab = "news" | "models" | "remote" | "openrouter" | "vast";
function subscribeToLocation(callback: () => void) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}
function locationTab(): ModelsTab {
  return new URLSearchParams(window.location.search).get("tab") === "vast" ? "vast" : "news";
}
const serverTab = (): ModelsTab => "news";

export const ModelsViewer = () => {
  const logic = useModelsViewerLogic();
  const { t } = logic;
  const initialTab = useSyncExternalStore(subscribeToLocation, locationTab, serverTab);
  const [chosenTab, setChosenTab] = useState<ModelsTab | null>(null);
  const activeTab = chosenTab ?? initialTab;

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow={t("models.page.eyebrow")}
        title={t("models.page.title")}
        description={t("models.page.description")}
        as="h1"
        size="lg"
        rightSlot={<Layers className="page-heading-icon" />}
      />

      <Link className="inline-block text-sm underline underline-offset-4" href={configHref({ tab: "integrations", integration: "core:local-runtime", visibility: "all" })}>{t("config.navigation.overviewShortcut")}</Link>
      <ModelResourcesControl
        releasing={logic.releasingResources}
        memory={logic.modelResources.data?.memory}
        result={logic.resourceRelease}
        entries={logic.resourceReleaseRows}
        error={logic.resourceReleaseError}
        onRelease={logic.handleReleaseAllModels}
        t={t}
      />
      {/* Tabs */}
      <div className={THEME_TAB_BAR_CLASS}>
        <Button
          onClick={() => setChosenTab("news")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "news"))}
        >
          <Newspaper className="h-4 w-4" />
          {t("models.tabs.news")}
        </Button>
        <Button
          onClick={() => setChosenTab("models")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "models"))}
        >
          <Server className="h-4 w-4" />
          {t("models.tabs.models")}
        </Button>
        <Button
          onClick={() => setChosenTab("remote")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "remote"))}
        >
          <Cloud className="h-4 w-4" />
          {t("models.tabs.remoteModels")}
        </Button>
        <Button onClick={() => setChosenTab("openrouter")} variant="ghost" size="sm" className={cn(getThemeTabClass(activeTab === "openrouter"))}>
          <Cloud className="h-4 w-4" />OpenRouter
        </Button>
        <Button onClick={() => setChosenTab("vast")} variant="ghost" size="sm" className={cn(getThemeTabClass(activeTab === "vast"))}>
          <Cloud className="h-4 w-4" />{t("models.vast.tab")}
        </Button>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {activeTab === "news" && (
          <div className="flex flex-col gap-10">
            <NewsSection {...logic} />

            <RecommendedAndCatalog {...logic} trainableModels={logic.trainableModels} />
          </div>
        )}

        {activeTab === "models" && (
          <>
            <div className="grid gap-10 items-start" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
              <RuntimeSection {...logic} />
            </div>

            <div className="flex flex-col gap-10 mt-10">
              <SearchSection {...logic} trainableModels={logic.trainableModels} />

              <InstalledAndOperations {...logic} />
            </div>
          </>
        )}

        {activeTab === "vast" && <VastEnvironmentsSection t={t} onChanged={async () => { await Promise.all([logic.llmServers.refresh(), logic.fetchRemoteProviders()]); }} />}
        {activeTab === "openrouter" && <OpenRouterModelsSection t={t} onChanged={async () => { await Promise.all([logic.llmServers.refresh(), logic.fetchRemoteProviders()]); }} />}
        {activeTab === "remote" && (
          <RemoteModelsSection {...logic} />
        )}
      </div>
    </div>
  );
};
