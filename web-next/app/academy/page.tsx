"use client";

import { Suspense } from "react";
import { AcademyDashboard } from "@/components/academy/academy-dashboard";
import { useTranslation } from "@/lib/i18n";

export default function AcademyPage() {
  const t = useTranslation();
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-zinc-400">{t("academy.common.loadingAcademy")}</div>
        </div>
      }
    >
      <AcademyDashboard />
    </Suspense>
  );
}
