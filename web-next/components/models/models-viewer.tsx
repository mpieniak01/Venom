"use client";

import React, { useState } from "react";
import { Layers, Newspaper, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { cn } from "@/lib/utils";
import {
  setActiveLlmServer,
  switchModel
} from "@/hooks/use-api";
import { useToast } from "@/components/ui/toast";
import { useModelsViewerLogic } from "./use-models-viewer-logic";
import {
  RuntimeSection,
  SearchSection,
  NewsSection,
  RecommendedAndCatalog,
  InstalledAndOperations
} from "./models-viewer-sections";

export const ModelsViewer = () => {
  const { pushToast } = useToast();
  const logic = useModelsViewerLogic();
  const { t } = logic;
  const [activeTab, setActiveTab] = useState<"news" | "models">("news");

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
      <div className="flex gap-2 border-b border-white/10">
        <Button
          onClick={() => setActiveTab("news")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "news"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Newspaper className="h-4 w-4" />
          {t("models.tabs.news")}
        </Button>
        <Button
          onClick={() => setActiveTab("models")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "models"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Server className="h-4 w-4" />
          {t("models.tabs.models")}
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
              <RuntimeSection
                {...logic}
                setActiveLlmServer={setActiveLlmServer}
                switchModel={switchModel}
                pushToast={pushToast}
              />
            </div>

            <div className="flex flex-col gap-10 mt-10">
              <SearchSection {...logic} trainableModels={logic.trainableModels} />

              <InstalledAndOperations {...logic} />
            </div>
          </>
        )}
      </div>
    </div>
  );
};
