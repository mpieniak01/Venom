"use client";

import React, { useState } from "react";
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

export const ModelsViewer = () => {
  const logic = useModelsViewerLogic();
  const { t } = logic;
  const [activeTab, setActiveTab] = useState<"news" | "models" | "remote">("news");

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

      {/* Tabs */}
      <div className={THEME_TAB_BAR_CLASS}>
        <Button
          onClick={() => setActiveTab("news")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "news"))}
        >
          <Newspaper className="h-4 w-4" />
          {t("models.tabs.news")}
        </Button>
        <Button
          onClick={() => setActiveTab("models")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "models"))}
        >
          <Server className="h-4 w-4" />
          {t("models.tabs.models")}
        </Button>
        <Button
          onClick={() => setActiveTab("remote")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "remote"))}
        >
          <Cloud className="h-4 w-4" />
          {t("models.tabs.remoteModels")}
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

        {activeTab === "remote" && (
          <RemoteModelsSection {...logic} />
        )}
      </div>
    </div>
  );
};
