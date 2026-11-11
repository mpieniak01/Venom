"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { THEME_TAB_BAR_CLASS, getThemeTabClass } from "@/lib/theme-ui";
import { ExperimentsPanel } from "./experiments-panel";
import { TrainingPanel } from "./training-panel";

export function TrainingWorkspace() {
  const t = useTranslation();
  const [experimentMode, setExperimentMode] = useState(false);

  return (
    <div className="space-y-4">
      <div className={THEME_TAB_BAR_CLASS} role="group" aria-label={t("academy.experiments.mode")}>
        <Button
          type="button"
          variant="ghost"
          aria-pressed={!experimentMode}
          className={getThemeTabClass(!experimentMode)}
          onClick={() => setExperimentMode(false)}
        >
          {t("academy.experiments.single")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          aria-pressed={experimentMode}
          className={getThemeTabClass(experimentMode)}
          onClick={() => setExperimentMode(true)}
        >
          {t("academy.experiments.title")}
        </Button>
      </div>
      {experimentMode ? <ExperimentsPanel /> : <TrainingPanel />}
    </div>
  );
}
