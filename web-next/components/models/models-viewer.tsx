"use client";

import React from "react";
import { Layers } from "lucide-react";
import { SectionHeading } from "@/components/ui/section-heading";
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

      <div className="grid gap-10 items-start" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
        <RuntimeSection
          {...logic}
          setActiveLlmServer={setActiveLlmServer}
          switchModel={switchModel}
          pushToast={pushToast}
        />
      </div>

      <div className="flex flex-col gap-10">
        <SearchSection {...logic} />

        <NewsSection {...logic} />

        <section className="grid gap-10 lg:grid-cols-[2.2fr_1fr]">
          <RecommendedAndCatalog {...logic} />

          <InstalledAndOperations {...logic} />
        </section>
      </div>
    </div>
  );
};
