"use client";

import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";
import { Command } from "lucide-react";

export function CockpitHeader() {
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
          <Command className="page-heading-icon" />
        </div>
      }
    />
  );
}
