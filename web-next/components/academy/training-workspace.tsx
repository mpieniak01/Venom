"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { THEME_TAB_BAR_CLASS, getThemeTabClass } from "@/lib/theme-ui";
import { CampaignPanel } from "./campaign-panel";
import { ExperimentsPanel } from "./experiments-panel";
import { TrainingPanel } from "./training-panel";

const MODES = [
  ["single", "academy.experiments.single"],
  ["experiment", "academy.experiments.title"],
  ["campaign", "academy.campaigns.title"],
] as const;
type Mode = (typeof MODES)[number][0];

export function TrainingWorkspace({ initialCampaignId }: { readonly initialCampaignId?: string }) {
  const t = useTranslation();
  const [mode, setMode] = useState<Mode>(initialCampaignId ? "campaign" : "single");
  const [runId, setRunId] = useState("");

  function openRun(id: string) {
    setRunId(id);
    setMode("experiment");
  }

  return (
    <div className="space-y-4">
      <div className={THEME_TAB_BAR_CLASS} role="group" aria-label={t("academy.experiments.mode")}>
        {MODES.map(([value, label]) => (
          <Button
            key={value}
            type="button"
            variant="ghost"
            aria-pressed={mode === value}
            className={getThemeTabClass(mode === value)}
            onClick={() => setMode(value)}
          >
            {t(label)}
          </Button>
        ))}
      </div>
      {mode === "single" && <TrainingPanel />}
      {mode === "experiment" && <ExperimentsPanel initialRunId={runId} />}
      {mode === "campaign" && <CampaignPanel onOpenRun={openRun} initialCampaignId={initialCampaignId} />}
    </div>
  );
}
