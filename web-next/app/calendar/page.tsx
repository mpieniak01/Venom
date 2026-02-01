"use client";

import { Suspense } from "react";
import { CalendarHome } from "@/components/calendar/calendar-home";
import { useTranslation } from "@/lib/i18n";

export default function CalendarPage() {
  const t = useTranslation();

  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-hint">{t("common.loading")}</div>
        </div>
      }
    >
      <CalendarHome />
    </Suspense>
  );
}
