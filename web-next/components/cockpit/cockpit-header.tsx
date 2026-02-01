"use client";

import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";
import { Command } from "lucide-react";

type CockpitHeaderProps = {
  showReferenceSections: boolean;
  showArtifacts: boolean;
  onToggleArtifacts: () => void;
};

export function CockpitHeader({
  showReferenceSections,
  showArtifacts,
  onToggleArtifacts,
}: CockpitHeaderProps) {
  const t = useTranslation();

  return (
    <SectionHeading
      eyebrow={t("cockpit.header.eyebrow")}
      title={t("cockpit.header.dashboardTitle")}
      description={
        <span className="text-zinc-200">
          {t("cockpit.header.dashboardDescription")}
        </span>
      }
      as="h1"
      size="lg"
      rightSlot={
        <div className="flex items-center gap-3">
          {!showReferenceSections && (
            <Button
              size="sm"
              variant="outline"
              className="text-zinc-200"
              onClick={onToggleArtifacts}
            >
              {showArtifacts
                ? t("cockpit.header.togglePanels.hide")
                : t("cockpit.header.togglePanels.show")}
            </Button>
          )}
          <Command className="page-heading-icon" />
        </div>
      }
    />
  );
}
